"""
SDK Agent 执行器 — 基于 claude-agent-sdk 的 Agent 核心

这是整个项目的核心模块，替代 DBAgent 的 LangChain AgentExecutor + LangGraph。

职责：
1. 通过 claude-agent-sdk 的 query() 函数驱动 Agent 循环
2. 将 SDK 的类型化消息转换为 SSE 事件（step/sql/final）
3. 管理工具注册和调用
4. 收集观测指标

参考：
- DBAgent 的 app/agent/llm_agent.py（Agent 执行流程）
- SDK-DBAgent 的 demo/agent.py（SDK API 用法）
"""

import re
from typing import Any, AsyncIterator

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.context import build_context, update_session_state, extract_sql_from_text
from app.tools import TOOLS, get_tool_handler, TOOL_HANDLERS
from app.observation.langfuse import LangfuseObserver, extract_result_size


# ========== 工具适配层 ==========

# SDK MCP 工具执行结果队列。
# SDK 模式下工具在内部执行，ToolResultBlock 不出现在流式消息中。
# 通过在 SDK tool wrapper 中 push 结果到此队列，_run_with_sdk 消费队列
# 来合成 tool_end 事件，从而让 Langfuse 能记录完整的 tool input + output。
_tool_result_queue: list[tuple[str, str]] = []


def _push_tool_result(tool_name: str, result: str) -> None:
    """将工具执行结果推入队列（由 SDK tool wrapper 调用）"""
    _tool_result_queue.append((tool_name, result))


def _pop_tool_results() -> list[tuple[str, str]]:
    """取出队列中所有待消费的工具结果"""
    results = _tool_result_queue[:]
    _tool_result_queue.clear()
    return results

def _build_tool_schemas() -> list[dict[str, Any]]:
    """
    将内部工具定义转换为 SDK 兼容的 tool schema 格式。

    由于 claude-agent-sdk 的具体工具注册 API 可能变化，
    这里提供标准化的 tool schema，方便适配。
    """
    schemas = []
    for tool in TOOLS:
        schemas.append({
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        })
    return schemas


async def _execute_tool(name: str, input_data: dict[str, Any]) -> str:
    """
    执行工具调用。

    Args:
        name: 工具名称
        input_data: 工具参数

    Returns:
        工具执行结果（字符串）
    """
    handler = get_tool_handler(name)
    if handler is None:
        return f"未知工具: {name}"

    try:
        result = await handler(**input_data)
        return str(result)
    except TypeError as e:
        return f"工具参数错误: {e}"
    except Exception as e:
        return f"工具执行异常: {e}"


# ========== SDK 适配层 ==========

def _is_sdk_available() -> bool:
    """检查 claude-agent-sdk 是否可用"""
    try:
        import claude_agent_sdk  # noqa: F401
        return True
    except ImportError:
        return False


