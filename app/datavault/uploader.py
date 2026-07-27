"""
HDCUploader — 将 HDC 内容写入 OpenViking 资源目录结构并设置结构化 tags。

目录结构：
    viking://resources/hdc/{schemaId}/{db}/                       # 数据库目录
    viking://resources/hdc/{schemaId}/{db}/_INDEX.md              # 数据库摘要
    viking://resources/hdc/{schemaId}/{db}/_tables/{table}/       # 表目录
    viking://resources/hdc/{schemaId}/{db}/_tables/{table}/_INDEX.md  # 表描述
    viking://resources/hdc/{schemaId}/{db}/_tables/{table}/_columns/{col}.md   # 列详情（独立子目录）
    viking://resources/hdc/{schemaId}/{db}/_relationships/{a}__{b}.md # 关系

Tags（表目录级别）：
    hdc_level:table  main_entity:{value}  table_type:{value}  pk:{value}

需求覆盖：1.3（tags 写入）、1.4（trigger SemanticProcessor via write）、3.3（rm 删除）
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.datavault.models import (
        ColumnSummary,
        DatabaseSummary,
        TableDescriptionWithColumns,
        TableRelationship,
    )
    from app.knowledge.openviking import OpenVikingClient

log = logging.getLogger("vkdbagent.datavault.uploader")

# Base URI prefix for all HDC content in OpenViking.
# Using resources path to route writes through _write_direct_with_refresh,
# which triggers SemanticProcessor to automatically generate L0 (.abstract.md)
# and L1 (.overview.md) semantic summaries for each table directory.
# These hierarchical summaries enable table-level semantic search via find(level=[0,1]).
# See: .kiro/specs/hdc-retrieval-optimization/requirements.md § Requirement 1
_HDC_ROOT = "viking://resources/hdc"


def storage_key(schema_id: int, database_name: str, *, namespace: str | None = None) -> str:
    """{schemaId}/{database_name}[/{namespace}] — 唯一标识一个数据库实例 + 可选的HDC变体。

    Args:
        schema_id: OneDBA schema ID
        database_name: 数据库名称
        namespace: 可选的HDC命名空间，用于同一(schema_id, database_name)下隔离不同知识库变体
                   （如 incomplete/complete/overcomplete）。None 时行为不变。
    """
    base = f"{schema_id}/{database_name}"
    if namespace:
        return f"{base}/{namespace}"
    return base


def _db_uri(key: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/"""
    return f"{_HDC_ROOT}/{key}"


