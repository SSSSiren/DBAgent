"""
SQL 修复器 — 当 SQL 验证失败时，调用 LLM 修复 SQL

参考 DBAgent 的 app/nl2sql/repair.py
"""

from __future__ import annotations

from typing import Optional

from app.nl2sql.generator import (
    GeneratedSQL,
    EnrichmentContext,
    _extract_json_object,
    _call_llm,
    _nl2sql_enrichment,
    _build_enriched_schema_lines,
    _build_hdc_column_map,
    _build_sql_memory_section,
)
from app.nl2sql.schema import ColumnSchema, schema_to_prompt


def build_repair_sql_prompt(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    failed_sql: str,
    error_message: str,
    enrichment: Optional[EnrichmentContext] = None,
) -> str:
    """构建 SQL 修复 prompt，可选注入 HDC 列描述和 SQL 历史记忆。"""

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
        "你是 MySQL SQL 修复器。请基于表结构和错误信息修复只读 SQL，只返回 JSON。",
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
    prompt_parts.append(f"失败 SQL：\n{failed_sql}")
    prompt_parts.append("")
    prompt_parts.append(f"错误信息：\n{error_message}")
    prompt_parts.append("")
    prompt_parts.append("输出 JSON：")
    prompt_parts.append("""{
  "sql": "SELECT ...",
  "has_topn": false,
  "explanation": "修复原因",
  "used_columns": ["..."],
  "assumptions": ["..."],
  "needs_clarification": false,
  "clarification_question": ""
}""")

    return "\n".join(prompt_parts)


async def repair_sql(
    question: str,
    table_name: str,
    columns: list[ColumnSchema],
    failed_sql: str,
    error_message: str | list[str],
) -> GeneratedSQL:
    """
    修复验证失败的 SQL。

    Args:
        question: 原始用户问题
        table_name: 表名
        columns: 表结构
        failed_sql: 失败的 SQL
        error_message: 错误信息（字符串或列表）

    Returns:
        GeneratedSQL: 修复后的 SQL 结果
    """
    # 权限相关错误无法修复
    if isinstance(error_message, list):
        error_message = "; ".join(error_message)
    if "permission" in error_message.lower() or "权限" in error_message:
        return GeneratedSQL(
            failed_sql,
            needs_clarification=True,
            clarification_question="当前查询失败可能与权限有关，请确认 OneDBA 权限。",
        )

    # 从 ContextVar 读取富化上下文（Runner 层设置，None 时优雅降级）
    enrichment = _nl2sql_enrichment.get(None)
    prompt = build_repair_sql_prompt(
        question, table_name, columns, failed_sql, error_message,
        enrichment=enrichment,
    )
    response = await _call_llm(prompt)
    payload = _extract_json_object(response)
    return GeneratedSQL(
        sql=payload.get("sql", failed_sql),
        explanation=payload.get("explanation", ""),
        used_columns=payload.get("used_columns") or [],
        assumptions=payload.get("assumptions") or [],
        needs_clarification=bool(payload.get("needs_clarification", False)),
        clarification_question=payload.get("clarification_question", ""),
        has_topn=bool(payload.get("has_topn", False)),
    )