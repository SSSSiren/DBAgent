import json
import re
from typing import Any

from app.agent.llm import get_llm, is_llm_configured
from app.agent.prompts import PLAN_PROMPT, SUMMARIZE_RESPONSE_PROMPT, UNDERSTAND_PROMPT
from app.agent.state import AgentState, ToolCall
from app.client.onedba_client import onedba_client
from app.memory.summary import update_summary
from app.nl2sql.generator import GeneratedSQL, generate_sql
from app.nl2sql.intent import NL2SQLIntent, parse_nl2sql_intent
from app.nl2sql.repair import repair_sql
from app.nl2sql.resolver import resolve_database_candidate, resolve_table_candidate
from app.nl2sql.schema import ColumnSchema, parse_describe_result, schema_to_prompt
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


def _nl2sql_result(
    content: str,
    steps: list[dict[str, Any]],
    sql: str = "",
    selected_schema_id: int | None = None,
    selected_database: dict[str, Any] | None = None,
    table_name: str = "",
    assumptions: list[str] | None = None,
    pending_nl2sql: dict[str, Any] | None = None,
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
    }


def _result_text(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("content") or result)
    return str(result or "")


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
        generated = await generate_sql(intent, table_name, columns, summary=summary)
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
    )


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
    """Patch common LLM omissions before executing tools."""

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
        if tool_name == "list_databases":
            args.setdefault("env_type", "test")
            if not args.get("keyword") and keyword:
                args["keyword"] = keyword
        if tool_name in {"list_tables", "describe_table", "execute_sql"} and schema_id and not args.get("schema_id"):
            args["schema_id"] = schema_id
        if tool_name == "execute_sql" and inferred_sql and not args.get("sql"):
            args["sql"] = inferred_sql
        if tool_name == "describe_table" and not args.get("table_name"):
            table_name = entities.get("table") or infer_table_name(state["user_input"])
            if inferred_sql:
                tool_name = "execute_sql"
                args = {"sql": inferred_sql, **({"schema_id": schema_id} if schema_id else {})}
            elif table_name:
                args["table_name"] = table_name
        normalized.append({"tool": tool_name, "args": args})
    has_database_lookup = any(step.get("tool") == "list_databases" for step in normalized)
    has_sql_step = any(step.get("tool") == "execute_sql" for step in normalized)
    if has_database_lookup and inferred_sql and not has_sql_step:
        args = {"sql": inferred_sql}
        if schema_id:
            args["schema_id"] = schema_id
        normalized.append({"tool": "execute_sql", "args": args})
    return normalized


async def plan_node(state: AgentState) -> dict[str, Any]:
    if state.get("execution_plan"):
        return {"current_step": "plan"}

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

    select_database_keyword = infer_select_database_keyword(state["user_input"])
    if select_database_keyword:
        return {
            "current_step": "plan",
            "execution_plan": [{"tool": "select_database", "args": {"keyword": select_database_keyword}}],
        }

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
    tools = {
        "execute_sql": execute_sql,
        "list_databases": list_databases,
        "list_tables": list_tables,
        "describe_table": describe_table,
    }
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

    updates: dict[str, Any] = {
        "current_step": "act",
        "tool_calls": (state.get("tool_calls") or []) + [call],
        "execution_plan": plan[1:],
    }
    if tool_name in {"nl2sql_query", "select_database"} and isinstance(call.result, dict):
        if call.result.get("selected_schema_id"):
            updates["selected_schema_id"] = call.result.get("selected_schema_id")
        if call.result.get("selected_database"):
            updates["selected_database"] = call.result.get("selected_database")
        updates["pending_nl2sql"] = call.result.get("pending_nl2sql")
    return updates


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
        if isinstance(databases, list) and databases:
            selected = databases[0]
            updates["selected_database"] = selected
            schema_id = selected.get("schemaId") or selected.get("schema_id")
            updates["selected_schema_id"] = schema_id
            if schema_id and state.get("execution_plan"):
                remaining_plan = []
                for step in state.get("execution_plan") or []:
                    args = dict(step.get("args") or {})
                    if step.get("tool") in {"list_tables", "describe_table", "execute_sql"} and not args.get("schema_id"):
                        args["schema_id"] = schema_id
                    remaining_plan.append({"tool": step.get("tool"), "args": args})
                updates["execution_plan"] = remaining_plan
    if last_call.tool == "nl2sql_query" and isinstance(last_call.result, dict):
        schema_id = last_call.result.get("selected_schema_id")
        selected_database = last_call.result.get("selected_database")
        if schema_id:
            updates["selected_schema_id"] = schema_id
        if selected_database:
            updates["selected_database"] = selected_database
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
                "result": _result_text(call.result)[:2000],
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
            response_text = "\n\n".join(_result_text(call.result) for call in tool_calls if call.result) or "没有可展示的结果。"

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
