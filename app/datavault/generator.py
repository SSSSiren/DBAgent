"""
HDCGenerator — column summary and table description generation using LLM.

Part of HDC (Hierarchical Data Context) bottom-up generation pipeline:
  1. Column summaries: vertical partitioning (6 columns per group), parallel LLM calls
  2. Table descriptions: one LLM call per table, parallel across tables
  3. Table relationships: two-stage detection (OpenViking coarse + LLM fine)
  4. Database summary: influence maximization (top 5 by relationship count)
  5. Full orchestration via generate()

Single-table LLM failures are logged and skipped — they never abort the batch.

Task 2.4 adds: table relationship generation, database summary generation,
and the generate() orchestration method.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.datavault.models import (
    ColumnRaw,
    ColumnSummary,
    DatabaseSummary,
    TableDescription,
    TableDescriptionWithColumns,
    TableRaw,
    TableRelationship,
)

if TYPE_CHECKING:
    from app.datavault.collector import SchemaCollector
    from app.datavault.uploader import HDCUploader

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

    def __init__(
        self,
        llm_client: AsyncOpenAI | None = None,
        collector: SchemaCollector | None = None,
        uploader: HDCUploader | None = None,
    ) -> None:
        self._settings = get_settings()
        self._client = llm_client
        self._collector = collector
        self._uploader = uploader

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

    # ═══════════════════════════════════════════════════════════════
    # LLM Helper
    # ═══════════════════════════════════════════════════════════════

    async def _chat_json(self, prompt: str) -> Any:
        """Make a single LLM chat completion call and return parsed JSON.

        Args:
            prompt: The user message to send to the LLM.

        Returns:
            Parsed JSON value (dict, list, etc.), or {} on failure.
        """
        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            return self._parse_json_response(content)
        except Exception as e:
            logger.error("_chat_json LLM call failed: %s", e)
            return {}

    @staticmethod
    def _parse_json_response(response_text: str) -> Any:
        """Parse LLM text into a JSON object, stripping markdown fences.

        Returns {} if parsing fails.
        """
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse JSON response: %s. Raw (first 300 chars): %.300s",
                e, text,
            )
            return {}

    # ═══════════════════════════════════════════════════════════════
    # Table Relationship Generation (Two-Stage)
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _build_table_desc_for_relationships(
        table_name: str,
        table_descriptions: list[TableDescription],
        column_summaries: dict[str, list[ColumnSummary]],
    ) -> str:
        """Build a one-table summary string for the relationship detection prompt."""
        desc = next((td for td in table_descriptions if td.table_name == table_name), None)
        cols = column_summaries.get(table_name, [])

        parts: list[str] = [f"表名: {table_name}"]
        if desc:
            parts.append(f"核心实体: {desc.main_entity}")
            parts.append(f"表类型: {desc.table_type}")
            parts.append(f"主键: {desc.primary_key}")
            if desc.description:
                parts.append(f"描述: {desc.description}")
        if cols:
            col_lines = [
                f"  - {c.column_name} ({c.data_type})" +
                (f" [PK]" if c.is_primary_key else "") +
                (f" — {c.description}" if c.description else "")
                for c in cols
            ]
            parts.append("字段:\n" + "\n".join(col_lines))

        return "\n".join(parts)

    @staticmethod
    def _build_relationship_prompt(
        source_table: str,
        target_table: str,
        source_desc: str,
        target_desc: str,
    ) -> str:
        """Build the LLM prompt for detecting a relationship between two tables."""
        return f"""你是一个数据库 schema 分析专家。请判断以下两个表之间是否存在关联关系。

{source_desc}

---

{target_desc}

---

请分析这两个表是否在业务上存在关联（通过外键、相同业务实体 ID、或业务逻辑上的引用关系），并输出一个 JSON 对象：

