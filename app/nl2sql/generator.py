"""
SQL 生成器 — 基于表结构和用户问题，调用 LLM 生成 SQL

参考 DBAgent 的 app/nl2sql/generator.py
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import AsyncOpenAI

from app.config import get_settings
from app.nl2sql.schema import ColumnSchema, normalize_identifier_hint, schema_to_prompt


@dataclass
class GeneratedSQL:
    """LLM 生成的 SQL 结果"""

    sql: str
    explanation: str = ""
    used_columns: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    has_topn: bool = False  # 用户是否明确要求了 TopN（如"前10条"），工程层据此决定是否保留 SQL 中的 LIMIT


@dataclass
class EnrichmentContext:
    """注入 NL2SQL prompt 的富化上下文（来自 HDC 和 SQL 记忆）。

    通过 ContextVar 从 Agent 层传递到 NL2SQL 引擎层，
    不修改 LLM 可见的 query_database 工具 schema。
    """

    hdc_ctx: Any = None          # HDCContext (lazy-import 避免循环依赖)
    sql_memories: list[dict[str, Any]] = field(default_factory=list)
    hdc_column_budget: int = 1200    # HDC 列描述段字符预算
    sql_memory_budget: int = 1500    # SQL 记忆段字符预算


_nl2sql_enrichment: ContextVar[Optional[EnrichmentContext]] = ContextVar(
    "nl2sql_enrichment", default=None
)


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


_llm_client: Optional[AsyncOpenAI] = None


def _get_llm_client() -> Optional[AsyncOpenAI]:
    """获取 LLM 客户端（模块级懒加载单例，复用 HTTP 连接池）"""
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    _llm_client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
    return _llm_client


def _is_llm_configured() -> bool:
    """检查 LLM 是否已配置"""
    settings = get_settings()
    return bool(settings.llm_api_key)


# ── Enrichment helpers ──


def _build_hdc_column_map(
    enrichment: EnrichmentContext,
    table_name: str,
    budget: int = 1200,
) -> dict[str, str]:
    """从 HDC 上下文中提取指定表的列名→业务描述映射。

    匹配 table_name 对应的 HDCContext.matched_tables，
    解析 relevant_columns 条目（格式 "列名: 描述"）。

    返回空字典表示无 HDC 数据或无匹配表。
    """
    if enrichment.hdc_ctx is None:
        return {}

    matched_tables: list = getattr(enrichment.hdc_ctx, "matched_tables", []) or []
    table_names_lower = {t.strip().lower() for t in table_name.split(",")}

    col_map: dict[str, str] = {}
    total_chars = 0

    for tm in matched_tables:
        tm_name = getattr(tm, "table_name", "").lower()
        if tm_name not in table_names_lower:
            continue
        for col_entry in getattr(tm, "relevant_columns", []) or []:
            if ":" not in col_entry:
                continue
            col_name, _, description = col_entry.partition(": ")
            col_name = col_name.strip()
            desc = description.strip()
            entry_chars = len(col_name) + len(desc) + 4
            if total_chars + entry_chars > budget:
                break
            col_map[col_name.lower()] = desc
            total_chars += entry_chars

    return col_map


def _build_enriched_schema_lines(
    columns: list[ColumnSchema],
    hdc_column_map: dict[str, str],
) -> list[str]:
    """合并原始 DESCRIBE 行与 HDC 列业务描述。

    原始 DESCRIBE 行始终保留（唯一真实来源）。
    存在 HDC 匹配时追加 ``-- description`` 注释。
    """
    lines: list[str] = []
    for col in columns:
        raw_line = (
            f"- {col.name} {col.type} null={col.nullable} "
            f"key={col.key} default={col.default} extra={col.extra}"
        )

        # 提取裸列名（去掉多表前缀如 "order_record.id" → "id"）
        bare_name = col.name.split(".")[-1] if "." in col.name else col.name

        # 匹配：先精确匹配，再规范化匹配（处理驼峰/下划线变体）
        hdc_desc = hdc_column_map.get(bare_name.lower())
        if hdc_desc is None:
            hdc_desc = hdc_column_map.get(normalize_identifier_hint(bare_name))

        if hdc_desc:
            lines.append(f"{raw_line}  -- {hdc_desc}")
        else:
            lines.append(raw_line)

    return lines


def _build_sql_memory_section(
    enrichment: EnrichmentContext,
    budget: int = 1500,
) -> str:
    """构建 [历史相似查询参考] 段。

    过滤条件：
    - 仅安全 SQL（无 INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE）
    - 按相似度降序取 top-3
    - 超出字符预算时截断

    无可用记忆时返回空字符串。
    """
    memories = enrichment.sql_memories
    if not memories:
        return ""

    dangerous_kw = {
        "INSERT ", "UPDATE ", "DELETE ", "DROP ",
        "TRUNCATE ", "ALTER ", "CREATE ",
    }

    safe: list[dict] = []
    for m in memories:
        sql_upper = (m.get("sql_text", "") or "").upper()
        if any(kw in sql_upper for kw in dangerous_kw):
            continue
        safe.append(m)

    if not safe:
        return ""

    safe.sort(key=lambda m: m.get("similarity", 0), reverse=True)
    top = safe[:3]

    header = "[历史相似查询参考]\n"
    lines: list[str] = [header]
    total = len(header)

    for i, m in enumerate(top, 1):
        sql_text = m.get("sql_truncated", "") or m.get("sql_text", "") or ""
        if len(sql_text) > 300:
            sql_text = sql_text[:300] + "..."
        question = (m.get("question", "") or "")[:100]

        entry = f'{i}. 问题: "{question}"\n   SQL: {sql_text}\n'
        if total + len(entry) > budget:
            break
        lines.append(entry)
        total += len(entry)

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


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
    enrichment: Optional[EnrichmentContext] = None,
) -> str:
    """构建 SQL 生成的 prompt，可选注入 HDC 列描述和 SQL 历史记忆。"""

    # ── 构建表结构行（可选 HDC 富化）──
    hdc_header = ""
    hdc_column_map: dict[str, str] = {}

    if enrichment is not None and enrichment.hdc_ctx is not None:
        hdc_column_map = _build_hdc_column_map(
            enrichment, table_name, enrichment.hdc_column_budget
        )
        if hdc_column_map:
            enriched_lines = _build_enriched_schema_lines(columns, hdc_column_map)
            enriched_count = sum(1 for line in enriched_lines if "  --" in line)
            if enriched_count > 0:
                hdc_header = (
                    "[列业务语义 — 来自数据底座 "
                    f"(共 {enriched_count} 列有业务描述)]\n"
                    "以下表结构中，`--` 后的文字为业务端对该字段的语义描述：\n"
                )
                schema_lines_raw = "\n".join(enriched_lines)
            else:
                schema_lines_raw = schema_to_prompt(columns)
        else:
            schema_lines_raw = schema_to_prompt(columns)
    else:
        schema_lines_raw = schema_to_prompt(columns)

    # ── 构建 SQL 历史记忆段 ──
    sql_memory_section = ""
    if enrichment is not None:
        sql_memory_section = _build_sql_memory_section(
            enrichment, enrichment.sql_memory_budget
        )

    # ── 组装 prompt ──
    prompt_parts: list[str] = [
        "你是 MySQL 8 SQL 生成器。只基于给定 table_schema 生成只读 SQL。",
        "不得使用 table_schema 中不存在的字段，不得发明表名。只返回 JSON。",
        "",
        "硬性规则：",
        "1. 只生成单条 SELECT 或 WITH 查询，不生成 INSERT/UPDATE/DELETE/DDL。",
        "2. 不得翻译、意译或本地化枚举值。例如用户说\"在售商品\"，不能写 status = '在售'。过滤值应从用户明确输入的原始值或字段示例值中推理，没有来源时必须在 assumptions 中说明。",
        "3. 使用 MySQL 8 语法。窗口函数可以使用 ROW_NUMBER/RANK/DENSE_RANK，但聚合窗口场景应先在 CTE/子查询中完成聚合，再在外层做窗口排名。",
        "4. 聚合和 TopN 查询必须给出确定性 ORDER BY。排序指标相同时，尽量追加主键、维度字段或名称字段作为稳定 tie-breaker。",
        "5. 输出列尽量贴合用户问题，只返回回答问题必需的列；不要使用 SELECT *。",
        "6. **has_topn 仅当用户明确要求了具体条数时才设为 true**。如\"前10条\"\"TOP 5\"\"最近3条\"\"只看5条\"→true。用户只描述查询内容但未指定条数（如\"查询工单信息\"\"统计告警数量\"）时→false。不确定时一律 false。",
        "",
        f"用户问题：{question}",
        "",
        f"表名：{table_name}",
        "表结构：",
    ]
    if hdc_header:
        prompt_parts.append(hdc_header)
    prompt_parts.append(schema_lines_raw)
    prompt_parts.append("")
    if sql_memory_section:
        prompt_parts.append(sql_memory_section)
        prompt_parts.append("")
    prompt_parts.append(f"历史摘要：{summary}")
    prompt_parts.append("")
    prompt_parts.append("输出 JSON：")
    prompt_parts.append("""{{
  "sql": "SELECT ...",
  "has_topn": false,
  "explanation": "简短解释",
  "used_columns": ["..."],
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification_question": ""
}}""")

    return "\n".join(prompt_parts)


async def generate_sql(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    summary: str = "",
    schema_id: int | None = None,
    database: str = "",
    sample_values: dict[str, tuple[str, ...]] | None = None,
) -> GeneratedSQL:
    """
    根据自然语言问题生成 SQL。

    Args:
        question: 用户的自然语言问题
        table_name: 表名
        columns: 表结构（字段列表）
        summary: 对话历史摘要
        schema_id: 数据库 schema ID（保留，供未来扩展使用）
        database: 数据库名称（保留，供未来扩展使用）
        sample_values: 字段示例值（保留，供未来扩展使用）

    Returns:
        GeneratedSQL 对象
    """

    # 从 ContextVar 读取富化上下文（Runner 层设置，None 时优雅降级）
    enrichment = _nl2sql_enrichment.get(None)

    # 构建 prompt
    prompt = build_generate_sql_prompt(
        question,
        table_name,
        columns,
        summary,
        enrichment=enrichment,
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
        has_topn=bool(payload.get("has_topn", False)),
    )