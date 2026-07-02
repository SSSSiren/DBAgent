"""
SQL 生成器 — 基于表结构和用户问题，调用 LLM 生成 SQL

参考 DBAgent 的 app/nl2sql/generator.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import AsyncOpenAI

from app.config import get_settings
from app.nl2sql.schema import ColumnSchema, schema_to_prompt
from app.nl2sql.semantics import (
    SemanticContext,
    SemanticProvider,
    render_semantic_candidates_for_prompt,
    render_semantic_rules_for_prompt,
    resolve_semantics,
)


@dataclass
class GeneratedSQL:
    """LLM 生成的 SQL 结果"""

    sql: str
    explanation: str = ""
    used_columns: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""


def _extract_json_object(content: str) -> dict[str, Any]:
    """从 LLM 响应中提取 JSON 对象"""
    content = content.strip()
    # 去除 markdown 代码块
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


def _get_llm_client() -> Optional[AsyncOpenAI]:
    """获取 LLM 客户端"""
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


def _is_llm_configured() -> bool:
    """检查 LLM 是否已配置"""
    settings = get_settings()
    return bool(settings.llm_api_key)


async def _call_llm(prompt: str) -> str:
    """调用 LLM 并返回响应文本，失败时返回友好的错误 JSON"""
    client = _get_llm_client()
    if client is None:
        return "{}"
    settings = get_settings()
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return response.choices[0].message.content or "{}"
    except Exception as e:
        error_str = str(e)
        if "402" in error_str or "Insufficient Balance" in error_str:
            raise RuntimeError(
                "LLM API 余额不足，无法生成 SQL。请充值 DeepSeek 账户或更换 API Key。"
            ) from e
        if "401" in error_str or "Invalid API Key" in error_str.lower():
            raise RuntimeError(
                "LLM API Key 无效，请检查 .env 中的 LLM_API_KEY 配置。"
            ) from e
        if "429" in error_str or "Rate limit" in error_str:
            raise RuntimeError(
                "LLM API 调用频率超限，请稍后重试。"
            ) from e
        raise


def build_generate_sql_prompt(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    summary: str = "",
    semantic_rules: list | None = None,
    semantic_candidates: list | None = None,
) -> str:
    """构建 SQL 生成的 prompt"""
    rendered_rules = render_semantic_rules_for_prompt(semantic_rules)
    rendered_candidates = render_semantic_candidates_for_prompt(semantic_candidates)

    return f"""你是 MySQL 8 SQL 生成器。只基于给定 table_schema 生成只读 SQL。
不得使用 table_schema 中不存在的字段，不得发明表名。只返回 JSON。

硬性规则：
1. 只生成单条 SELECT 或 WITH 查询，不生成 INSERT/UPDATE/DELETE/DDL。
2. 不得翻译、意译或本地化枚举值。例如用户说"在售商品"，不能写 status = '在售'，应使用样例值或语义层给出的真实值。
3. 过滤值只能来自三类来源：用户明确输入的原始值、字段样例值、业务语义层规则。没有来源时必须在 assumptions 中说明，低置信时设置 needs_clarification=true。
4. 有效订单、GMV、支付成功、退款成功、在售商品等业务口径只能采用业务语义层提供的规则；语义层没有给出时不要自行编造。
5. 使用 MySQL 8 语法。窗口函数可以使用 ROW_NUMBER/RANK/DENSE_RANK，但聚合窗口场景应先在 CTE/子查询中完成聚合，再在外层做窗口排名。
6. 聚合和 TopN 查询必须给出确定性 ORDER BY。排序指标相同时，尽量追加主键、维度字段或名称字段作为稳定 tie-breaker。
7. 输出列尽量贴合用户问题，只返回回答问题必需的列；不要使用 SELECT *。
8. 只有用户明确要求 TopN（如"前10条"、"TOP 5"）时才加 LIMIT。

业务语义层规则：
{rendered_rules}

候选语义（未确认，不能直接用于 SQL）：
{rendered_candidates}

用户问题：{question}

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


async def generate_sql(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    summary: str = "",
    schema_id: int | None = None,
    database: str = "",
    semantic_domain: str = "",
    semantic_provider: SemanticProvider | None = None,
    sample_values: dict[str, tuple[str, ...]] | None = None,
) -> GeneratedSQL:
    """
    根据自然语言问题生成 SQL。

    Args:
        question: 用户的自然语言问题
        table_name: 表名
        columns: 表结构（字段列表）
        summary: 对话历史摘要
        schema_id: 数据库 schema ID
        database: 数据库名称
        semantic_domain: 语义域
        semantic_provider: 语义提供者
        sample_values: 字段示例值

    Returns:
        GeneratedSQL 对象
    """
    settings = get_settings()

    # 解析语义规则
    context = SemanticContext(
        schema_id=schema_id,
        database=database,
        domain=semantic_domain or settings.semantic_default_domain,
        tables=(table_name,),
        columns=tuple(columns),
        user_input=question,
        sample_values=sample_values or {},
    )
    semantic_resolution = await resolve_semantics(context, provider=semantic_provider)

    # 构建 prompt
    prompt = build_generate_sql_prompt(
        question,
        table_name,
        columns,
        summary,
        semantic_rules=list(semantic_resolution.rules),
        semantic_candidates=list(semantic_resolution.candidates),
    )

    if not _is_llm_configured():
        return GeneratedSQL(
            "",
            needs_clarification=True,
            clarification_question="LLM API key 未配置，无法生成 SQL。",
        )

    # 调用 LLM
    response = await _call_llm(prompt)
    payload = _extract_json_object(response)

    return GeneratedSQL(
        sql=payload.get("sql", ""),
        explanation=payload.get("explanation", ""),
        used_columns=payload.get("used_columns") or [],
        assumptions=payload.get("assumptions") or [],
        needs_clarification=bool(payload.get("needs_clarification", False)),
        clarification_question=payload.get("clarification_question", ""),
    )