{{
  "has_relationship": true/false,
  "relationship_type": "one_to_one" / "one_to_many" / "many_to_many" （如果无关系则为空字符串）,
  "join_columns": [["source_column", "target_column"], ...] （可能的连接字段对，如果无关系则为空数组）,
  "confidence": 0.0-1.0（你对判断的信心程度，0=完全不确定，1=非常确定）,
  "description": "关系的中文描述（简短，1-2句话，如果无关系则为空字符串）"
}}

只输出 JSON 对象，不要 markdown 代码块标记。"""

    async def _stage1_coarse_candidates(
        self,
        database_name: str,
        table_name: str,
        table_descriptions: list[TableDescription],
    ) -> list[str]:
        """Stage 1: Use OpenViking find to get top 5 candidate tables for a source table.

        Uses the table's main_entity as a search query against the _tables directory
        for the given database, filtered to hdc_level:table tags and L0/L1 level.
        Returns up to 5 candidate table names (excluding the source table itself).
        """
        desc = next((td for td in table_descriptions if td.table_name == table_name), None)
        if desc is None:
            return []

        # Build search query from the table's main_entity and description
        query_parts = [desc.main_entity]
        if desc.description:
            query_parts.append(desc.description)
        query = " ".join(query_parts)

        target_uri = f"viking://resources/hdc/{database_name}/_tables"

        try:
            result = await self._uploader._ov.find(
                query=query,
                target_uri=target_uri,
                tags=["hdc_level:table"],
                level=[0, 1],
                limit=10,
            )
        except Exception as e:
            logger.warning(
                "Stage 1 find failed for table '%s': %s", table_name, e
            )
            return []

        # Extract candidate table names from find results
        candidates: list[str] = []
        items = result if isinstance(result, list) else result.get("items", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            # The find result's uri looks like .../hdc/{db}/_tables/{table_name}
            uri = item.get("uri", "")
            # Extract table name from the URI path
            parts = uri.rstrip("/").split("/")
            if parts:
                candidate_name = parts[-1]
                if candidate_name and candidate_name != table_name and candidate_name not in candidates:
                    candidates.append(candidate_name)

        # Limit to top 5
        return candidates[:5]

    async def _stage2_llm_fine_screening(
        self,
        database_name: str,
        source_table: str,
        candidate_tables: list[str],
        table_descriptions: list[TableDescription],
        column_summaries: dict[str, list[ColumnSummary]],
    ) -> list[TableRelationship]:
        """Stage 2: Use LLM to confirm join columns, relationship type, and confidence."""
        source_desc_text = self._build_table_desc_for_relationships(
            source_table, table_descriptions, column_summaries,
        )

        relationships: list[TableRelationship] = []

        for target_table in candidate_tables:
            target_desc_text = self._build_table_desc_for_relationships(
                target_table, table_descriptions, column_summaries,
            )
            prompt = self._build_relationship_prompt(
                source_table, target_table, source_desc_text, target_desc_text,
            )

            result = await self._chat_json(prompt)
            if not isinstance(result, dict) or not result:
                logger.warning(
                    "Stage 2 LLM returned invalid result for %s -> %s",
                    source_table, target_table,
                )
                continue

            has_rel = result.get("has_relationship", False)
            if not has_rel:
                continue

            # Validate and normalize relationship_type
            rel_type = str(result.get("relationship_type", "")).lower().strip()
            if rel_type not in ("one_to_one", "one_to_many", "many_to_many"):
                if "many" in rel_type:
                    rel_type = "many_to_many"
                elif "one" in rel_type:
                    rel_type = "one_to_one"
                else:
                    rel_type = "one_to_many"  # safe default

            # Parse join_columns
            join_cols_raw = result.get("join_columns", [])
            join_cols: list[tuple[str, str]] = []
            if isinstance(join_cols_raw, list):
                for pair in join_cols_raw:
                    if isinstance(pair, list) and len(pair) >= 2:
                        join_cols.append((str(pair[0]), str(pair[1])))

            # Parse confidence
            try:
                confidence = float(result.get("confidence", 0.5))
            except (ValueError, TypeError):
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))

            rel = TableRelationship(
                source_table=source_table,
                target_table=target_table,
                relationship_type=rel_type,
                join_columns=join_cols,
                confidence=confidence,
                description=str(result.get("description", "")),
            )
            relationships.append(rel)

        return relationships

    async def generate_relationships(
        self,
        database_name: str,
        table_descriptions: list[TableDescription],
        column_summaries: dict[str, list[ColumnSummary]] | None = None,
    ) -> list[TableRelationship]:
        """Generate table relationships using two-stage detection.

        Stage 1: OpenViking find coarse-screening — for each source table,
        find up to 5 candidate related tables.
        Stage 2: LLM fine-screening — confirm join_columns, relationship_type,
        and confidence for each candidate pair.

        Args:
            database_name: Target database name for OpenViking URI construction.
            table_descriptions: Pre-generated table descriptions.
            column_summaries: Pre-generated column summaries keyed by table name.

        Returns:
            List of detected TableRelationship objects.
        """
        if column_summaries is None:
            column_summaries = {}

        if not table_descriptions:
            logger.info("generate_relationships: no tables to relate")
            return []

        # Build a lookup of table_name -> TableDescription for fast access
        desc_map: dict[str, TableDescription] = {
            td.table_name: td for td in table_descriptions
        }

        # Process each table as a source, running Stage 1 in parallel
        async def _relate_one_source(source_table: str) -> list[TableRelationship]:
            if not self._uploader:
                logger.warning(
                    "generate_relationships: no uploader configured; "
                    "cannot run Stage 1 coarse screening"
                )
                return []

            # Stage 1: coarse candidates
            candidates = await self._stage1_coarse_candidates(
                database_name, source_table, table_descriptions,
            )
            if not candidates:
                return []

            # Stage 2: LLM fine screening
            return await self._stage2_llm_fine_screening(
                database_name, source_table, candidates,
                table_descriptions, column_summaries,
            )

        coros = [_relate_one_source(td.table_name) for td in table_descriptions]
        results = await asyncio.gather(*coros, return_exceptions=True)

        all_relationships: list[TableRelationship] = []
        seen_pairs: set[tuple[str, str]] = set()

        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Relationship generation task failed: %s", result
                )
                continue
            for rel in result:
                # Deduplicate: avoid A->B appearing twice when both tables are sources
                pair = (rel.source_table, rel.target_table)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    all_relationships.append(rel)

        logger.info(
            "generate_relationships: detected %d relationships across %d tables",
            len(all_relationships), len(table_descriptions),
        )
        return all_relationships

    # ═══════════════════════════════════════════════════════════════
    # Database Summary Generation (Influence Maximization)
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _build_database_summary_prompt(
        database_name: str,
        top_tables: list[tuple[TableDescription, int]],
    ) -> str:
        """Build the LLM prompt for generating a database summary.

        The prompt includes the top tables (by relationship count) with their
        main_entity, table_type, and description.
        """
        lines: list[str] = [
            "你是一个数据库架构分析专家。请根据以下数据库的核心表信息，推断该数据库的整体业务定位。",
            "",
            f"数据库名称: {database_name}",
            "",
            "核心表（按业务关联度排序）:",
        ]

        for td, rel_count in top_tables:
            lines.append(
                f"  - {td.table_name}: 实体={td.main_entity}, "
                f"类型={td.table_type}, 关联表数={rel_count}"
            )
            if td.description:
                lines.append(f"    描述: {td.description}")
        lines.append("")

        lines.extend([
            "只输出 JSON 对象（不要 markdown 代码块标记），包含以下字段:",
            '  "representative_entities": 该数据库包含的核心业务实体列表（3-8个，中文简称），'
            '例如 ["订单", "用户", "商品", "支付", "物流"]',
            '  "domain_hint": 业务域标识，例如 "电商交易域"、"客户管理域"、'
            '"供应链域"、"金融核心域"',
            '  "description": 数据库整体描述（中文，2-4句话），总结其业务范围和数据用途',
            "",
            "示例:",
            "{",
            '  "representative_entities": ["订单", "用户", "商品", "支付", "物流"],',
            '  "domain_hint": "电商交易域",',
            '  "description": "该数据库是电商平台的核心交易数据库，涵盖订单创建、支付处理、商品管理和物流配送等核心业务流程。主要用于交易分析、运营监控和业务决策支持。"',
            "}",
        ])

        return "\n".join(lines)

    async def generate_database_summary(
        self,
        database_name: str,
        table_descriptions: list[TableDescription],
        relationships: list[TableRelationship],
    ) -> DatabaseSummary:
        """Generate database-level summary using influence maximization.

        Counts relationships per table, selects the top 5 by relationship count
        (influence), then feeds them to the LLM to infer representative entities,
        domain hint, and a natural-language description.

        Args:
            database_name: Database name.
            table_descriptions: Pre-generated table descriptions.
            relationships: Pre-generated table relationships.

        Returns:
            DatabaseSummary with inferred entities, domain, and description.
        """
        # Count relationships per table (influence maximization)
        rel_count: dict[str, int] = defaultdict(int)
        for rel in relationships:
            rel_count[rel.source_table] += 1
            rel_count[rel.target_table] += 1

        # Sort tables by relationship count descending, pick top 5
        desc_map: dict[str, TableDescription] = {
            td.table_name: td for td in table_descriptions
        }
        sorted_tables = sorted(rel_count.items(), key=lambda x: x[1], reverse=True)
        top_5_names = [t[0] for t in sorted_tables[:5]]

        # If fewer than 5 tables have relationships, pad with other tables by name order
        if len(top_5_names) < min(5, len(table_descriptions)):
            remaining = [
                td.table_name for td in table_descriptions
                if td.table_name not in top_5_names
            ]
            top_5_names.extend(remaining[:5 - len(top_5_names)])

        top_tables: list[tuple[TableDescription, int]] = [
            (desc_map[name], rel_count.get(name, 0)) for name in top_5_names
        ]

        prompt = self._build_database_summary_prompt(database_name, top_tables)
        result = await self._chat_json(prompt)

        if isinstance(result, dict) and result:
            entities = result.get("representative_entities", [])
            if not isinstance(entities, list):
                entities = []
            entities = [str(e) for e in entities[:8]]

            return DatabaseSummary(
                database_name=database_name,
                representative_entities=entities,
                domain_hint=str(result.get("domain_hint", "")),
                description=str(result.get("description", "")),
                table_count=len(table_descriptions),
            )

        # Fallback: build a minimal summary from available data
        logger.warning(
            "Database summary LLM returned invalid result for '%s', using fallback",
            database_name,
        )
        entities = [td.main_entity.split("/")[0] for td in table_descriptions[:5]]
        return DatabaseSummary(
            database_name=database_name,
            representative_entities=entities,
            domain_hint="",
            description="",
            table_count=len(table_descriptions),
        )

    # ═══════════════════════════════════════════════════════════════
    # Full Orchestration: generate()
    # ═══════════════════════════════════════════════════════════════

    async def generate(
        self,
        schema_id: int,
        database_name: str,
    ) -> dict[str, Any]:
        """Orchestrate the full HDC generation pipeline.

        Pipeline order:
          1. collect_database → DatabaseRaw
          2. generate_column_summaries → dict[table_name, list[ColumnSummary]]
          3. generate_table_descriptions → list[TableDescription]
          4. generate_relationships → list[TableRelationship]
          5. generate_database_summary → DatabaseSummary
          6. upload_database → write to OpenViking

        Single-table failures are tolerated throughout (Requirement 1.5).
        The uploader step is optional — if no uploader is configured the
        pipeline completes up to step 5 and returns a stats dict without
        uploading.

        Args:
            schema_id: OneDBA schema ID.
            database_name: Database name for OpenViking URI.

        Returns:
            Stats dict:
            {
                "status": "completed" | "partial" | "failed",
                "tables_total": int,
                "tables_succeeded": int,
                "columns": int,
                "relationships": int,
                "duration_seconds": float,
                "errors": list[str],
            }
        """
        start_time = time.time()
        errors: list[str] = []

        # ── Step 1: Collect schema ──
        if not self._collector:
            return {
                "status": "failed",
                "tables_total": 0,
                "tables_succeeded": 0,
                "columns": 0,
                "relationships": 0,
                "duration_seconds": time.time() - start_time,
                "errors": ["No SchemaCollector configured"],
            }

        db_raw = await self._collector.collect_database(schema_id)
        tables = db_raw.tables
        tables_total = len(tables)
        if tables_total == 0:
            logger.warning("generate: no tables collected for schema_id=%d", schema_id)
            return {
                "status": "completed",
                "tables_total": 0,
                "tables_succeeded": 0,
                "columns": 0,
                "relationships": 0,
                "duration_seconds": time.time() - start_time,
                "errors": [],
            }

        # ── Step 2: Column summaries ──
        column_summaries: dict[str, list[ColumnSummary]] = {}
        try:
            column_summaries = await self.generate_column_summaries(tables)
        except Exception as e:
            error_msg = f"Column summary generation failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            # Continue with whatever we have — some groups may have succeeded

        total_columns = sum(len(cs) for cs in column_summaries.values())

        # ── Step 3: Table descriptions ──
        table_descriptions: list[TableDescription] = []
        try:
            table_descriptions = await self.generate_table_descriptions(
                tables, column_summaries,
            )
        except Exception as e:
            error_msg = f"Table description generation failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        tables_succeeded = len(table_descriptions)

        # ── Step 4: Table relationships ──
        relationships: list[TableRelationship] = []
        try:
            relationships = await self.generate_relationships(
                database_name, table_descriptions, column_summaries,
            )
        except Exception as e:
            error_msg = f"Relationship generation failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # ── Step 5: Database summary ──
        db_summary: DatabaseSummary | None = None
        try:
            db_summary = await self.generate_database_summary(
                database_name, table_descriptions, relationships,
            )
        except Exception as e:
            error_msg = f"Database summary generation failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # ── Step 6: Upload to OpenViking ──
        if self._uploader and db_summary:
            # Build TableDescriptionWithColumns for upload
            tables_with_cols: list[TableDescriptionWithColumns] = []
            for td in table_descriptions:
                cols = column_summaries.get(td.table_name, [])
                tables_with_cols.append(TableDescriptionWithColumns(
                    table_name=td.table_name,
                    main_entity=td.main_entity,
                    table_type=td.table_type,
                    primary_key=td.primary_key,
                    key_attributes=td.key_attributes,
                    description=td.description,
                    row_count_estimate=td.row_count_estimate,
                    columns=cols,
                ))

            try:
                await self._uploader.upload_database(
                    database_name, db_summary, tables_with_cols, relationships,
                )
            except Exception as e:
                error_msg = f"Upload failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # ── Determine final status ──
        if tables_succeeded == 0 and tables_total > 0:
            status = "failed"
        elif errors or tables_succeeded < tables_total:
            status = "partial"
        else:
            status = "completed"

        duration = time.time() - start_time
        stats: dict[str, Any] = {
            "status": status,
            "tables_total": tables_total,
            "tables_succeeded": tables_succeeded,
            "columns": total_columns,
            "relationships": len(relationships),
            "duration_seconds": round(duration, 2),
            "errors": errors,
        }

        logger.info(
            "generate: %s — %d/%d tables, %d columns, %d relationships, %.2fs",
            status, tables_succeeded, tables_total, total_columns,
            len(relationships), duration,
        )
        return stats