def _tables_dir_uri(key: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/_tables/"""
    return f"{_db_uri(key)}/_tables"


def _relations_dir_uri(key: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/_relationships/"""
    return f"{_db_uri(key)}/_relationships"


def _table_dir_uri(key: str, table_name: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/_tables/{table}/"""
    return f"{_tables_dir_uri(key)}/{table_name}"


def _db_index_uri(key: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/_INDEX.md"""
    return f"{_db_uri(key)}/_INDEX.md"


def _table_index_uri(key: str, table_name: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/_tables/{table}/_INDEX.md"""
    return f"{_table_dir_uri(key, table_name)}/_INDEX.md"


def _columns_dir_uri(key: str, table_name: str) -> str:
    """viking://resources/hdc/{schemaId}/{db}/_tables/{table}/_columns/"""
    return f"{_table_dir_uri(key, table_name)}/_columns"


def _format_table_index(table: "TableDescriptionWithColumns") -> str:
    """Format the _INDEX.md content for a table.

    First paragraph MUST contain main_entity synonyms to ensure VLM summary quality
    (requirement from design.md: "first paragraph must contain main_entity synonyms
    for VLM summary quality").
    """
    me = table.main_entity or table.table_name
    tt = table.table_type
    pk = table.primary_key or "（无主键）"

    lines = [
        f"{me}",
        "",
        f"**{table.table_name}** 是 **{tt}** 类型的表，主键为 `{pk}`。",
        "",
    ]

    if table.key_attributes:
        lines.append("## 关键业务属性")
        lines.append("")
        for attr in table.key_attributes:
            lines.append(f"- {attr}")
        lines.append("")

    if table.description:
        lines.append("## 详细描述")
        lines.append("")
        lines.append(table.description)
        lines.append("")

    if table.usage_scenario:
        lines.append("## 使用场景")
        lines.append("")
        lines.append(table.usage_scenario)
        lines.append("")

    if table.row_count_estimate:
        lines.append(f"*估计行数：{table.row_count_estimate:,}*")

    return "\n".join(lines).strip() + "\n"


def _format_column_md(col: "ColumnSummary") -> str:
    """Format a single column .md file."""
    lines = [
        f"# {col.column_name}",
        "",
        col.description or f"`{col.column_name}` 列（{col.data_type}）",
    ]
    if col.sample_values:
        lines.append("")
        lines.append("**示例值**：")
        for v in col.sample_values:
            lines.append(f"- `{v}`")
    return "\n".join(lines).strip() + "\n"


def _format_tables_index(tables: list["TableDescriptionWithColumns"]) -> str:
    """Format the _tables/_INDEX.md content — minimal index for SemanticProcessor.

    Provides SemanticProcessor with material to generate _tables/.abstract.md (L0)
    and .overview.md (L1). Without this file, the directory-level L0 would remain
    "[Directory overview is not generated]".

    DESIGN: Grouped by main_entity prefix to keep file size O(unique entities) not
    O(table count). For 5000 tables with 200 unique entities, this is ~8KB instead
    of ~200KB. The per-table _INDEX.md already carries full descriptions and
    generates per-table L0/L1 vectors. The directory-level L0/L1 only needs enough
    signal for coarse-grained domain filtering ("which tables match the user's
    business domain?").
    """
    from collections import Counter

    # Group by the first part of main_entity (the primary entity name)
    entity_groups: Counter[str] = Counter()
    for t in tables:
        me = t.main_entity or t.table_name
        primary = me.split("/")[0].strip()
        if primary:
            entity_groups[primary] += 1

    lines = [
        f"# 数据库表目录",
        "",
        f"**表总数**：{len(tables)}",
        f"**业务实体**：{len(entity_groups)} 类",
        "",
        "## 核心实体分布",
        "",
    ]
    for entity, count in entity_groups.most_common():
        lines.append(f"- **{entity}**：{count} 张表")
    return "\n".join(lines).strip() + "\n"


def _format_database_index(db_summary: "DatabaseSummary") -> str:
    """Format the database-level _INDEX.md content."""
    entities = "、".join(db_summary.representative_entities) if db_summary.representative_entities else db_summary.database_name
    domain = db_summary.domain_hint or ""

    lines = [
        f"# {db_summary.database_name}",
        "",
        f"**核心实体**：{entities}",
    ]
    if domain:
        lines.append(f"**业务域**：{domain}")
    lines.append(f"**表数量**：{db_summary.table_count}")
    lines.append("")
    if db_summary.description:
        lines.append(db_summary.description)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _format_relationship_md(rel: "TableRelationship") -> str:
    """Format a single relationship .md file."""
    src = rel.source_table
    tgt = rel.target_table
    rt = rel.relationship_type
    conf = rel.confidence

    lines = [
        f"# {src} → {tgt}",
        "",
        f"**关系类型**：{rt}",
        f"**置信度**：{conf:.0%}",
    ]
    if rel.join_columns:
        lines.append("")
        lines.append("**连接字段**：")
        for sc, tc in rel.join_columns:
            lines.append(f"- `{src}.{sc}` = `{tgt}.{tc}`")
    if rel.description:
        lines.append("")
        lines.append(rel.description)
    return "\n".join(lines).strip() + "\n"


class HDCUploader:
    """将 HDC 生成内容写入 OpenViking 资源目录结构。

    职责：
    - 创建目录结构：viking://resources/hdc/{db}/_tables/{table}/
    - 写入 _INDEX.md（表/数据库摘要）和 {column}.md 文件
    - 调用 set_tags 设置结构化元数据
    - write(wait=True) 触发 SemanticProcessor 自动生成 L0/L1
    - 通过 rm 递归删除数据库或单表 HDC 数据
    """

    def __init__(self, ov_client: "OpenVikingClient") -> None:
        self._ov = ov_client

    # ── Embedding 等待 ──────────────────────────────────────────

    async def wait_for_embedding(
        self, key: str, *, timeout: float = 60.0, interval: float = 1.0
    ) -> bool:
        """Poll find(level=[0,1]) until L0/L1 summaries are retrievable.

        Resources path generates L0/L1 asynchronously via SemanticProcessor
        after L2 embedding completes, so L0/L1 readiness is the more restrictive
        condition and the correct signal that all levels are ready.
        """
        tables_uri = _tables_dir_uri(key)
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            try:
                result = await self._ov.find(
                    query="test",
                    target_uri=tables_uri,
                    level=[0, 1],
                    limit=1,
                )
                if result:
                    entries = (
                        result if isinstance(result, list)
                        else result.get("memories", []) if isinstance(result, dict)
                        else []
                    )
                    if entries:
                        log.info(
                            "HDCUploader: embedding ready for key=%s after %.1fs",
                            key, timeout - (deadline - asyncio.get_event_loop().time()),
                        )
                        return True
            except Exception:
                pass  # find() 可能抛异常，重试
            await asyncio.sleep(interval)

        log.warning(
            "HDCUploader: embedding not ready for key=%s within %.0fs timeout",
            key, timeout,
        )
        return False

    # ── 公开 API ────────────────────────────────────────────────

    async def upload_tables(
        self,
        key: str,
        tables: list["TableDescriptionWithColumns"],
    ) -> None:
        """Phase A: 上传表到 OpenViking（不含数据库摘要和关系）。

        创建数据库目录和 _tables 目录，逐表上传表描述和列详情。
        单表上传失败不中断整体流程，记录错误并继续。

        使 OpenViking find API 在后续关系检测阶段可用。
        """
        # 1. 创建目录结构
        await self._ov.mkdir(_db_uri(key))
        await self._ov.mkdir(_tables_dir_uri(key))

        # 2. 逐表上传（单表失败不中断）
        for table in tables:
            try:
                await self.upload_table(key, table)
            except Exception:
                log.warning(
                    "HDCUploader: upload table failed for %s/%s",
                    key, table.table_name, exc_info=True,
                )

        # 3. 写入 _tables/_INDEX.md 目录汇总，触发 SemanticProcessor 生成 L0/L1
        # 没有此文件时，_tables/.abstract.md 永远为 "[Directory overview is not generated]"
        # 导致 find() 的 tags 语义过滤失效
        # wait=False — 避免 OpenViking VLM 连接池超时，embedding 异步完成
        tables_index = _format_tables_index(tables)
        await self._ov.write(
            f"{_tables_dir_uri(key)}/_INDEX.md", tables_index,
            mode="create", wait=False,
        )

        log.info(
            "HDCUploader: uploaded %d tables for %s",
            len(tables), key,
        )

    async def upload_cascade(
        self,
        key: str,
        db_summary: "DatabaseSummary",
        relationships: list["TableRelationship"],
    ) -> None:
        """Phase B: 上传数据库摘要和关系文件。

        假设 upload_tables() 已经完成（数据库目录和 _tables 目录已存在）。
        写入数据库 _INDEX.md 和 _relationships/{src}__{tgt}.md 文件。
        """
        # 确保 _relationships 目录存在
        await self._ov.mkdir(_relations_dir_uri(key))

        # 写入数据库摘要（wait=True + timeout=60s，等 embedding 完成）
        db_index_content = _format_database_index(db_summary)
        db_index_uri = f"{_db_uri(key)}/_INDEX.md"
        await self._ov.write(
            db_index_uri, db_index_content, mode="replace", wait=True,
            timeout=60.0,
        )

        # 写入关系文件（mode="replace" — on rebuild, old relationship files exist）
        for rel in relationships:
            rel_content = _format_relationship_md(rel)
            rel_uri = f"{_relations_dir_uri(key)}/{rel.source_table}__{rel.target_table}.md"
            await self._ov.write(rel_uri, rel_content, mode="replace", wait=False)

        log.info(
            "HDCUploader: uploaded cascade for %s (summary + %d relationships)",
            key, len(relationships),
        )

    async def upload_database(
        self,
        key: str,
        db_summary: "DatabaseSummary",
        tables: list["TableDescriptionWithColumns"],
        relationships: list["TableRelationship"],
    ) -> None:
        """便捷方法：upload_tables + upload_cascade。保持向后兼容。

        等效于依次调用 upload_tables() 和 upload_cascade()。
        """
        await self.upload_tables(key, tables)
        await self.upload_cascade(key, db_summary, relationships)

    async def upload_table(
        self,
        key: str,
        table_desc: "TableDescriptionWithColumns",
    ) -> None:
        """上传单张表的 HDC 内容（用于增量更新）。

        流程：
        1. mkdir 创建表目录和 _columns/ 子目录
        2. 写入各列 .md 文件到 _columns/ 子目录（无 wait）
        3. 写入 _INDEX.md（wait=True 触发 SemanticProcessor L0/L1 生成）
        4. 设置表目录 tags（hdc_level、main_entity、table_type、pk）
        """
        table_dir = _table_dir_uri(key, table_desc.table_name)
        columns_dir = _columns_dir_uri(key, table_desc.table_name)
        await self._ov.mkdir(table_dir)
        await self._ov.mkdir(columns_dir)

        # 写入各列 .md 文件到 _columns/ 子目录
        for col in table_desc.columns:
            col_content = _format_column_md(col)
            col_uri = f"{columns_dir}/{col.column_name}.md"
            await self._ov.write(col_uri, col_content, mode="create", wait=False)

        # 写入 _INDEX.md（wait=True 等 embedding 完成，timeout=60s 防止 VLM 超时阻塞）
        # HDC 内容已是 LLM 精炼描述，VLM 摘要可有可无
        # 60s 足够 embedding 向量化完成，VLM 超时在服务端日志中记录但不影响上传
        index_content = _format_table_index(table_desc)
        index_uri = f"{table_dir}/_INDEX.md"
        await self._ov.write(
            index_uri, index_content, mode="create", wait=True,
            timeout=60.0,
        )

        # 设置 tags（OpenViking 要求 k=v 格式）
        tags = [
            "hdc_level=table",
            f"main_entity={table_desc.main_entity}",
            f"table_type={table_desc.table_type}",
            f"pk={table_desc.primary_key}",
        ]
        result = await self._ov.set_tags(table_dir, tags, mode="replace")

        # 额外等待 embedding，确保 tags 索引生效 / find() API 可用
        await asyncio.sleep(1.0)
        if not result:
            log.warning(
                "HDCUploader: set_tags returned empty for table_dir=%s tags=%s. "
                "Tags-based retrieval (hdc_level=table) will not work for this table.",
                table_dir, tags,
            )
        else:
            log.debug(
                "HDCUploader: set_tags succeeded for table_dir=%s tags=%s",
                table_dir, tags,
            )

        log.info(
            "HDCUploader: uploaded table %s/%s (%d columns)",
            key, table_desc.table_name, len(table_desc.columns),
        )

    async def delete_database(self, key: str) -> None:
        """递归删除整个数据库的 HDC 目录。

        需求 3.3：删除 table/database HDC 数据 via rm API。
        """
        db_uri = _db_uri(key)
        await self._ov.rm(db_uri, recursive=True)
        log.info("HDCUploader: deleted database %s", key)

    async def delete_table(self, key: str, table_name: str) -> None:
        """删除单张表的 HDC 目录。

        需求 3.3：删除 table/database HDC 数据 via rm API。
        """
        table_dir = _table_dir_uri(key, table_name)
        await self._ov.rm(table_dir, recursive=True)
        log.info("HDCUploader: deleted table %s/%s", key, table_name)