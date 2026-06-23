# ============================================================================
# Agent 节点实现 — LangGraph 状态图的核心逻辑
# ============================================================================
# 这个文件实现了 LangGraph 状态图的所有节点函数：
#
# 核心节点（6个）：
#   - understand_node: 解析用户意图（调用 LLM）
#   - plan_node: 规划执行步骤（路由决策中心）
#   - act_node: 执行工具调用
#   - reflect_node: 反思执行结果，决定下一步
#   - summarize_node: 生成最终响应
#   - confirm_node: 等待用户确认写操作
#
# 辅助函数（大量）：
#   - JSON 解析和意图推断
#   - 追问分类和处理
#   - NL2SQL 查询执行（run_nl2sql_query）
#   - 追问查询执行（run_followup_query）
#   - 语义规则处理
#   - SQL 生成和校验
#
# 关键概念：
#   - 每个节点函数签名：async def xxx_node(state: AgentState) -> dict[str, Any]
#   - 节点返回一个 partial dict，LangGraph 自动合并到当前状态
#   - plan_node 是路由决策中心，决定走哪条路径（NL2SQL/追问/通用工具）
#   - act_node 通过 _invoke_tool 分发工具调用
# ============================================================================

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agent.llm import get_llm, is_llm_configured
from app.agent.prompts import PLAN_PROMPT, SUMMARIZE_RESPONSE_PROMPT, UNDERSTAND_PROMPT
from app.agent.state import AgentState, ToolCall
from app.client.onedba_client import onedba_client
from app.memory.summary import update_summary
from app.nl2sql.generator import GeneratedSQL, generate_sql
from app.nl2sql.intent import NL2SQLIntent, infer_time_days, parse_nl2sql_intent, parse_requested_limit
from app.nl2sql.repair import repair_sql
from app.nl2sql.resolver import resolve_database_candidate, resolve_table_candidate
from app.nl2sql.schema import ColumnSchema, parse_describe_result, schema_to_prompt
from app.nl2sql.semantic_parser import parse_custom_semantic_rule_with_llm
from app.nl2sql.semantics import (
    SemanticContext,
    confirm_semantic_rule,
    parse_custom_semantic_rule,
    render_semantic_candidates_for_prompt,
    resolve_semantics,
    save_user_semantic_rules,
    semantic_rule_from_pending,
)
from app.nl2sql.validator import validate_sql
from app.tools import describe_table, execute_sql, list_databases, list_tables, needs_confirmation
from app.tools.db_explorer import quote_identifier, sanitize_database_item
from app.tools.formatters import format_as_markdown_table


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


def infer_keyword(user_input: str) -> str:
    """Infer an ASCII database/table keyword from mixed Chinese input."""

    candidates = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", user_input)
    stop_words = {"select", "show", "desc", "describe", "from", "where", "limit"}
    for candidate in candidates:
        if candidate.lower() not in stop_words:
            return candidate
    return ""


