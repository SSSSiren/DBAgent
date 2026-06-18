import json
import re
from typing import Any

from app.agent.llm import get_llm, is_llm_configured
from app.agent.prompts import PLAN_PROMPT, SUMMARIZE_RESPONSE_PROMPT, UNDERSTAND_PROMPT
from app.agent.state import AgentState, ToolCall
from app.memory.summary import update_summary
from app.tools import describe_table, execute_sql, list_databases, list_tables, needs_confirmation


def extract_json(content: str, fallback: Any) -> Any:
    """Parse JSON from plain text or fenced LLM output."""

    content = content.strip()
    if not content:
        return fallback
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        content = fenced.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return fallback
    return fallback


def fallback_intent(user_input: str) -> dict[str, Any]:
    text = user_input.lower()
    intent = "query"
    if any(word in text for word in ("数据库", "库", "database", "schema", "表", "table", "结构")):
        intent = "explore"
    if any(word in text for word in ("分析", "趋势", "统计", "排行", "占比")):
        intent = "analyze"
    if any(word in text for word in ("你好", "hello", "hi")):
        intent = "chat"
    return {"intent": intent, "entities": {}, "requires_context": intent != "chat"}


async def understand_node(state: AgentState) -> dict[str, Any]:
    prompt = UNDERSTAND_PROMPT.format(user_input=state["user_input"], summary=state.get("summary", ""))
    default = fallback_intent(state["user_input"])
    try:
        if not is_llm_configured():
            raise RuntimeError("DeepSeek API key is not configured")
        response = await get_llm().ainvoke(prompt)
        parsed = extract_json(response.content, default)
    except Exception:
        parsed = default
    return {"current_step": "understand", "parsed_intent": parsed}


def fallback_plan(state: AgentState) -> list[dict[str, Any]]:
    intent = state.get("parsed_intent") or {}
    entities = intent.get("entities") or {}
    schema_id = state.get("selected_schema_id")
    table = entities.get("table") or ""
    sql = entities.get("sql") or ""

    if intent.get("intent") == "chat":
        return []
    if not schema_id:
        return [{"tool": "list_databases", "args": {"keyword": entities.get("database", ""), "env_type": "test"}}]
    if intent.get("intent") == "explore":
        if table:
            return [{"tool": "describe_table", "args": {"schema_id": schema_id, "table_name": table}}]
        return [{"tool": "list_tables", "args": {"schema_id": schema_id}}]
    if sql:
        return [{"tool": "execute_sql", "args": {"schema_id": schema_id, "sql": sql}}]
    return []


async def plan_node(state: AgentState) -> dict[str, Any]:
    if state.get("execution_plan"):
        return {"current_step": "plan"}

    prompt = PLAN_PROMPT.format(
        user_input=state["user_input"],
        intent=json.dumps(state.get("parsed_intent") or {}, ensure_ascii=False),
        schema_id=state.get("selected_schema_id"),
        table_schemas=json.dumps(state.get("table_schemas") or {}, ensure_ascii=False),
        summary=state.get("summary", ""),
    )
    default = fallback_plan(state)
    try:
        if not is_llm_configured():
            raise RuntimeError("DeepSeek API key is not configured")
        response = await get_llm().ainvoke(prompt)
        plan = extract_json(response.content, default)
        if not isinstance(plan, list):
            plan = default
    except Exception:
        plan = default
    return {"current_step": "plan", "execution_plan": plan}


async def _invoke_tool(tool_name: str, args: dict[str, Any]) -> str:
    tools = {
        "execute_sql": execute_sql,
        "list_databases": list_databases,
        "list_tables": list_tables,
        "describe_table": describe_table,
    }
    if tool_name not in tools:
        return f"未知工具：{tool_name}"
    return await tools[tool_name].ainvoke(args)


async def act_node(state: AgentState) -> dict[str, Any]:
    plan = state.get("execution_plan") or []
    if not plan:
        return {"current_step": "finish"}

    current = plan[0]
    tool_name = current.get("tool", "")
    tool_args = current.get("args") or {}
    if (
        tool_name == "execute_sql"
        and needs_confirmation(tool_args.get("sql", ""))
        and state.get("confirmed_action") != current
    ):
        return {"current_step": "confirm", "needs_confirmation": True, "pending_action": current}

    call = ToolCall(tool=tool_name, args=tool_args, status="running")
    try:
        result = await _invoke_tool(tool_name, tool_args)
        call.result = result
        call.status = "completed"
    except Exception as exc:
        call.result = str(exc)
        call.status = "failed"

    return {
        "current_step": "act",
        "tool_calls": (state.get("tool_calls") or []) + [call],
        "execution_plan": plan[1:],
    }


async def reflect_node(state: AgentState) -> dict[str, Any]:
    tool_calls = state.get("tool_calls") or []
    if not tool_calls:
        return {"current_step": "finish"}

    last_call = tool_calls[-1]
    updates: dict[str, Any] = {"current_step": "continue" if state.get("execution_plan") else "finish"}

    if last_call.status == "failed":
        updates["current_step"] = "finish"
        return updates

    if last_call.tool == "list_databases" and last_call.result:
        databases = extract_json(last_call.result, [])
        if isinstance(databases, list) and len(databases) == 1:
            selected = databases[0]
            updates["selected_database"] = selected
            updates["selected_schema_id"] = selected.get("schemaId") or selected.get("schema_id")
    return updates


async def summarize_node(state: AgentState) -> dict[str, Any]:
    tool_calls = state.get("tool_calls") or []
    if state.get("needs_confirmation") or state.get("pending_action"):
        return {
            "current_step": "finish",
            "response": state.get("response", ""),
            "needs_confirmation": state.get("needs_confirmation", False),
        }

    if not tool_calls and (state.get("parsed_intent") or {}).get("intent") == "chat":
        response_text = "你好，我可以帮你探索数据库、生成 SQL、执行查询并分析结果。"
    else:
        results_summary = [
            {
                "tool": call.tool,
                "args": call.args,
                "status": call.status,
                "result": (call.result or "")[:2000],
            }
            for call in tool_calls
        ]
        prompt = SUMMARIZE_RESPONSE_PROMPT.format(
            results_summary=json.dumps(results_summary, ensure_ascii=False, indent=2)
        )
        try:
            if not is_llm_configured():
                raise RuntimeError("DeepSeek API key is not configured")
            response = await get_llm().ainvoke(prompt)
            response_text = response.content
        except Exception:
            response_text = "\n\n".join(call.result or "" for call in tool_calls if call.result) or "没有可展示的结果。"

    new_summary = await update_summary(state.get("summary", ""), state["user_input"], response_text)
    return {"current_step": "finish", "response": response_text, "summary": new_summary}


async def confirm_node(state: AgentState) -> dict[str, Any]:
    pending = state.get("pending_action") or {}
    response = (
        "即将执行写操作，请确认：\n\n"
        f"操作类型：{pending.get('tool')}\n\n"
        f"参数：```json\n{json.dumps(pending.get('args', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        '输入 "确认执行" 继续，其他任意内容取消。'
    )
    return {"current_step": "finish", "response": response, "needs_confirmation": True}
