import json

from app.agent.llm import get_llm, is_llm_configured
from app.nl2sql.generator import GeneratedSQL, extract_json_object
from app.nl2sql.schema import ColumnSchema, schema_to_prompt


async def repair_sql(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    failed_sql: str,
    error_message: str,
) -> GeneratedSQL:
    if "permission" in error_message.lower() or "权限" in error_message:
        return GeneratedSQL(failed_sql, needs_clarification=True, clarification_question="当前查询失败可能与权限有关，请确认 OneDBA 权限。")

    if not is_llm_configured():
        return GeneratedSQL(failed_sql, needs_clarification=True, clarification_question="DeepSeek API key 未配置，无法修复 SQL。")

    prompt = f"""你是 MySQL SQL 修复器。请基于表结构和错误信息修复只读 SQL，只返回 JSON。

用户问题：{question}

表名：{table_name}
表结构：
{schema_to_prompt(columns)}

失败 SQL：
{failed_sql}

错误信息：
{error_message}

输出 JSON：
{{
  "sql": "SELECT ...",
  "explanation": "修复原因",
  "used_columns": ["..."],
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification_question": ""
}}
"""
    response = await get_llm().ainvoke(prompt)
    payload = extract_json_object(response.content)
    return GeneratedSQL(
        sql=payload.get("sql", failed_sql),
        explanation=payload.get("explanation", ""),
        used_columns=payload.get("used_columns") or [],
        assumptions=payload.get("assumptions") or [],
        needs_clarification=bool(payload.get("needs_clarification", False)),
        clarification_question=payload.get("clarification_question", ""),
    )