def _build_sdk_mcp_server():
    """
    使用 SDK 的 create_sdk_mcp_server() + @tool 装饰器，
    将 7 个 OneDBA 工具注册为进程内 MCP Server。

    工具名会带上 mcp__onedba__ 前缀，例如：
    - list_databases → mcp__onedba__list_databases
    """
    from claude_agent_sdk import tool, create_sdk_mcp_server

    # ---- 工具定义 ----
    @tool("list_databases", "列出当前用户有权限访问的数据库", {
        "keyword": str,
        "env_type": str,
    })
    async def list_databases_sdk(args):
        from app.tools.list_databases import list_databases
        result = await list_databases(
            keyword=args.get("keyword", ""),
            env_type=args.get("env_type", "test"),
        )
        _push_tool_result("list_databases", result)
        # print(f"list_databases_sdk: keyword='{args.get('keyword', '')}' env_type='{args.get('env_type', 'test')}' result={(result)}")
        return {"content": [{"type": "text", "text": result}]}

    @tool("select_database", "选择当前数据库", {
        "schema_id": int,
    })
    async def select_database_sdk(args):
        from app.tools.select_database import select_database
        result = await select_database(schema_id=args["schema_id"])
        _push_tool_result("select_database", result)
        return {"content": [{"type": "text", "text": result}]}

    @tool("list_tables", "列出指定数据库中的表", {
        "schema_id": int,
        "keyword": str,
    })
    async def list_tables_sdk(args):
        from app.tools.list_tables import list_tables
        result = await list_tables(
            schema_id=args["schema_id"],
            keyword=args.get("keyword", ""),
        )
        _push_tool_result("list_tables", result)
        # print(f"list_tables_sdk: schema_id={args['schema_id']} keyword='{args.get('keyword', '')}' result={(result)}")
        return {"content": [{"type": "text", "text": result}]}

    @tool("describe_table", "查看表结构（字段名、类型等）", {
        "schema_id": int,
        "table_name": str,
    })
    async def describe_table_sdk(args):
        from app.tools.describe_table import describe_table
        result = await describe_table(
            schema_id=args["schema_id"],
            table_name=args["table_name"],
        )
        _push_tool_result("describe_table", result)
        return {"content": [{"type": "text", "text": result}]}

    @tool("query_database", "自然语言查询数据库，自动生成并执行 SQL", {
        "schema_id": int,
        "question": str,
        "table_name": str,
        "summary": str,
    })
    async def query_database_sdk(args):
        from app.tools.query_database import query_database
        result = await query_database(
            schema_id=args["schema_id"],
            question=args["question"],
            table_name=args["table_name"],
            summary=args.get("summary", ""),
        )
        _push_tool_result("query_database", result)
        return {"content": [{"type": "text", "text": result}]}

    @tool("execute_sql", "直接执行 SQL 查询（只允许 SELECT/SHOW/DESCRIBE）", {
        "schema_id": int,
        "sql": str,
    })
    async def execute_sql_sdk(args):
        from app.tools.execute_sql import execute_sql
        result = await execute_sql(
            schema_id=args["schema_id"],
            sql=args["sql"],
        )
        _push_tool_result("execute_sql", result)
        return {"content": [{"type": "text", "text": result}]}

    @tool("ask_user", "向用户提问获取更多信息", {
        "question": str,
    })
    async def ask_user_sdk(args):
        from app.tools.ask_user import ask_user
        result = await ask_user(question=args["question"])
        _push_tool_result("ask_user", result)
        return {"content": [{"type": "text", "text": result}]}

    return create_sdk_mcp_server(
        name="onedba",
        version="1.0.0",
        tools=[
            list_databases_sdk,
            select_database_sdk,
            list_tables_sdk,
            describe_table_sdk,
            query_database_sdk,
            execute_sql_sdk,
            ask_user_sdk,
        ],
    )


