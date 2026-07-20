"""
HDCGenerator — column summary and table description generation using LLM.

Part of HDC (Hierarchical Data Context) bottom-up generation pipeline:
  1. Column summaries: vertical partitioning (6 columns per group), parallel LLM calls
  2. Table descriptions: one LLM call per table, parallel across tables

Single-table LLM failures are logged and skipped — they never abort the batch.

Task 2.4 adds: table relationship generation, database summary generation,
and the generate() orchestration method.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.datavault.models import ColumnRaw, ColumnSummary, TableDescription, TableRaw

logger = logging.getLogger(__name__)


class HDCGenerator:
    """Generate column summaries and table descriptions using LLM.

    Column summaries use vertical partitioning: columns are grouped into batches
    of 6, and all groups across all tables are sent in parallel via asyncio.gather.
    Table descriptions use one LLM call per table, also parallelized.

    The constructor accepts an optional AsyncOpenAI client for testability;
    if omitted, one is created lazily from Settings.

    Contract: Service
    Requirements: 1.2, 1.5
    """

    def __init__(self, llm_client: AsyncOpenAI | None = None) -> None:
        self._settings = get_settings()
        self._client = llm_client

    def _get_client(self) -> AsyncOpenAI:
        """Lazily create the AsyncOpenAI client if not injected."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._settings.llm_api_key,
                base_url=self._settings.llm_base_url,
            )
        return self._client

    # ═══════════════════════════════════════════════════════════════
    # Column Summary Generation
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _build_column_summary_prompt(
        table: TableRaw,
        column_group: list[ColumnRaw],
    ) -> str:
        """Build the LLM prompt for generating column descriptions."""
        lines: list[str] = [
            "你是一个数据库 schema 分析专家。请为以下表的每个字段生成简洁的业务含义描述。",
            "",
            f"表名: {table.name}",
        ]
        if table.comment:
            lines.append(f"表注释: {table.comment}")
        lines.append("")

        # Column details
        lines.append("字段信息:")
        for col in column_group:
            parts = [f"  - 字段名: {col.name}"]
            if col.data_type:
                parts.append(f"类型: {col.data_type}")
            parts.append(f"可空: {'YES' if col.nullable else 'NO'}")
            if col.key:
                key_label = {"PRI": "主键", "UNI": "唯一键", "MUL": "索引"}.get(
                    col.key, col.key
                )
                parts.append(f"键: {key_label}")
            if col.default:
                parts.append(f"默认值: {col.default}")
            if col.extra:
                parts.append(f"额外: {col.extra}")
            lines.append("; ".join(parts))
        lines.append("")

        # Sample data
        if table.sample_rows:
            lines.append("采样数据（最多 3 行）:")
            for i, row in enumerate(table.sample_rows, 1):
                row_parts = [
                    f"{col.name}={row.get(col.name, 'NULL')}"
                    for col in column_group
                ]
                lines.append(f"  行 {i}: {', '.join(row_parts)}")
            lines.append("")

        # Output format instruction
        lines.extend([
            "只输出 JSON 数组（不要 markdown 代码块标记），每个元素包含:",
            '  "column_name": 字段名（与输入完全一致）',
            '  "description": 业务含义描述（中文，简洁）',
            "",
            "示例格式:",
            '[{"column_name": "id", "description": "主键自增ID"}, '
            '{"column_name": "order_status", "description": "订单状态: 0待支付 1已支付 2已发货"}]',
        ])

        return "\n".join(lines)

    async def _generate_one_column_group(
        self,
        table: TableRaw,
        column_group: list[ColumnRaw],
    ) -> tuple[str, list[ColumnSummary]]:
        """Call LLM to generate column summaries for one group.

        Returns:
            Tuple of (table_name, list[ColumnSummary]).
        """
        client = self._get_client()
        prompt = self._build_column_summary_prompt(table, column_group)

        try:
            response = await client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            summaries = self._parse_column_summaries(content, column_group, table.name)
            return (table.name, summaries)
        except Exception as e:
            logger.error(
                "Column summary LLM call failed for table '%s', columns [%s]: %s",
                table.name,
                ", ".join(c.name for c in column_group),
                e,
            )
            return (table.name, [])

    @staticmethod
    def _parse_column_summaries(
        response_text: str,
        column_group: list[ColumnRaw],
        table_name: str,
    ) -> list[ColumnSummary]:
        """Parse LLM JSON response into ColumnSummary objects.

        Gracefully handles malformed responses by returning empty-summary
        fallbacks so that downstream table description generation still has
        full column coverage.
        """
        text = response_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse column summary JSON for table '%s': %s. "
                "Raw (first 300 chars): %.300s",
                table_name, e, text,
            )
            return HDCGenerator._fallback_column_summaries(column_group)

        if not isinstance(data, list):
            logger.warning(
                "Column summary response is not a JSON array for table '%s'. "
                "Raw (first 300 chars): %.300s",
                table_name, text,
            )
            return HDCGenerator._fallback_column_summaries(column_group)

        # Build a lookup from column name (lowercased) to ColumnRaw
        col_map: dict[str, ColumnRaw] = {}
        for c in column_group:
            col_map[c.name.lower()] = c

        summaries: list[ColumnSummary] = []
        seen: set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("column_name", "")).strip()
            if not name:
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())

            desc = str(item.get("description", "")).strip()
            raw_col = col_map.get(name.lower())
            summaries.append(ColumnSummary(
                column_name=name,
                description=desc,
                data_type=raw_col.data_type if raw_col else "",
                nullable=raw_col.nullable if raw_col else False,
                is_primary_key=(raw_col.key == "PRI") if raw_col else False,
            ))

        return summaries

    @staticmethod
    def _fallback_column_summaries(
        column_group: list[ColumnRaw],
    ) -> list[ColumnSummary]:
        """Create empty-summary fallbacks when LLM response is unparseable."""
        return [
            ColumnSummary(
                column_name=c.name,
                description="",
                data_type=c.data_type,
                nullable=c.nullable,
                is_primary_key=(c.key == "PRI"),
            )
            for c in column_group
        ]

    async def generate_column_summaries(
        self,
        tables: list[TableRaw],
    ) -> dict[str, list[ColumnSummary]]:
        """Generate column summaries for all tables using vertical partitioning.

        Columns are grouped in batches of 6. All batches across all tables are
        dispatched in parallel via asyncio.gather. Single-group failures are
        tolerated — the group is dropped and the remaining groups are aggregated.

        Args:
            tables: TableRaw objects to generate column summaries for.

        Returns:
            Dict mapping table_name -> list of ColumnSummary for that table.
            Tables where every group failed will be absent from the result.
        """
        # Collect all column-group tasks across all tables
        coros: list[asyncio.Future[tuple[str, list[ColumnSummary]]]] = []

        for table in tables:
            if not table.columns:
                continue
            for i in range(0, len(table.columns), 6):
                column_group = table.columns[i:i + 6]
                coros.append(
                    self._generate_one_column_group(table, column_group)
                )

        if not coros:
            logger.info("generate_column_summaries: no columns to process")
            return {}

        results = await asyncio.gather(*coros, return_exceptions=True)

        # Aggregate by table name
        table_summaries: dict[str, list[ColumnSummary]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Column summary task failed with unhandled exception: %s",
                    result,
                )
                continue
            table_name, summaries = result
            if table_name not in table_summaries:
                table_summaries[table_name] = []
            table_summaries[table_name].extend(summaries)

        succeeded = len(table_summaries)
        total = len(tables)
        logger.info(
            "generate_column_summaries: %d/%d tables succeeded",
            succeeded, total,
        )
        return table_summaries

    # ═══════════════════════════════════════════════════════════════
    # Table Description Generation
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _build_table_description_prompt(
        table: TableRaw,
        column_summaries: list[ColumnSummary],
    ) -> str:
        """Build the LLM prompt for generating a table description."""
        lines: list[str] = [
            "你是一个数据库 schema 分析专家。请根据以下表信息和字段描述，生成该表的业务描述。",
            "",
            f"表名: {table.name}",
        ]
        if table.comment:
            lines.append(f"表注释: {table.comment}")
        if table.engine:
            lines.append(f"存储引擎: {table.engine}")
        if table.row_count_estimate:
            lines.append(f"估计行数: {table.row_count_estimate}")
        lines.append("")

        # Column summaries
        if column_summaries:
            lines.append("已有字段描述:")
            for cs in column_summaries:
                prefix_parts: list[str] = []
                if cs.is_primary_key:
                    prefix_parts.append("PK")
                type_str = f"({cs.data_type})" if cs.data_type else ""
                prefix_parts.append(type_str)
                prefix = f" [{', '.join(p for p in prefix_parts if p)}]" if any(prefix_parts) else ""
                desc = f" — {cs.description}" if cs.description else ""
                lines.append(f"  - {cs.column_name}{prefix}{desc}")
            lines.append("")

        # Output format instruction
        lines.extend([
            "只输出 JSON 对象（不要 markdown 代码块标记），必须包含以下字段:",
            '  "main_entity": 核心业务实体，使用 / 分隔的同义词 '
            '(例如 "售后/退货/退款/换货"、"用户/客户/会员")',
            '  "table_type": "fact"(事实表)、"dimension"(维度表) 或 "bridge"(桥接表)',
            '  "primary_key": 主键字段名，复合主键用逗号分隔',
            '  "key_attributes": 最重要的 5 个业务属性字段名（数组）',
            '  "description": 表的业务描述（中文，1-3 句话）',
            "",
            "示例:",
            "{",
            '  "main_entity": "售后/退货/退款/换货",',
            '  "table_type": "fact",',
            '  "primary_key": "id",',
            '  "key_attributes": ["order_id", "user_id", "refund_amount", "status", "created_at"],',
            '  "description": "记录所有售后订单信息，包括退货、退款和换货流程的核心数据，'
            '是客服分析和退款追踪的主要数据来源"',
            "}",
        ])

        return "\n".join(lines)

    async def _generate_one_table_description(
        self,
        table: TableRaw,
        column_summaries: list[ColumnSummary],
    ) -> TableDescription | None:
        """Call LLM to generate description for a single table.

        Returns:
            TableDescription on success, or None if the LLM call fails.
            Requirement 1.5: failure is logged and the batch continues.
        """
        client = self._get_client()
        prompt = self._build_table_description_prompt(table, column_summaries)

        try:
            response = await client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            return self._parse_table_description(content, table)
        except Exception as e:
            logger.error(
                "Table description LLM call failed for table '%s': %s",
                table.name, e,
            )
            return None

    @staticmethod
    def _parse_table_description(
        response_text: str,
        table: TableRaw,
    ) -> TableDescription:
        """Parse LLM JSON response into a TableDescription object.

        Falls back to a skeleton description using table comment/name when the
        response cannot be parsed.
        """
        text = response_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse table description JSON for table '%s': %s. "
                "Raw (first 300 chars): %.300s",
                table.name, e, text,
            )
            return HDCGenerator._fallback_table_description(table)

        if not isinstance(data, dict):
            logger.warning(
                "Table description response is not a JSON object for table '%s'. "
                "Raw (first 300 chars): %.300s",
                table.name, text,
            )
            return HDCGenerator._fallback_table_description(table)

        table_type_raw = str(data.get("table_type", "fact")).lower().strip()
        if table_type_raw not in ("fact", "dimension", "bridge"):
            logger.warning(
                "Invalid table_type '%s' for table '%s', defaulting to 'fact'",
                table_type_raw, table.name,
            )
            table_type_raw = "fact"

        key_attrs = data.get("key_attributes", [])
        if not isinstance(key_attrs, list):
            key_attrs = []
        key_attrs = [str(a) for a in key_attrs[:5]]

        return TableDescription(
            table_name=table.name,
            main_entity=str(data.get("main_entity", "") or table.comment or table.name),
            table_type=table_type_raw,  # type: ignore[arg-type]
            primary_key=str(data.get("primary_key", "")),
            key_attributes=key_attrs,
            description=str(data.get("description", "") or table.comment or ""),
            row_count_estimate=table.row_count_estimate,
        )

    @staticmethod
    def _fallback_table_description(table: TableRaw) -> TableDescription:
        """Create a skeleton TableDescription when LLM response is unparseable."""
        return TableDescription(
            table_name=table.name,
            main_entity=table.comment or table.name,
            table_type="fact",
            primary_key="",
            key_attributes=[],
            description=table.comment or "",
            row_count_estimate=table.row_count_estimate,
        )

    async def generate_table_descriptions(
        self,
        tables: list[TableRaw],
        column_summaries: dict[str, list[ColumnSummary]],
    ) -> list[TableDescription]:
        """Generate table descriptions for all tables in parallel.

        One LLM call per table, dispatched concurrently via asyncio.gather.
        Single-table failures are logged and the table is omitted from results
        (Requirement 1.5).

        Args:
            tables: TableRaw objects to generate descriptions for.
            column_summaries: Pre-generated column summaries keyed by table name.

        Returns:
            List of successful TableDescription objects. Failed tables are absent.
        """
        coros: list[asyncio.Future[TableDescription | None]] = []

        for table in tables:
            summaries = column_summaries.get(table.name, [])

            async def _describe(t=table, s=summaries) -> TableDescription | None:
                return await self._generate_one_table_description(t, s)

            coros.append(asyncio.ensure_future(_describe()))

        if not coros:
            logger.info("generate_table_descriptions: no tables to process")
            return []

        results = await asyncio.gather(*coros, return_exceptions=True)

        descriptions: list[TableDescription] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Table description task failed with unhandled exception: %s",
                    result,
                )
                continue
            if result is not None:
                descriptions.append(result)

        succeeded = len(descriptions)
        total = len(tables)
        logger.info(
            "generate_table_descriptions: %d/%d tables succeeded",
            succeeded, total,
        )
        return descriptions

    # ═══════════════════════════════════════════════════════════════
    # Single-table entry point (used by HDCUpdater in task 4.1)
    # ═══════════════════════════════════════════════════════════════

    async def generate_table(
        self,
        table: TableRaw,
    ) -> TableDescription | None:
        """Generate column summaries + table description for a single table.

        Used by the incremental update path (HDCUpdater).
        Task 2.4's generate() method orchestrates the full batch pipeline.

        Returns:
            TableDescription on success, None if either phase fails.
        """
        col_map = await self.generate_column_summaries([table])
        summaries = col_map.get(table.name, [])
        if not summaries:
            logger.warning(
                "generate_table: no column summaries for table '%s'", table.name
            )
        return await self._generate_one_table_description(table, summaries)
