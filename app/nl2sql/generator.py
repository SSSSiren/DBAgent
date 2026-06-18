import json
from dataclasses import dataclass, field

from app.agent.llm import get_llm, is_llm_configured
from app.nl2sql.intent import NL2SQLIntent
from app.nl2sql.schema import ColumnSchema, schema_to_prompt


@dataclass
class GeneratedSQL:
    sql: str
    explanation: str = ""
    used_columns: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""


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


async def generate_sql(intent: NL2SQLIntent, table_name: str, columns: list[ColumnSchema], summary: str = "") -> GeneratedSQL:
    prompt = f"""你是 MySQL SQL 生成器。只基于给定 table_schema 生成只读 SQL。
不得使用 table_schema 中不存在的字段，不得发明表名。只返回 JSON。

用户意图：
{json.dumps(intent.__dict__, ensure_ascii=False)}

表名：{table_name}
表结构：
{schema_to_prompt(columns)}

历史摘要：{summary}

输出 JSON：
{{
  "sql": "SELECT ...",
  "explanation": "简短解释",
  "used_columns": ["..."],
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification_question": ""
}}
"""
    if not is_llm_configured():
        return GeneratedSQL("", needs_clarification=True, clarification_question="DeepSeek API key 未配置，无法生成 SQL。")

    response = await get_llm().ainvoke(prompt)
    payload = extract_json_object(response.content)
    return GeneratedSQL(
        sql=payload.get("sql", ""),
        explanation=payload.get("explanation", ""),
        used_columns=payload.get("used_columns") or [],
        assumptions=payload.get("assumptions") or [],
        needs_clarification=bool(payload.get("needs_clarification", False)),
        clarification_question=payload.get("clarification_question", ""),
    )