async def _run_with_sdk(
    prompt: str,
    tool_schemas: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """
    使用 claude-agent-sdk 执行 Agent。

    通过 create_sdk_mcp_server() 注册 7 个 OneDBA 自定义工具。
    工具名带 mcp__onedba__ 前缀（如 mcp__onedba__list_databases）。

    产出格式统一的事件字典：
    {
        "type": "text" | "tool_start" | "tool_end" | "final",
        ...
    }
    """
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

    onedba_server = _build_sdk_mcp_server()
    tool_names = [f"mcp__onedba__{t['name']}" for t in tool_schemas]

    options = ClaudeAgentOptions(
        system_prompt=AGENT_SYSTEM_PROMPT,
        mcp_servers={"onedba": onedba_server},
        allowed_tools=tool_names,
        tools=[],  # 禁用所有内置工具（Bash/Read/Skill 等），只使用 MCP 自定义工具
        strict_mcp_config=True,  # 严格模式：只使用 mcp_servers 中传入的服务器
        permission_mode="acceptEdits",  # 自动批准 allowed_tools 中的工具（Docker 中不能用 bypassPermissions）
    )

    # 工具名映射
    prefix = "mcp__onedba__"
    # tool_use_id → short_name 映射，用于 tool_end 事件
    tool_name_map: dict[str, str] = {}

    def _short_name(raw: str) -> str:
        return raw[len(prefix):] if raw.startswith(prefix) else raw

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            # 聚合同一 message 内的所有 text block（SDK 流式分块）
            text_parts: list[str] = []
            for block in message.content:
                block_type = type(block).__name__

                # 文本块：先收集，不立即 yield
                if hasattr(block, "text") and block.text:
                    text_parts.append(block.text)

                # 工具调用块 (ToolUseBlock)
                elif block_type == "ToolUseBlock" or (hasattr(block, "name") and hasattr(block, "input")):
                    raw_name = block.name if hasattr(block, "name") else getattr(block, "tool", "unknown")
                    short_name = _short_name(raw_name)
                    tool_use_id = getattr(block, "id", "") or getattr(block, "tool_use_id", "")
                    if tool_use_id:
                        tool_name_map[tool_use_id] = short_name
                    yield {
                        "type": "tool_start",
                        "name": short_name,
                        "input": block.input if isinstance(block.input, dict) else (getattr(block, "input", {}) or {}),
                    }
                # 工具结果块 (ToolResultBlock)
                elif block_type == "ToolResultBlock" or hasattr(block, "tool_use_id"):
                    tool_use_id = getattr(block, "tool_use_id", "")
                    # 尝试从 content 中提取文本
                    content_blocks = getattr(block, "content", [])
                    if isinstance(content_blocks, list) and content_blocks:
                        result_text_parts = [c.get("text", "") for c in content_blocks if isinstance(c, dict)]
                        result_text = "\n".join(result_text_parts)
                    else:
                        result_text = str(content_blocks)

                    yield {
                        "type": "tool_end",
                        "name": tool_name_map.get(tool_use_id, "unknown"),
                        "tool_use_id": tool_use_id,
                        "content": result_text,
                    }

            # 聚合后 yield 一个完整的 text 事件（一个 AssistantMessage = 一次 LLM 推理）
            if text_parts:
                yield {
                    "type": "text",
                    "text": "".join(text_parts),
                }

            # SDK MCP 模式：工具在 SDK 内部执行，ToolResultBlock 不出现在流中。
            # SDK tool wrapper 已将结果推入 _tool_result_queue，在此消费队列
            # 合成 tool_end 事件，让 Langfuse 能记录完整的 tool input + output。
            for tool_name, result_text in _pop_tool_results():
                yield {
                    "type": "tool_end",
                    "name": tool_name,
                    "content": result_text,
                }

        elif isinstance(message, ResultMessage):
            # ResultMessage 字段：subtype, is_error, result, duration_ms, num_turns 等
            is_error = getattr(message, "is_error", False)
            subtype = getattr(message, "subtype", "completed")
            result_text = getattr(message, "result", "") or ""

            # 提取执行统计
            duration_ms = getattr(message, "duration_ms", 0) or 0
            num_turns = getattr(message, "num_turns", 0) or 0
            usage = getattr(message, "usage", None)
            token_count = 0
            if isinstance(usage, dict):
                token_count = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            stats = {
                "duration_ms": duration_ms,
                "num_turns": num_turns,
                "tokens": token_count,
            }

            # SDK 已知 bug: Claude Code CLI 正常完成时返回
            # is_error=True, subtype="success"。
            # 这不是真正的错误，当作正常完成处理。
            if is_error and subtype in ("success", "Success"):
                yield {
                    "type": "final",
                    "subtype": "completed",
                    "content": result_text or "(查询完成)",
                    "stats": stats,
                }
            elif is_error:
                yield {
                    "type": "final",
                    "subtype": "error",
                    "content": result_text or f"执行出错: {subtype}",
                    "stats": stats,
                }
            else:
                yield {
                    "type": "final",
                    "subtype": subtype,
                    "content": result_text,
                    "stats": stats,
                }


async def _run_with_openai_fallback(
    prompt: str,
    tool_schemas: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """
    当 claude-agent-sdk 不可用时，使用 OpenAI 兼容 API 作为 fallback。

    实现简单的 ReAct 循环：LLM 决策 → 工具执行 → 观察结果 → 继续决策
    """
    from openai import AsyncOpenAI
    from app.config import get_settings

    settings = get_settings()
    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # OpenAI 工具格式
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_schemas
    ]

    max_iterations = 15
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # 调用 LLM
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=openai_tools,
            temperature=0.1,
        )

        choice = response.choices[0]
        message = choice.message

        # 如果 LLM 决定调用工具
        if message.tool_calls:
            # 添加助手消息（含工具调用）。
            # 使用 model_dump() 保留 DeepSeek 返回的 signature 等额外字段，
            # 否则下一轮 LLM 调用会报 "Missing required field: 'signature'"。
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    tc.model_dump()
                    for tc in message.tool_calls
                ],
            })

            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    import json
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                # 通知工具调用开始
                yield {
                    "type": "tool_start",
                    "name": tool_name,
                    "input": tool_input,
                }

                # 执行工具
                result = await _execute_tool(tool_name, tool_input)

                # 通知工具调用完成
                yield {
                    "type": "tool_end",
                    "name": tool_name,
                    "content": result,
                }

                # 添加工具结果到消息历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            # 最终响应
            final_content = message.content or ""
            messages.append({
                "role": "assistant",
                "content": final_content,
            })
            yield {
                "type": "final",
                "subtype": "completed",
                "content": final_content,
            }
            return

    # 达到最大迭代次数
    yield {
        "type": "final",
        "subtype": "max_iterations",
        "content": "抱歉，查询过程中步骤过多，已自动停止。请尝试简化您的问题。",
    }


