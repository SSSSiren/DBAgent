import json

from app.agent.llm import get_llm, is_llm_configured
from app.nl2sql.generator import GeneratedSQL, extract_json_object
from app.nl2sql.schema import ColumnSchema, schema_to_prompt

# 从 Deep Agents QUERY_CHECKER 借鉴的 10 类常见 SQL 错误检查清单，
# 注入 repair prompt 让 LLM 修复时有明确方向。
_SQL_ERROR_CHECKLIST = """Double check the MySQL query above for common mistakes, including:
- Using NOT IN with NULL values (NOT IN with a subquery that may return NULL causes the entire condition to be false)
- Using UNION when UNION ALL should have been used (UNION incurs an unnecessary sort to deduplicate)
- Using BETWEEN for exclusive ranges (BETWEEN is inclusive on both ends)
- Data type mismatch in predicates (e.g. comparing a string column to an unquoted number)
- Properly quoting identifiers with backticks (e.g. reserved words used as column names)
- Using the correct number of arguments for functions (e.g. SUBSTRING, DATE_FORMAT)
- Casting to the correct data type (CAST or CONVERT target type is compatible with source)
- Using the proper columns for JOIN conditions (ON clause references columns that exist in the joined tables)
- Missing GROUP BY for aggregate queries with non-aggregated columns (MySQL 8 ONLY_FULL_GROUP_BY)
- ORDER BY referencing columns not in SELECT or not valid for the query context"""


async def repair_sql(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    failed_sql: str,
    error_message: str,
    *,
    attempt: int = 1,
    previous_errors: list[str] | None = None,
) -> GeneratedSQL:
    """修复验证失败或执行失败的 SQL。

    基于表结构、原始问题、失败 SQL 和具体错误信息，
    调用 LLM 生成修正后的 SQL。支持多次重试时携带历史错误上下文。

    Args:
        question: 用户原始自然语言问题
        table_name: 目标表名
        columns: 表结构（字段列表）
        failed_sql: 验证失败或执行失败的 SQL
        error_message: 当前尝试的错误信息（来自 validator 或数据库）
        attempt: 当前尝试次数（1-based），用于 prompt 中的上下文标记
        previous_errors: 之前所有尝试的错误信息列表，帮助 LLM 避免重复犯错

    Returns:
        GeneratedSQL 对象，包含修复后的 SQL。
        修复失败时 needs_clarification=True。
    """
    if "permission" in error_message.lower() or "权限" in error_message:
        return GeneratedSQL(
            failed_sql,
            needs_clarification=True,
            clarification_question="当前查询失败可能与权限有关，请确认 OneDBA 权限。",
        )

    if not is_llm_configured():
        return GeneratedSQL(
            failed_sql,
            needs_clarification=True,
            clarification_question="DeepSeek API key 未配置，无法修复 SQL。",
        )

    # 构建历史失败上下文，避免 LLM 重复之前的错误方向
    previous_context = ""
    if previous_errors and len(previous_errors) > 0:
        previous_context = "## 之前尝试的修复记录（请避免重复这些错误）\n"
        for i, err in enumerate(previous_errors, 1):
            previous_context += f"- 第{i}次: {err}\n"
        previous_context += "\n"

    prompt = f"""你是 MySQL 8 SQL 修复器。请基于表结构、用户问题和错误信息修复只读 SQL，只返回 JSON。

{_SQL_ERROR_CHECKLIST}

用户问题：{question}

表名：{table_name}
表结构：
{schema_to_prompt(columns)}

失败 SQL：
{failed_sql}

错误信息（第{attempt}次尝试）：
{error_message}

{previous_context}
## 修复要求
1. 仔细分析错误信息，精准定位问题根因
2. 如果错误是"字段不存在"，检查字段名的下划线/驼峰/大小写
3. 如果错误涉及聚合/GROUP BY，确保非聚合列都在 GROUP BY 中
4. 如果错误涉及 JOIN，检查 ON 条件中的字段是否存在于对应表
5. **禁止**：将正确的 SQL 改错、引入新的语法错误、删除安全相关的 WHERE 条件

输出 JSON：
{{
  "sql": "SELECT ...",
  "explanation": "修复了 X 问题：...",
  "used_columns": ["..."],
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification_question": ""
}}"""
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