def infer_table_name(user_input: str) -> str:
    """Infer a table name from phrases like 'xxx表' and normalize separators."""

    patterns = [
        r"数据库中\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*表",
        r"库中\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*表",
        r"([A-Za-z][A-Za-z0-9_\-\s]*?)\s*表",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if not match:
            continue
        table = re.sub(r"[\s\-]+", "_", match.group(1).strip())
        table = table.strip("_")
        if table:
            return table
    return ""


def infer_sql(user_input: str) -> str:
    """Build deterministic SQL for common data questions."""

    table = infer_table_name(user_input)
    if not table:
        return ""
    lower_input = user_input.lower()
    if "最多" in user_input:
        if "nodeid" in lower_input or "node_id" in lower_input:
            return f"SELECT nodeid, COUNT(*) AS cnt FROM {table} GROUP BY nodeid ORDER BY cnt DESC LIMIT 1"
        if "id" in lower_input:
            return f"SELECT id, COUNT(*) AS cnt FROM {table} GROUP BY id ORDER BY cnt DESC LIMIT 1"
    if "总数" in user_input or "多少" in user_input:
        return f"SELECT COUNT(*) AS total FROM {table}"
    if "最近" in user_input:
        return f"SELECT * FROM {table} LIMIT 10"
    return ""


def infer_select_database_keyword(user_input: str) -> str:
    patterns = [
        r"(?:使用|选择|切换到|切到)\s*([A-Za-z][A-Za-z0-9_-]*)\s*(?:数据库|库|实例)?",
        r"(?:把数据库设置为|设置数据库为)\s*([A-Za-z][A-Za-z0-9_-]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            return match.group(1)
    return ""


def infer_followup_database_keyword(user_input: str) -> str:
    patterns = [
        r"在\s*([A-Za-z][A-Za-z0-9_-]*)\s*实例上",
        r"用\s*([A-Za-z][A-Za-z0-9_-]*)\s*(?:实例|数据库|库)?",
        r"就\s*([A-Za-z][A-Za-z0-9_-]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            return match.group(1)
    return ""


def classify_followup(user_input: str, state: AgentState) -> dict[str, Any]:
    """Classify lightweight follow-up intents without executing them."""

    last_task = state.get("last_nl2sql_task")
    last_sql = state.get("last_validated_sql") or state.get("last_generated_sql")
    if not last_task and not last_sql:
        return {"is_followup": False, "type": "not_follow_up", "confidence": 0.0}

    text = user_input.strip()
    normalized = text.lower()
    if any(phrase in normalized for phrase in ("sql", "查询语句")) or any(
        phrase in text for phrase in ("把 SQL 给我", "给我 SQL", "看看 SQL", "刚才的 SQL", "执行的 SQL")
    ):
        return {
            "is_followup": True,
            "type": "show_sql",
            "confidence": 0.95,
            "patch": {"op": "show_sql"},
            "needs_clarification": False,
            "clarification_question": "",
        }

    limit = parse_requested_limit(text)
    if limit is not None and any(phrase in text for phrase in ("只看", "前", "最多", "排名前", "top", "Top")):
        return {
            "is_followup": True,
            "type": "change_limit",
            "confidence": 0.9,
            "patch": {"op": "replace_limit", "limit": limit},
            "needs_clarification": False,
            "clarification_question": "",
        }

    time_days = infer_time_days(text)
    if time_days is not None and any(phrase in text for phrase in ("改成", "换成", "最近", "只看")):
        if last_task and last_task.get("time_field"):
            needs_clarification = False
            question = ""
        else:
            needs_clarification = True
            question = "上一轮查询没有明确时间字段，请先说明要用哪个时间字段。"
        return {
            "is_followup": True,
            "type": "change_time_range",
            "confidence": 0.88,
            "patch": {"op": "replace_time_range", "time_range": {"type": "relative_days", "value": time_days}},
            "needs_clarification": needs_clarification,
            "clarification_question": question,
        }

    return {"is_followup": False, "type": "not_follow_up", "confidence": 0.0}


def _extract_table_names(result: dict[str, Any]) -> list[str]:
    columns = result.get("columnNames") or []
    rows = result.get("columnDatas") or []
    table_key = None
    for column in columns:
        title = str(column.get("title") or "")
        key = column.get("key") or column.get("field")
        if title.lower().startswith("tables_in_"):
            table_key = key
            break
    if not table_key and len(columns) > 1:
        table_key = columns[1].get("key") or columns[1].get("field")
    if not table_key:
        return []
    return [str(row.get(table_key)) for row in rows if row.get(table_key)]


def _fallback_generated_sql(intent: NL2SQLIntent, table_name: str, columns: list[ColumnSchema]) -> GeneratedSQL:
    column_names = {column.name.lower(): column.name for column in columns}
    normalized_columns = {re.sub(r"[^a-z0-9]", "", column.name.lower()): column.name for column in columns}
    field = ""
    for hint in intent.field_hints:
        normalized_hint = re.sub(r"[^a-z0-9]", "", hint.lower())
        if hint.lower() in column_names:
            field = column_names[hint.lower()]
            break
        if normalized_hint in normalized_columns:
            field = normalized_columns[normalized_hint]
            break
    time_field = ""
    for candidate in ("alert_time", "create_time", "gmt_create", "created_at"):
        if candidate in column_names:
            time_field = column_names[candidate]
            break
    if not field and intent.operation == "count":
        return GeneratedSQL(
            sql=f"SELECT COUNT(*) AS total FROM {table_name}",
            explanation="统计表记录总数。",
            assumptions=["使用 COUNT(*) 统计总数。"],
        )
    if field and intent.operation == "most_frequent":
        return GeneratedSQL(
            sql=f"SELECT {field}, COUNT(*) AS cnt FROM {table_name} GROUP BY {field} ORDER BY cnt DESC",
            explanation=f"按 {field} 分组统计出现次数，并按次数倒序返回。",
            used_columns=[field],
        )
    if field and intent.operation == "ranking_count":
        assumptions = []
        where_clause = ""
        if intent.time_days and time_field:
            where_clause = f" WHERE {time_field} >= DATE_SUB(NOW(), INTERVAL {intent.time_days} DAY)"
            assumptions.append(f"最近 {intent.time_days} 天使用字段 {time_field} 过滤。")
        elif intent.time_days:
            assumptions.append("用户指定了时间范围，但表结构中未找到高置信时间字段，未添加时间过滤。")
        return GeneratedSQL(
            sql=f"SELECT {field}, COUNT(*) AS cnt FROM {table_name}{where_clause} GROUP BY {field} ORDER BY cnt DESC",
            explanation=f"按 {field} 分组统计次数，并按次数倒序排行。",
            used_columns=[field, *([time_field] if time_field else [])],
            assumptions=assumptions,
        )
    if intent.operation == "recent":
        return GeneratedSQL(sql=f"SELECT * FROM {table_name}", explanation="查询表中的最近数据。")
    return GeneratedSQL(
        sql="",
        needs_clarification=True,
        clarification_question="无法基于当前问题和表结构确定要查询的字段，请补充字段或指标。",
    )


def _build_table_counts_sql(table_names: list[str]) -> str:
    selects = []
    for table_name in table_names:
        safe_literal = table_name.replace("'", "''")
        selects.append(f"SELECT '{safe_literal}' AS table_name, COUNT(*) AS total FROM {quote_identifier(table_name)}")
    return "\nUNION ALL\n".join(selects) + "\nORDER BY total DESC"


def _column_titles_and_keys(result: dict[str, Any]) -> tuple[list[str], list[str]]:
    columns = result.get("columnNames") or []
    titles = [str(column.get("title") or column.get("field") or column.get("key") or "") for column in columns]
    keys = [str(column.get("key") or column.get("field") or "") for column in columns]
    return titles, keys


def _result_summary(result: dict[str, Any], max_rows: int = 20) -> dict[str, Any]:
    titles, keys = _column_titles_and_keys(result)
    rows = result.get("columnDatas") or []
    top_rows = [
        {title: row.get(key) for title, key in zip(titles, keys) if key}
        for row in rows[:max_rows]
        if isinstance(row, dict)
    ]
    return {
        "row_count": len(rows),
        "columns": titles,
        "top_rows": top_rows,
        "empty": len(rows) == 0,
    }


def _resolve_field_hint(field_hint: str, columns: list[ColumnSchema]) -> str:
    normalized_hint = re.sub(r"[^a-z0-9]", "", field_hint.lower())
    for column in columns:
        if field_hint.lower() == column.name.lower():
            return column.name
    for column in columns:
        if normalized_hint == re.sub(r"[^a-z0-9]", "", column.name.lower()):
            return column.name
    return ""


def _infer_time_field(sql: str, columns: list[ColumnSchema]) -> str:
    lowered_sql = sql.lower()
    for column in columns:
        if column.name.lower() in lowered_sql and any(token in column.type.lower() for token in ("date", "time")):
            return column.name
    return ""


def _build_last_nl2sql_task(
    intent: NL2SQLIntent,
    schema_id: int,
    selected_database: dict[str, Any],
    table_name: str,
    columns: list[ColumnSchema],
    generated: GeneratedSQL,
    sql: str,
    assumptions: list[str],
) -> dict[str, Any]:
    dimension_field = ""
    for field in generated.used_columns or intent.field_hints:
        dimension_field = _resolve_field_hint(field, columns)
        if dimension_field:
            break
    time_field = _infer_time_field(sql, columns) if intent.time_days else ""
    where = []
    if intent.time_days and time_field:
        where.append(
            {
                "field": time_field,
                "operator": ">=",
                "value_type": "relative_days",
                "value": intent.time_days,
            }
        )
    select_fields = []
    group_by = []
    order_by = []
    if dimension_field:
        select_fields.append({"name": dimension_field, "role": "dimension"})
        if intent.operation in {"most_frequent", "ranking_count"}:
            group_by.append(dimension_field)
            select_fields.append({"name": "cnt", "role": "metric", "expression": "COUNT(*)"})
            order_by.append({"field": "cnt", "direction": "DESC"})
    elif intent.operation == "count":
        select_fields.append({"name": "total", "role": "metric", "expression": "COUNT(*)"})
    now = datetime.now(timezone.utc).isoformat()
    return {
        "task_id": str(uuid4()),
        "created_at": now,
        "updated_at": now,
        "user_question": intent.user_input,
        "database": {
            "schema_id": schema_id,
            "schema_name": selected_database.get("schemaName"),
            "instance_name": selected_database.get("instanceName"),
            "env": selected_database.get("env") or selected_database.get("envType"),
        },
        "table": {"name": table_name, "hint": intent.table_hint},
        "operation": intent.operation,
        "select_fields": select_fields,
        "where": where,
        "filters": [],
        "group_by": group_by,
        "order_by": order_by,
        "limit": intent.limit,
        "time_field": time_field,
        "table_schema": [column.__dict__ for column in columns],
        "sql": sql,
        "assumptions": assumptions,
    }


def _columns_from_task(task: dict[str, Any]) -> list[ColumnSchema]:
    return [ColumnSchema(**column) for column in task.get("table_schema") or [] if isinstance(column, dict)]


def _quote_sql_value(value: Any) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _render_task_where(where: list[dict[str, Any]]) -> list[str]:
    clauses = []
    for condition in where:
        field = condition.get("field")
        operator = condition.get("operator") or "="
        value_type = condition.get("value_type")
        value = condition.get("value")
        if not field:
            continue
        if value_type == "relative_days":
            clauses.append(f"{field} {operator} DATE_SUB(NOW(), INTERVAL {int(value)} DAY)")
        else:
            clauses.append(f"{field} {operator} {_quote_sql_value(value)}")
    return clauses


def _build_sql_from_task(task: dict[str, Any]) -> str:
    table_name = (task.get("table") or {}).get("name")
    if not table_name:
        return ""
    select_parts = []
    for field in task.get("select_fields") or []:
        expression = field.get("expression")
        name = field.get("name")
        if expression and name:
            select_parts.append(f"{expression} AS {name}")
        elif name:
            select_parts.append(str(name))
    if not select_parts:
        select_parts.append("*")

    clauses = [f"SELECT {', '.join(select_parts)} FROM {quote_identifier(str(table_name))}"]
    where_clauses = _render_task_where(task.get("where") or [])
    if where_clauses:
        clauses.append("WHERE " + " AND ".join(where_clauses))
    group_by = [str(field) for field in task.get("group_by") or [] if field]
    if group_by:
        clauses.append("GROUP BY " + ", ".join(group_by))
    order_by = [
        f"{item.get('field')} {item.get('direction', 'ASC')}"
        for item in task.get("order_by") or []
        if item.get("field")
    ]
    if order_by:
        clauses.append("ORDER BY " + ", ".join(order_by))
    if task.get("limit"):
        clauses.append(f"LIMIT {int(task['limit'])}")
    return " ".join(clauses)


def _apply_followup_patch(task: dict[str, Any], patch: dict[str, Any], user_input: str) -> dict[str, Any]:
    patched = json.loads(json.dumps(task))
    patched["updated_at"] = datetime.now(timezone.utc).isoformat()
    patched["user_question"] = user_input
    op = patch.get("op")
    if op == "replace_limit":
        patched["limit"] = int(patch["limit"])
    if op == "replace_time_range":
        time_field = patched.get("time_field")
        if not time_field:
            return patched
        days = int((patch.get("time_range") or {}).get("value"))
        replacement = {
            "field": time_field,
            "operator": ">=",
            "value_type": "relative_days",
            "value": days,
        }
        where = [
            condition
            for condition in patched.get("where") or []
            if not (condition.get("field") == time_field and condition.get("value_type") == "relative_days")
        ]
        patched["where"] = [*where, replacement]
    patched["sql"] = _build_sql_from_task(patched)
    return patched


def _nl2sql_result(
    content: str,
    steps: list[dict[str, Any]],
    sql: str = "",
    selected_schema_id: int | None = None,
    selected_database: dict[str, Any] | None = None,
    table_name: str = "",
    assumptions: list[str] | None = None,
    pending_nl2sql: dict[str, Any] | None = None,
    pending_semantic_confirmation: dict[str, Any] | None = None,
    last_nl2sql_task: dict[str, Any] | None = None,
    last_generated_sql: str = "",
    last_validated_sql: str = "",
    last_result_preview: list[dict[str, Any]] | None = None,
    last_result_summary: dict[str, Any] | None = None,
    followup_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "content": content,
        "steps": steps,
        "sql": sql,
        "selected_schema_id": selected_schema_id,
        "selected_database": selected_database,
        "table_name": table_name,
        "assumptions": assumptions or [],
        "pending_nl2sql": pending_nl2sql,
        "pending_semantic_confirmation": pending_semantic_confirmation,
        "last_nl2sql_task": last_nl2sql_task,
        "last_generated_sql": last_generated_sql,
        "last_validated_sql": last_validated_sql,
        "last_result_preview": last_result_preview or [],
        "last_result_summary": last_result_summary,
        "followup_patch": followup_patch,
    }


def _result_text(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("content") or result)
    return str(result or "")


def _should_return_tool_result_directly(call: ToolCall) -> bool:
    if not isinstance(call.result, dict):
        return False
    if call.tool not in {"nl2sql_query", "followup_query"}:
        return False
    if call.result.get("pending_nl2sql") or call.result.get("pending_semantic_confirmation"):
        return True
    steps = call.result.get("steps") or []
    return any(str(step.get("status")) == "needs_clarification" for step in steps if isinstance(step, dict))


def _infer_database_keyword_from_summary(summary: str) -> str:
    match = re.search(r"\b[A-Za-z][A-Za-z0-9_-]*-[A-Za-z0-9_-]*\b", summary)
    return match.group(0) if match else ""


async def run_select_database(keyword: str) -> dict[str, Any] | str:
    if not keyword:
        return "请提供要选择的数据库或实例关键词，例如：使用 dw-onedba-t1。"
    databases = await onedba_client.list_databases(keyword=keyword, env_type="test")
    database_resolution = resolve_database_candidate(databases, keyword)
    if database_resolution.needs_clarification:
        return database_resolution.question
    selected_database = sanitize_database_item(database_resolution.candidates[0])
    schema_id = int(database_resolution.value)
    content = (
        "已选择数据库：\n\n"
        f"- 数据库：`{selected_database.get('schemaName')}`\n"
        f"- 实例：`{selected_database.get('instanceName')}`\n"
        f"- Schema ID：`{schema_id}`\n\n"
        "后续查询如果不指定数据库，将默认使用该数据库。"
    )
    return {
        "content": content,
        "selected_schema_id": schema_id,
        "selected_database": selected_database,
    }


async def run_followup_query(
    user_input: str,
    followup: dict[str, Any],
    last_nl2sql_task: dict[str, Any] | None = None,
    last_validated_sql: str = "",
    last_generated_sql: str = "",
) -> dict[str, Any] | str:
    patch = followup.get("patch") or {}
    if followup.get("needs_clarification"):
        return _nl2sql_result(
            followup.get("clarification_question") or "这个追问需要进一步确认。",
            [{"name": "classify_followup", "status": "needs_clarification", "detail": followup.get("type", "")}],
            followup_patch=patch,
        )
    if followup.get("type") == "show_sql":
        sql = last_validated_sql or last_generated_sql
        if not sql:
            return "上一轮没有可返回的 SQL。"
        return _nl2sql_result(
            f"上一轮执行 SQL：\n\n```sql\n{sql}\n```",
            [{"name": "show_sql", "status": "completed", "detail": "返回上一轮 SQL"}],
            sql=sql,
            last_validated_sql=last_validated_sql,
            last_generated_sql=last_generated_sql,
            followup_patch=patch,
        )
    if not last_nl2sql_task:
        return "上一轮没有可追问的 NL2SQL 任务。"

    patched_task = _apply_followup_patch(last_nl2sql_task, patch, user_input)
    table_name = (patched_task.get("table") or {}).get("name") or ""
    columns = _columns_from_task(patched_task)
    sql = patched_task.get("sql") or ""
    if not table_name or not columns or not sql:
        return "上一轮任务信息不完整，无法应用追问。"

    steps = [
        {"name": "classify_followup", "status": "completed", "detail": followup.get("type", "")},
        {"name": "apply_patch", "status": "completed", "detail": patch.get("op", "")},
        {"name": "validate_sql", "status": "running", "detail": "只读/字段/LIMIT"},
    ]
    validation = validate_sql(sql, table_name, columns, default_limit=int(patched_task.get("limit") or 100))
    if not validation.passed:
        return "追问生成的 SQL 校验未通过：\n" + "\n".join(f"- {error}" for error in validation.errors)
    steps[-1] = {"name": "validate_sql", "status": "completed", "detail": "校验通过"}

    schema_id = int((patched_task.get("database") or {}).get("schema_id") or 0)
    if not schema_id:
        return "上一轮任务缺少 schema_id，无法执行追问。"
    steps.append({"name": "execute_sql", "status": "running", "detail": "followup"})
    result_raw = await onedba_client.execute_sql(schema_id=schema_id, sql=validation.sql)
    steps[-1] = {"name": "execute_sql", "status": "completed", "detail": "查询完成"}
    result_summary = _result_summary(result_raw)
    result_markdown = format_as_markdown_table(result_raw)
    assumptions = list(dict.fromkeys([*(patched_task.get("assumptions") or []), *validation.assumptions]))
    patched_task["sql"] = validation.sql
    patched_task["assumptions"] = assumptions
    selected_database = {
        "schemaName": (patched_task.get("database") or {}).get("schema_name"),
        "instanceName": (patched_task.get("database") or {}).get("instance_name"),
    }
    description = "已基于上一轮查询应用追问修改。"
    if patch.get("op") == "replace_limit":
        description = f"已将结果数量改为前 {patch.get('limit')} 条。"
    if patch.get("op") == "replace_time_range":
        description = f"已将时间范围改为最近 {(patch.get('time_range') or {}).get('value')} 天。"
    content = f"""### 追问查询结果

{description}

### 执行 SQL
```sql
{validation.sql}
```

### 查询结果
{result_markdown}
"""
    return _nl2sql_result(
        content,
        steps,
        sql=validation.sql,
        selected_schema_id=schema_id,
        selected_database=selected_database,
        table_name=table_name,
        assumptions=assumptions,
        last_nl2sql_task=patched_task,
        last_generated_sql=sql,
        last_validated_sql=validation.sql,
        last_result_preview=result_summary["top_rows"],
        last_result_summary=result_summary,
        followup_patch=patch,
    )


def semantic_confirmation_text(candidates: list[Any]) -> str:
    rendered = render_semantic_candidates_for_prompt(candidates)
    return f"""我识别到以下业务口径候选，但它们还没有被确认，不能直接用于生成 SQL：

{rendered}

如果这些口径正确，请回复“确认”或“记住”。确认后我会把它们保存到当前库表的语义记忆，并继续执行原查询。
如果不正确，请直接说明正确口径，例如：有效订单是 order_status IN ('paid', 'completed')。
"""


async def run_confirm_semantic_rules(pending: dict[str, Any]) -> dict[str, Any]:
    raw_context = pending.get("context") or {}
    context = SemanticContext(
        schema_id=raw_context.get("schema_id"),
        database=raw_context.get("database", ""),
        domain=raw_context.get("domain", ""),
        tables=tuple(raw_context.get("tables") or ()),
        columns=tuple(ColumnSchema(**column) for column in raw_context.get("columns") or ()),
        user_input=raw_context.get("user_input", ""),
    )
    rules = [
        confirm_semantic_rule(semantic_rule_from_pending(rule), context)
        for rule in pending.get("rules", [])
        if isinstance(rule, dict)
    ]
    save_user_semantic_rules(rules)
    names = "、".join(rule.name for rule in rules) or "业务口径"
    return {
        "content": f"已记住当前库表的语义规则：{names}。我会继续执行原查询。",
        "confirmed_semantic_rules": [rule.to_dict() for rule in rules],
    }


async def run_save_custom_semantic_rule(pending: dict[str, Any], message: str) -> dict[str, Any]:
    raw_context = pending.get("context") or {}
    context = SemanticContext(
        schema_id=raw_context.get("schema_id"),
        database=raw_context.get("database", ""),
        domain=raw_context.get("domain", ""),
        tables=tuple(raw_context.get("tables") or ()),
        columns=tuple(ColumnSchema(**column) for column in raw_context.get("columns") or ()),
        user_input=raw_context.get("user_input", ""),
    )
    rule = parse_custom_semantic_rule(message, context)
    if rule is None:
        rule = await parse_custom_semantic_rule_with_llm(message, context)
    if rule is None:
        return {
            "content": "没有识别到可保存的业务口径，或口径引用了当前表中不存在的字段。请用类似“有效订单其实是 order_status IN ('paid', 'completed')”的格式说明；如果只用自然语言描述，请包含明确字段或枚举值。",
            "custom_semantic_rule_failed": True,
        }
    save_user_semantic_rules([rule])
    return {
        "content": f"已按你的说明记住业务口径：{rule.name} = {rule.sql}。我会继续执行原查询。",
        "confirmed_semantic_rules": [rule.to_dict()],
    }


async def run_nl2sql_query(
    user_input: str,
    summary: str = "",
    selected_schema_id: int | None = None,
    selected_database: dict[str, Any] | None = None,
    database_keyword: str = "",
) -> str:
    steps: list[dict[str, Any]] = []
    intent = parse_nl2sql_intent(user_input)
    if not intent.is_query:
        return "该问题未识别为 NL2SQL 查询。"
    if not intent.database_keyword:
        intent.database_keyword = database_keyword or _infer_database_keyword_from_summary(summary)
    elif database_keyword:
        intent.database_keyword = database_keyword
    if not intent.table_hint and not intent.table_prefix:
        return "需要先明确要查询的表名。"

    if selected_schema_id:
        schema_id = int(selected_schema_id)
        selected_database = selected_database or {}
    else:
        if not intent.database_keyword:
            return "需要先明确数据库或实例关键词，或先在当前会话中选择一个数据库。"
        steps.append({"name": "resolve_database", "status": "running", "detail": intent.database_keyword})
        databases = await onedba_client.list_databases(keyword=intent.database_keyword, env_type="test")
        steps[-1] = {"name": "resolve_database", "status": "completed", "detail": f"候选 {len(databases)} 个"}
        database_resolution = resolve_database_candidate(databases, intent.database_keyword)
        if database_resolution.needs_clarification:
            return _nl2sql_result(
                database_resolution.question,
                steps,
                pending_nl2sql={"user_input": user_input},
            )
        schema_id = int(database_resolution.value)
        selected_database = sanitize_database_item(database_resolution.candidates[0])

    steps.append({"name": "list_tables", "status": "running", "detail": f"schema_id={schema_id}"})
    tables_raw = await onedba_client.execute_sql(schema_id=schema_id, sql="SHOW TABLES")
    table_names = _extract_table_names(tables_raw)
    steps[-1] = {"name": "list_tables", "status": "completed", "detail": f"{len(table_names)} 张表"}
    if intent.operation == "table_counts":
        prefix = intent.table_prefix
        matched_tables = [table for table in table_names if table.startswith(prefix)]
        if not matched_tables:
            return f"没有找到前缀为 `{prefix}` 的表。"
        sql = _build_table_counts_sql(matched_tables)
        steps.append({"name": "generate_sql", "status": "completed", "detail": "多表 COUNT UNION ALL"})
        steps.append({"name": "execute_sql", "status": "running", "detail": f"{len(matched_tables)} 张表"})
        result_raw = await onedba_client.execute_sql(schema_id=schema_id, sql=sql)
        steps[-1] = {"name": "execute_sql", "status": "completed", "detail": "查询完成"}
        result_markdown = format_as_markdown_table(result_raw)
        result_summary = _result_summary(result_raw)
        content = f"""### NL2SQL 查询结果

数据库：`{selected_database.get('schemaName')}` / 实例：`{selected_database.get('instanceName')}`
表名前缀：`{prefix}`

### 执行 SQL
```sql
{sql}
```

### SQL 说明
统计 `{prefix}` 前缀匹配到的 {len(matched_tables)} 张表分别有多少条数据，并按数据量倒序展示。

### 查询结果
{result_markdown}

### 假设与限制
- “approval 各个表”被解释为表名以 `approval` 开头的所有表。
"""
        return _nl2sql_result(
            content,
            steps,
            sql=sql,
            selected_schema_id=schema_id,
            selected_database=selected_database,
            assumptions=[f"表名前缀 `{prefix}` 匹配 {len(matched_tables)} 张表"],
            last_generated_sql=sql,
            last_validated_sql=sql,
            last_result_preview=result_summary["top_rows"],
            last_result_summary=result_summary,
        )

    steps.append({"name": "resolve_table", "status": "running", "detail": intent.table_hint})
    table_resolution = resolve_table_candidate(table_names, intent.table_hint)
    if table_resolution.needs_clarification:
        return table_resolution.question
    table_name = str(table_resolution.value)
    steps[-1] = {"name": "resolve_table", "status": "completed", "detail": table_name}

    steps.append({"name": "load_schema", "status": "running", "detail": table_name})
    describe_raw = await onedba_client.execute_sql(schema_id=schema_id, sql=f"DESCRIBE `{table_name}`")
    columns = parse_describe_result(describe_raw)
    if not columns:
        return f"已定位到表 {table_name}，但未能解析表结构，无法生成 SQL。"
    steps[-1] = {"name": "load_schema", "status": "completed", "detail": f"{len(columns)} 个字段"}

    if intent.operation == "field_count":
        column_markdown = "\n".join(f"- `{column.name}`: {column.type}" for column in columns)
        content = f"""### NL2SQL 查询结果

数据库：`{selected_database.get('schemaName')}` / 实例：`{selected_database.get('instanceName')}`
表：`{table_name}`

### 分析结论
`{table_name}` 表共有 **{len(columns)} 个字段**。

### 字段列表
{column_markdown}
"""
        return _nl2sql_result(
            content,
            steps,
            selected_schema_id=schema_id,
            selected_database=selected_database,
            table_name=table_name,
        )

    steps.append({"name": "generate_sql", "status": "running", "detail": intent.operation})
    if intent.operation == "ranking_count":
        generated = _fallback_generated_sql(intent, table_name, columns)
    else:
        semantic_context = SemanticContext(
            schema_id=schema_id,
            database=str(selected_database.get("schemaName") or ""),
            domain="",
            tables=(table_name,),
            columns=tuple(columns),
            user_input=intent.user_input,
        )
        semantic_resolution = await resolve_semantics(semantic_context)
        if semantic_resolution.candidates and not semantic_resolution.rules:
            return _nl2sql_result(
                semantic_confirmation_text(list(semantic_resolution.candidates)),
                steps,
                selected_schema_id=schema_id,
                selected_database=selected_database,
                table_name=table_name,
                pending_semantic_confirmation={
                    "context": {
                        "schema_id": schema_id,
                        "database": str(selected_database.get("schemaName") or ""),
                        "domain": "",
                        "tables": [table_name],
                        "columns": [column.__dict__ for column in columns],
                        "user_input": intent.user_input,
                    },
                    "rules": [rule.to_dict() for rule in semantic_resolution.candidates],
                    "resume": {
                        "user_input": user_input,
                        "summary": summary,
                        "selected_schema_id": schema_id,
                        "selected_database": selected_database,
                        "database_keyword": database_keyword,
                    },
                },
            )
        generated = await generate_sql(
            intent,
            table_name,
            columns,
            summary=summary,
            schema_id=schema_id,
            database=str(selected_database.get("schemaName") or ""),
        )
    if generated.needs_clarification:
        fallback = _fallback_generated_sql(intent, table_name, columns)
        generated = fallback if fallback.sql else generated
    if generated.needs_clarification or not generated.sql:
        return generated.clarification_question or "无法生成 SQL，请补充查询字段或筛选条件。"
    steps[-1] = {"name": "generate_sql", "status": "completed", "detail": generated.explanation or "SQL 已生成"}

    steps.append({"name": "validate_sql", "status": "running", "detail": "只读/字段/LIMIT"})
    validation = validate_sql(generated.sql, table_name, columns, default_limit=intent.limit or 100)
    if not validation.passed:
        return "SQL 校验未通过：\n" + "\n".join(f"- {error}" for error in validation.errors)
    steps[-1] = {"name": "validate_sql", "status": "completed", "detail": "校验通过"}

    sql = validation.sql
    execution_error = ""
    result_raw: dict[str, Any] | None = None
    repair_attempts = 0
    while repair_attempts <= 4:
        try:
            steps.append({"name": "execute_sql", "status": "running", "detail": f"attempt={repair_attempts + 1}"})
            result_raw = await onedba_client.execute_sql(schema_id=schema_id, sql=sql)
            steps[-1] = {"name": "execute_sql", "status": "completed", "detail": "查询完成"}
            execution_error = ""
            break
        except Exception as exc:
            steps[-1] = {"name": "execute_sql", "status": "failed", "detail": str(exc)}
            execution_error = str(exc)
            if repair_attempts >= 4:
                break
            repaired = await repair_sql(intent, table_name, columns, sql, execution_error)
            if repaired.needs_clarification or not repaired.sql:
                break
            repaired_validation = validate_sql(repaired.sql, table_name, columns, default_limit=intent.limit or 100)
            if not repaired_validation.passed:
                execution_error = "SQL 修复后校验未通过：" + "；".join(repaired_validation.errors)
                break
            sql = repaired_validation.sql
            generated.assumptions.extend(repaired.assumptions)
            generated.explanation = repaired.explanation or generated.explanation
            repair_attempts += 1

    if execution_error:
        return f"SQL 执行失败，已尝试修复 {repair_attempts} 次。\n\n错误：{execution_error}\n\nSQL：\n```sql\n{sql}\n```"

    result_markdown = format_as_markdown_table(result_raw or {})
    assumptions = list(dict.fromkeys([*generated.assumptions, *validation.assumptions]))
    result_summary = _result_summary(result_raw or {})
    last_nl2sql_task = _build_last_nl2sql_task(
        intent,
        schema_id,
        selected_database,
        table_name,
        columns,
        generated,
        sql,
        assumptions,
    )
    assumption_text = "\n".join(f"- {item}" for item in assumptions) if assumptions else "- 无"
    content = f"""### NL2SQL 查询结果

数据库：`{selected_database.get('schemaName')}` / 实例：`{selected_database.get('instanceName')}`
表：`{table_name}`

### 执行 SQL
```sql
{sql}
```

### SQL 说明
{generated.explanation or "基于用户问题和真实表结构生成 SQL。"}

### 查询结果
{result_markdown}

### 假设与限制
{assumption_text}
"""
    return _nl2sql_result(
        content,
        steps,
        sql=sql,
        selected_schema_id=schema_id,
        selected_database=selected_database,
        table_name=table_name,
        assumptions=assumptions,
        last_nl2sql_task=last_nl2sql_task,
        last_generated_sql=generated.sql,
        last_validated_sql=sql,
        last_result_preview=result_summary["top_rows"],
        last_result_summary=result_summary,
    )


async def understand_node(state: AgentState) -> dict[str, Any]:
    """
    理解节点 — 解析用户意图。

    执行流程：
    1. 构建 prompt，包含用户输入和历史摘要
    2. 调用 LLM 解析意图（返回 JSON）
    3. 如果 LLM 调用失败，使用规则兜底（fallback_intent）

    输出状态：
    - current_step: "understand"
    - parsed_intent: {"intent": "query/explore/analyze/chat", "entities": {...}, ...}

    注意：这个节点只是粗粒度意图分类，真正的 NL2SQL 细粒度解析在 plan_node 中完成。
    """
    # 构建 prompt，包含用户输入和历史摘要
    prompt = UNDERSTAND_PROMPT.format(user_input=state["user_input"], summary=state.get("summary", ""))

    # 规则兜底：如果 LLM 调用失败，用关键词匹配推断意图
    default = fallback_intent(state["user_input"])

    try:
        if not is_llm_configured():
            raise RuntimeError("DeepSeek API key is not configured")
        # 调用 LLM 解析意图
        response = await get_llm().ainvoke(prompt)
        # 从 LLM 输出中提取 JSON（支持 fenced code block 和裸 JSON）
        parsed = extract_json(response.content, default)
    except Exception:
        # LLM 调用失败时使用规则兜底
        parsed = default

    return {"current_step": "understand", "parsed_intent": parsed}


def fallback_plan(state: AgentState) -> list[dict[str, Any]]:
    """
    规则兜底的执行计划生成。

    当 LLM 调用失败时，根据意图和上下文用规则生成执行计划。
    这是一个简单的启发式逻辑，覆盖常见场景：
    - chat 意图：空计划（直接回复问候）
    - 没有选中数据库：先 list_databases，再 execute_sql
    - explore 意图：list_tables 或 describe_table
    - 有 SQL：直接 execute_sql
    """
    intent = state.get("parsed_intent") or {}
    entities = intent.get("entities") or {}
    schema_id = state.get("selected_schema_id")
    table = entities.get("table") or ""
    sql = entities.get("sql") or infer_sql(state["user_input"])

    if intent.get("intent") == "chat":
        return []
    if not schema_id:
        keyword = entities.get("database") or infer_keyword(state["user_input"])
        plan = [{"tool": "list_databases", "args": {"keyword": keyword, "env_type": "test"}}]
        if sql:
            plan.append({"tool": "execute_sql", "args": {"sql": sql}})
        return plan
    if intent.get("intent") == "explore":
        if table:
            return [{"tool": "describe_table", "args": {"schema_id": schema_id, "table_name": table}}]
        return [{"tool": "list_tables", "args": {"schema_id": schema_id}}]
    if sql:
        return [{"tool": "execute_sql", "args": {"schema_id": schema_id, "sql": sql}}]
    return []


def normalize_plan(state: AgentState, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    修补 LLM 生成的执行计划中常见的遗漏。

    LLM 生成的计划经常缺少参数（如 schema_id、keyword、sql），
    这个函数从上下文推断并补全这些参数，提高执行稳定性。

    修补规则：
    1. list_databases 缺少 keyword → 从用户输入推断
    2. list_tables/describe_table/execute_sql 缺少 schema_id → 从状态中补充
    3. execute_sql 缺少 sql → 从用户输入推断
    4. describe_table 缺少 table_name → 从用户输入推断
    5. 有 list_databases 但没有 execute_sql → 自动追加 execute_sql
    """

    intent = state.get("parsed_intent") or {}
    entities = intent.get("entities") or {}
    keyword = entities.get("database") or infer_keyword(state["user_input"])
    schema_id = state.get("selected_schema_id")
    inferred_sql = entities.get("sql") or infer_sql(state["user_input"])

    normalized = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        tool_name = step.get("tool")
        args = dict(step.get("args") or {})
        # 修补 list_databases 的 keyword 和 env_type
        if tool_name == "list_databases":
            args.setdefault("env_type", "test")
            if not args.get("keyword") and keyword:
                args["keyword"] = keyword
        # 修补需要 schema_id 的工具
        if tool_name in {"list_tables", "describe_table", "execute_sql"} and schema_id and not args.get("schema_id"):
            args["schema_id"] = schema_id
        # 修补 execute_sql 的 sql
        if tool_name == "execute_sql" and inferred_sql and not args.get("sql"):
            args["sql"] = inferred_sql
        # 修补 describe_table 的 table_name，或转换为 execute_sql
        if tool_name == "describe_table" and not args.get("table_name"):
            table_name = entities.get("table") or infer_table_name(state["user_input"])
            if inferred_sql:
                tool_name = "execute_sql"
                args = {"sql": inferred_sql, **({"schema_id": schema_id} if schema_id else {})}
            elif table_name:
                args["table_name"] = table_name
        normalized.append({"tool": tool_name, "args": args})
    # 如果有 list_databases 但没有 execute_sql，自动追加 execute_sql
    has_database_lookup = any(step.get("tool") == "list_databases" for step in normalized)
    has_sql_step = any(step.get("tool") == "execute_sql" for step in normalized)
    if has_database_lookup and inferred_sql and not has_sql_step:
        args = {"sql": inferred_sql}
        if schema_id:
            args["schema_id"] = schema_id
        normalized.append({"tool": "execute_sql", "args": args})
    return normalized


async def plan_node(state: AgentState) -> dict[str, Any]:
    """
    规划节点 — 路由决策中心。

    这是 Agent 最关键的节点，决定用户请求走哪条路径。
    按优先级从高到低判断：

    优先级 1：execution_plan 已存在（从确认流程回来）→ 直接返回
    优先级 2：选库续接 → pending_nl2sql + 用户指定了数据库 → nl2sql_query
    优先级 3：显式选库 → "使用 dw-onedba-t1" → select_database
    优先级 4：追问 → "把 SQL 给我" / "只看前 5 个" → followup_query
    优先级 5：NL2SQL 查询 → 识别到表名提示 → nl2sql_query
    优先级 6：兜底 → 调用 LLM 生成通用执行计划（探索类问题）

    输出状态：
    - current_step: "plan"
    - execution_plan: [{"tool": "...", "args": {...}}, ...]
    """
    # 优先级 1：如果 execution_plan 已存在（从确认流程回来），直接返回
    if state.get("execution_plan"):
        return {"current_step": "plan"}

    # 优先级 2：选库续接
    # 场景：用户之前问了问题，但多个数据库候选，现在用户指定了数据库
    # 例如：上一轮 Agent 问"请选择数据库"，用户说"在 onedba-t1 实例上找"
    pending_nl2sql = state.get("pending_nl2sql") or {}
    followup_database_keyword = infer_followup_database_keyword(state["user_input"])
    if pending_nl2sql and followup_database_keyword:
        return {
            "current_step": "plan",
            "execution_plan": [
                {
                    "tool": "nl2sql_query",
                    "args": {
                        "user_input": pending_nl2sql.get("user_input", state["user_input"]),
                        "summary": state.get("summary", ""),
                        "selected_schema_id": None,
                        "selected_database": None,
                        "database_keyword": followup_database_keyword,
                    },
                }
            ],
        }

    # 优先级 3：显式选库
    # 场景：用户说"使用 dw-onedba-t1"或"选择 xxx 数据库"
    select_database_keyword = infer_select_database_keyword(state["user_input"])
    if select_database_keyword:
        return {
            "current_step": "plan",
            "execution_plan": [{"tool": "select_database", "args": {"keyword": select_database_keyword}}],
        }

    # 优先级 4：追问
    # 场景：用户说"把 SQL 给我"、"只看前 5 个"、"改成最近 7 天"
    followup = classify_followup(state["user_input"], state)
    if followup.get("is_followup"):
        return {
            "current_step": "plan",
            "execution_plan": [
                {
                    "tool": "followup_query",
                    "args": {
                        "user_input": state["user_input"],
                        "followup": followup,
                        "last_nl2sql_task": state.get("last_nl2sql_task"),
                        "last_validated_sql": state.get("last_validated_sql", ""),
                        "last_generated_sql": state.get("last_generated_sql", ""),
                    },
                }
            ],
        }

    # 优先级 5：NL2SQL 查询
    # 场景：用户说"帮我查 xxx 表中出现最多的 yyy 是什么"
    # 通过 parse_nl2sql_intent 判断是否有表名提示
    nl2sql_intent = parse_nl2sql_intent(state["user_input"])
    if nl2sql_intent.is_query and (nl2sql_intent.table_hint or nl2sql_intent.table_prefix):
        return {
            "current_step": "plan",
            "execution_plan": [
                {
                    "tool": "nl2sql_query",
                    "args": {
                        "user_input": state["user_input"],
                        "summary": state.get("summary", ""),
                        "selected_schema_id": state.get("selected_schema_id"),
                        "selected_database": state.get("selected_database"),
                        "database_keyword": "",
                    },
                }
            ],
        }

    # 优先级 6：兜底 — 调用 LLM 生成通用执行计划
    # 场景：探索类问题（"有哪些库"、"有哪些表"、"表结构是什么"）
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
    return {"current_step": "plan", "execution_plan": normalize_plan(state, plan)}


async def _invoke_tool(tool_name: str, args: dict[str, Any]) -> str:
    """
    工具调用分发器 — 根据工具名称调用对应的工具函数。

    工具分为两类：
    1. 内置工具（LangChain Tool）：execute_sql, list_databases, list_tables, describe_table
    2. 合成工具（直接调用函数）：select_database, nl2sql_query, followup_query, 语义规则相关

    参数：
    - tool_name: 工具名称
    - args: 工具参数字典

    返回：
    - 工具执行结果（字符串或字典）
    """
    # 内置工具映射表（LangChain Tool 对象）
    tools = {
        "execute_sql": execute_sql,
        "list_databases": list_databases,
        "list_tables": list_tables,
        "describe_table": describe_table,
    }
    # 如果不是内置工具，检查是否是合成工具
    if tool_name not in tools:
        if tool_name == "select_database":
            return await run_select_database(args.get("keyword", ""))
        if tool_name == "nl2sql_query":
            return await run_nl2sql_query(
                args.get("user_input", ""),
                summary=args.get("summary", ""),
                selected_schema_id=args.get("selected_schema_id"),
                selected_database=args.get("selected_database"),
                database_keyword=args.get("database_keyword", ""),
            )
        if tool_name == "followup_query":
            return await run_followup_query(
                args.get("user_input", ""),
                args.get("followup", {}),
                last_nl2sql_task=args.get("last_nl2sql_task"),
                last_validated_sql=args.get("last_validated_sql", ""),
                last_generated_sql=args.get("last_generated_sql", ""),
            )
        if tool_name == "confirm_semantic_rules":
            return await run_confirm_semantic_rules(args.get("pending", {}))
        if tool_name == "save_custom_semantic_rule":
            return await run_save_custom_semantic_rule(args.get("pending", {}), args.get("message", ""))
        return f"未知工具：{tool_name}"
    # 调用内置工具
    return await tools[tool_name].ainvoke(args)


async def act_node(state: AgentState) -> dict[str, Any]:
    """
    执行节点 — 执行执行计划中的第一个工具调用。

    执行流程：
    1. 从 execution_plan 中取出第一个工具
    2. 检查是否需要用户确认（写操作场景）
    3. 调用 _invoke_tool 执行工具
    4. 创建 ToolCall 记录，追加到 tool_calls 列表
    5. 从 execution_plan 中移除已执行的工具
    6. 如果是 NL2SQL 相关工具，提取关键信息到状态

    输出状态：
    - current_step: "act"
    - tool_calls: 追加新的 ToolCall
    - execution_plan: 移除已执行的工具
    - selected_schema_id/selected_database: 如果工具返回了数据库信息
    - last_nl2sql_task/last_validated_sql 等: 如果工具返回了 NL2SQL 结果
    """
    # 获取执行计划
    plan = state.get("execution_plan") or []
    if not plan:
        return {"current_step": "finish"}

    # 取出第一个工具
    current = plan[0]
    tool_name = current.get("tool", "")
    tool_args = current.get("args") or {}

    # 检查是否需要用户确认（写操作场景）
    # 如果 SQL 是 UPDATE/DELETE/INSERT，需要用户确认
    if (
        tool_name == "execute_sql"
        and needs_confirmation(tool_args.get("sql", ""))
        and state.get("confirmed_action") != current  # 避免重复确认
    ):
        return {"current_step": "confirm", "needs_confirmation": True, "pending_action": current}

    # 创建 ToolCall 记录
    call = ToolCall(tool=tool_name, args=tool_args, status="running")
    try:
        # 调用工具
        result = await _invoke_tool(tool_name, tool_args)
        call.result = result
        call.status = "completed"
    except Exception as exc:
        call.result = str(exc)
        call.status = "failed"

    # 构建状态更新
    updates: dict[str, Any] = {
        "current_step": "act",
        "tool_calls": (state.get("tool_calls") or []) + [call],  # 追加新的 ToolCall
        "execution_plan": plan[1:],  # 移除已执行的工具
    }

    # 如果是 NL2SQL 相关工具，提取关键信息到状态
    if tool_name in {"nl2sql_query", "select_database", "followup_query"} and isinstance(call.result, dict):
        # 提取数据库上下文
        if call.result.get("selected_schema_id"):
            updates["selected_schema_id"] = call.result.get("selected_schema_id")
        if call.result.get("selected_database"):
            updates["selected_database"] = call.result.get("selected_database")
        # 提取待处理状态
        updates["pending_nl2sql"] = call.result.get("pending_nl2sql")
        updates["pending_semantic_confirmation"] = call.result.get("pending_semantic_confirmation")
        # 提取 NL2SQL 追问记忆
        for key in (
            "last_nl2sql_task",
            "last_generated_sql",
            "last_validated_sql",
            "last_result_preview",
            "last_result_summary",
            "followup_patch",
        ):
            if call.result.get(key):
                updates[key] = call.result.get(key)

    # 如果是语义规则确认工具，清除待确认状态
    if tool_name in {"confirm_semantic_rules", "save_custom_semantic_rule"}:
        updates["pending_semantic_confirmation"] = None
        # 如果保存失败，清空执行计划
        if isinstance(call.result, dict) and call.result.get("custom_semantic_rule_failed"):
            updates["execution_plan"] = []

    return updates


async def reflect_node(state: AgentState) -> dict[str, Any]:
    """
    反思节点 — 检查工具执行结果，决定下一步走向。

    执行流程：
    1. 获取最后一个 ToolCall
    2. 判断是否还有执行计划
    3. 如果工具执行失败，直接结束
    4. 如果是 list_databases 工具，提取选中的数据库信息，并为后续工具补充 schema_id
    5. 如果是 nl2sql_query 工具，提取数据库信息

    输出状态：
    - current_step: "continue"（还有工具要执行）或 "finish"（完成）
    - selected_schema_id/selected_database: 如果从 list_databases 或 nl2sql_query 提取到了
    - execution_plan: 为后续工具补充 schema_id
    """
    # 获取工具调用记录
    tool_calls = state.get("tool_calls") or []
    if not tool_calls:
        return {"current_step": "finish"}

    # 获取最后一个工具调用
    last_call = tool_calls[-1]
    # 判断是否继续：如果还有执行计划，返回 "continue"；否则返回 "finish"
    updates: dict[str, Any] = {"current_step": "continue" if state.get("execution_plan") else "finish"}

    # 如果工具执行失败，直接结束
    if last_call.status == "failed":
        updates["current_step"] = "finish"
        return updates

    # 如果是 list_databases 工具，提取选中的数据库信息
    if last_call.tool == "list_databases" and last_call.result:
        databases = extract_json(last_call.result, [])
        if isinstance(databases, list) and databases:
            # 默认选择第一个数据库
            selected = databases[0]
            updates["selected_database"] = selected
            schema_id = selected.get("schemaId") or selected.get("schema_id")
            updates["selected_schema_id"] = schema_id
            # 为后续工具补充 schema_id
            if schema_id and state.get("execution_plan"):
                remaining_plan = []
                for step in state.get("execution_plan") or []:
                    args = dict(step.get("args") or {})
                    if step.get("tool") in {"list_tables", "describe_table", "execute_sql"} and not args.get("schema_id"):
                        args["schema_id"] = schema_id
                    remaining_plan.append({"tool": step.get("tool"), "args": args})
                updates["execution_plan"] = remaining_plan

    # 如果是 nl2sql_query 工具，提取数据库信息
    if last_call.tool == "nl2sql_query" and isinstance(last_call.result, dict):
        schema_id = last_call.result.get("selected_schema_id")
        selected_database = last_call.result.get("selected_database")
        if schema_id:
            updates["selected_schema_id"] = schema_id
        if selected_database:
            updates["selected_database"] = selected_database

    return updates


async def summarize_node(state: AgentState) -> dict[str, Any]:
    """
    总结节点 — 生成最终响应。

    执行流程：
    1. 如果是确认场景，直接返回确认提示
    2. 如果是闲聊场景，返回问候语
    3. 如果是 NL2SQL 或追问，直接返回工具结果（已经是 Markdown 格式）
    4. 其他场景，调用 LLM 生成响应
    5. 更新摘要记忆

    输出状态：
    - current_step: "finish"
    - response: 最终响应文本（Markdown 格式）
    - summary: 更新后的摘要记忆
    """
    tool_calls = state.get("tool_calls") or []

    # 如果是确认场景，直接返回确认提示
    if state.get("needs_confirmation") or state.get("pending_action"):
        return {
            "current_step": "finish",
            "response": state.get("response", ""),
            "needs_confirmation": state.get("needs_confirmation", False),
        }

    # 如果是闲聊场景，返回问候语
    if not tool_calls and (state.get("parsed_intent") or {}).get("intent") == "chat":
        response_text = "你好，我可以帮你探索数据库、生成 SQL、执行查询并分析结果。"

    # 如果是 NL2SQL 或追问，直接返回工具结果（已经是 Markdown 格式）
    elif tool_calls and _should_return_tool_result_directly(tool_calls[-1]):
        response_text = _result_text(tool_calls[-1].result)

    # 其他场景，调用 LLM 生成响应
    else:
        # 构建工具调用摘要
        results_summary = [
            {
                "tool": call.tool,
                "args": call.args,
                "status": call.status,
                "result": _result_text(call.result)[:2000],  # 截断过长的结果
            }
            for call in tool_calls
        ]
        # 调用 LLM 生成响应
        prompt = SUMMARIZE_RESPONSE_PROMPT.format(
            results_summary=json.dumps(results_summary, ensure_ascii=False, indent=2)
        )
        try:
            if not is_llm_configured():
                raise RuntimeError("DeepSeek API key is not configured")
            response = await get_llm().ainvoke(prompt)
            response_text = response.content
        except Exception:
            # LLM 调用失败时，直接拼接工具结果
            response_text = "\n\n".join(_result_text(call.result) for call in tool_calls if call.result) or "没有可展示的结果。"

    # 更新摘要记忆
    new_summary = await update_summary(state.get("summary", ""), state["user_input"], response_text)
    return {"current_step": "finish", "response": response_text, "summary": new_summary}


async def confirm_node(state: AgentState) -> dict[str, Any]:
    """
    确认节点 — 等待用户确认写操作。

    当 act_node 检测到写操作（UPDATE/DELETE/INSERT）时，会设置 needs_confirmation=True，
    状态图路由到 confirm_node，生成确认提示。

    用户需要回复"确认执行"才能继续执行，其他任何输入都会取消操作。

    输出状态：
    - current_step: "finish"
    - response: 确认提示文本
    - needs_confirmation: True
    """
    pending = state.get("pending_action") or {}
    response = (
        "即将执行写操作，请确认：\n\n"
        f"操作类型：{pending.get('tool')}\n\n"
        f"参数：```json\n{json.dumps(pending.get('args', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        '输入 "确认执行" 继续，其他任意内容取消。'
    )
    return {"current_step": "finish", "response": response, "needs_confirmation": True}