# ========== 事件流处理 ==========

def _extract_sql_from_tool_result(tool_name: str, content: str) -> str:
    """从工具结果中提取 SQL"""
    if tool_name in ("query_database", "execute_sql"):
        return extract_sql_from_text(content)
    return ""


def _extract_sql_from_tool_input(tool_name: str, input_data: dict[str, Any]) -> str:
    """从工具输入参数中提取 SQL"""
    if tool_name == "execute_sql":
        sql = input_data.get("sql", "")
        if sql:
            return sql.replace("\\n", " ").replace("\\r", "").strip()
    return ""




# ========== 主入口 ==========

async def run_agent_stream(
    user_input: str,
    session_state: dict[str, Any],
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    流式运行 Agent，产出 SSE 事件。

    这是 Agent 层的唯一对外接口，被 API 路由调用。

    事件类型：
        ("step", {"step": "tool:xxx", "status": "running/completed"})
        ("step", {"step": "thinking", "text": "..."})
        ("sql", {"sql": "SELECT ..."})
        ("final", {"response": "...", "updated_state": {...}})

    Args:
        user_input: 用户当前输入的消息
        session_state: 会话状态字典

    Yields:
        (event_type, data) 元组
    """
    session_id = session_state.get("session_id", "")

    # 0. 创建 Langfuse 观测器
    observer = LangfuseObserver(session_id=session_id, user_input=user_input)
    observer.start_trace("SDK-DBAgent-Chat")

    # 1. 构建上下文
    context = build_context(session_state)
    if context:
        full_prompt = f"{context}\n\n用户问题: {user_input}"
    else:
        full_prompt = user_input

    # 2. 构建工具 schema
    tool_schemas = _build_tool_schemas()

    # 3. 收集执行信息
    tool_calls_info: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    all_texts: list[str] = []

    # 4. 选择执行引擎
    # 优先使用 SDK 模式（需在 DBR conda 环境中运行，且 claude-agent-sdk 已安装）。
    # 可通过环境变量 AGENT_ENGINE=fallback 强制使用 OpenAI fallback 模式。
    # 默认使用 SDK 模式。SDK 不可用时直接报错，不再 fallback 到 OpenAI。
    if _is_sdk_available():
        event_stream = _run_with_sdk(full_prompt, tool_schemas)
    else:
        raise RuntimeError(
            "claude-agent-sdk 不可用，无法执行 Agent。"
            "请确认已安装 claude-agent-sdk 并处于正确的 conda 环境中。"
        )
    
    print("working...")

    final_response = ""
    final_stats: dict[str, Any] = {}

    try:
        async for event in event_stream:
            event_type = event.get("type", "")

            if event_type == "text":
                # LLM 推理文本
                text = event.get("text", "")
                all_texts.append(text)
                yield "step", {
                    "step": "thinking",
                    "status": "running",
                    "text": text,
                }
                # === Langfuse: 记录 LLM 推理 ===
                if len(all_texts) == 1:
                    # 第一次推理是 Agent 的初始分析，记录完整 prompt
                    observer.record_llm_call(
                        name="agent-reasoning",
                        input_data={"prompt": full_prompt[:500]},
                        output_data={"reasoning": text[:300]},
                    )
                else:
                    # 后续推理是工具观察后的再分析
                    observer.record_llm_call(
                        name="agent-reasoning",
                        output_data={"reasoning": text[:300]},
                    )

            elif event_type == "tool_start":
                # 工具调用开始
                tool_name = event.get("name", "unknown")
                step_key = f"tool_start:{tool_name}"
                if step_key not in seen_events:
                    seen_events.add(step_key)
                    yield "step", {
                        "step": f"tool:{tool_name}",
                        "status": "running",
                    }

                # 从工具输入中提取 SQL（用于 execute_sql_tool）
                tool_input = event.get("input", {})
                sql = _extract_sql_from_tool_input(tool_name, tool_input)
                if sql:
                    yield "sql", {"sql": sql}

                tool_calls_info.append({
                    "tool": tool_name,
                    "args": tool_input,
                    "result": None,
                })

                # === Langfuse: 记录工具调用（在 tool_start 而非 tool_end，
                # 因为 SDK MCP 模式下工具执行在 SDK 内部完成，不会产出 tool_end 事件）===
                observer.record_tool_call(
                    tool_name=tool_name,
                    input_data=tool_input,
                )

            elif event_type == "tool_end":
                # 工具调用完成
                tool_name = event.get("name", "unknown")
                content = event.get("content", "")
                step_key = f"tool_end:{tool_name}"
                if step_key not in seen_events:
                    seen_events.add(step_key)
                    yield "step", {
                        "step": f"tool:{tool_name}",
                        "status": "completed",
                    }

                # 从工具结果中提取 SQL
                sql = _extract_sql_from_tool_result(tool_name, content)
                if sql:
                    yield "sql", {"sql": sql}

                # 更新工具调用结果
                for tc in tool_calls_info:
                    if tc.get("tool") == tool_name and tc.get("result") is None:
                        tc["result"] = content
                        break

                # === Langfuse: 补充工具调用结果（fallback 模式有 tool_end 事件）===
                row_count, col_count = extract_result_size(content)
                observer.update_tool_result(
                    tool_name=tool_name,
                    output_data=content,
                    row_count=row_count,
                    col_count=col_count,
                )

            elif event_type == "final":
                # Agent 完成
                final_response = event.get("content", "")
                final_stats = event.get("stats", {})

    except Exception as e:
        error_msg = str(e)
        # SDK bug workaround: Claude Code CLI returns is_error=True with
        # subtype="success" on normal completion. The SDK wraps this as a
        # ProcessError with message "Claude Code returned an error result: success".
        # Treat it as a normal completion, not an error.
        if "error result: success" in error_msg or "error result: Success" in error_msg:
            # Normal completion — use collected text from stream
            if not final_response and all_texts:
                final_response = all_texts[-1]
        else:
            final_response = f"查询过程中发生错误：{error_msg}"
            print(f"[SDK Agent] Error: {error_msg}")

    # 5. 确保有最终响应
    if not final_response and all_texts:
        final_response = all_texts[-1]
    elif not final_response:
        final_response = "获取响应失败"

    # 6. 更新会话状态
    updated_state = update_session_state(
        session_state,
        user_input,
        final_response,
    )

    # === Langfuse: 写入最终指标 ===
    observer.flush(response=final_response)

    # 7. yield 最终事件
    yield "final", {
        "response": final_response,
        "updated_state": updated_state,
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": tool_calls_info,
        "stats": final_stats,
    }