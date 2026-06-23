from __future__ import annotations

import json

from app.agent.llm import get_llm, is_llm_configured
from app.nl2sql.schema import schema_to_prompt
from app.nl2sql.semantics import SemanticContext, SemanticRule, is_safe_semantic_sql_fragment, rule_columns_exist


def extract_json_object(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.removeprefix("json").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
    return {}


def build_semantic_parse_prompt(message: str, context: SemanticContext) -> str:
    return f"""你是业务语义口径解析器，只把用户的自然语言口径解析成结构化 JSON，不生成完整 SQL。

硬性约束：
1. 只返回 JSON，不要解释文本。
2. sql 只能是 SQL 条件片段或表达式，例如 `order_status IN ('paid', 'completed')` 或 `SUM(total_amount)`。
3. 不得返回 SELECT/INSERT/UPDATE/DELETE/DDL，不得返回多语句。
4. 只能使用给定表结构中的字段。
5. 枚举值必须来自用户原文、样例值或上下文候选；不能把中文枚举直接翻译成英文，除非用户原文明确给出英文值。
6. 如果无法确定字段或枚举值，返回 needs_clarification=true。

当前表：{", ".join(context.tables) or "未知"}
表结构：
{schema_to_prompt(list(context.columns))}

字段样例值：
{json.dumps(context.sample_values, ensure_ascii=False, indent=2)}

用户原始查询：
{context.user_input}

用户本轮口径说明：
{message}

输出 JSON：
{{
  "name": "业务词",
  "sql": "SQL 条件片段或表达式",
  "required_columns": ["..."],
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": ""
}}
"""


async def parse_custom_semantic_rule_with_llm(message: str, context: SemanticContext) -> SemanticRule | None:
    if not is_llm_configured():
        return None

    response = await get_llm().ainvoke(build_semantic_parse_prompt(message, context))
    payload = extract_json_object(response.content)
    if payload.get("needs_clarification"):
        return None

    name = str(payload.get("name") or "").strip()
    sql = str(payload.get("sql") or "").strip()
    if not name or not sql or not is_safe_semantic_sql_fragment(sql):
        return None

    required_columns = tuple(str(column) for column in payload.get("required_columns") or ())
    rule = SemanticRule(
        name=name,
        sql=sql,
        tables=context.tables,
        description=f"LLM 解析并由用户确认的业务口径：{name}",
        domain=context.domain,
        schema_ids=((context.schema_id,) if context.schema_id is not None else ()),
        source="user_confirmed_llm_parsed",
        required_columns=required_columns,
        confidence=float(payload.get("confidence", 0.0)),
        status="confirmed",
        requires_confirmation=False,
    )
    if rule.confidence < 0.8:
        return None
    if context.columns and not rule_columns_exist(rule, {column.name.lower() for column in context.columns}):
        return None
    return rule
