"""
HDCUploader — 将 HDC 内容写入 OpenViking 资源目录结构并设置结构化 tags。

目录结构：
    viking://resources/hdc/{db}/                       # 数据库目录
    viking://resources/hdc/{db}/_INDEX.md              # 数据库摘要
    viking://resources/hdc/{db}/_tables/{table}/       # 表目录
    viking://resources/hdc/{db}/_tables/{table}/_INDEX.md  # 表描述
    viking://resources/hdc/{db}/_tables/{table}/{col}.md   # 列详情
    viking://resources/hdc/{db}/_relationships/{a}__{b}.md # 关系

Tags（表目录级别）：
    hdc_level:table  main_entity:{value}  table_type:{value}  pk:{value}

需求覆盖：1.3（tags 写入）、1.4（trigger SemanticProcessor via write wait=True）、3.3（rm 删除）
"""

from __future__ import annotations

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

# Base URI prefix for all HDC content in OpenViking
_HDC_ROOT = "viking://resources/hdc"


def _db_uri(database_name: str) -> str:
    """viking://resources/hdc/{db}/"""
    return f"{_HDC_ROOT}/{database_name}"


def _tables_dir_uri(database_name: str) -> str:
    """viking://resources/hdc/{db}/_tables/"""
    return f"{_db_uri(database_name)}/_tables"


def _relations_dir_uri(database_name: str) -> str:
    """viking://resources/hdc/{db}/_relationships/"""
    return f"{_db_uri(database_name)}/_relationships"


def _table_dir_uri(database_name: str, table_name: str) -> str:
    """viking://resources/hdc/{db}/_tables/{table}/"""
    return f"{_tables_dir_uri(database_name)}/{table_name}"


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

    # ── 公开 API ────────────────────────────────────────────────

    async def upload_database(
        self,
        database_name: str,
        db_summary: "DatabaseSummary",
        tables: list["TableDescriptionWithColumns"],
        relationships: list["TableRelationship"],
    ) -> None:
        """创建完整的数据库 HDC 目录结构并上传所有内容。

        流程：
        1. mkdir 创建数据库目录、_tables 目录、_relationships 目录
        2. 逐表调用 upload_table() 上传表描述和列详情
        3. 写入数据库 _INDEX.md（wait=True 触发 SemanticProcessor）
        4. 写入 _relationships/{src}__{tgt}.md 文件

        单表上传失败不中断整体流程，记录错误并继续。
        """
        # 1. 创建目录结构
        await self._ov.mkdir(_db_uri(database_name))
        await self._ov.mkdir(_tables_dir_uri(database_name))
        await self._ov.mkdir(_relations_dir_uri(database_name))

        # 2. 逐表上传（单表失败不中断）
        for table in tables:
            try:
                await self.upload_table(database_name, table)
            except Exception:
                log.warning(
                    "HDCUploader: upload table failed for %s.%s",
                    database_name, table.table_name, exc_info=True,
                )

        # 3. 写入数据库摘要（wait=True 触发 SemanticProcessor）
        db_index_content = _format_database_index(db_summary)
        db_index_uri = f"{_db_uri(database_name)}/_INDEX.md"
        await self._ov.write(db_index_uri, db_index_content, mode="replace", wait=True)

        # 4. 写入关系文件
        for rel in relationships:
            rel_content = _format_relationship_md(rel)
            rel_uri = f"{_relations_dir_uri(database_name)}/{rel.source_table}__{rel.target_table}.md"
            await self._ov.write(rel_uri, rel_content, mode="replace", wait=False)

        log.info(
            "HDCUploader: uploaded database %s (%d tables, %d relationships)",
            database_name, len(tables), len(relationships),
        )

    async def upload_table(
        self,
        database_name: str,
        table_desc: "TableDescriptionWithColumns",
    ) -> None:
        """上传单张表的 HDC 内容（用于增量更新）。

        流程：
        1. mkdir 创建表目录
        2. 写入各列 .md 文件（无 wait）
        3. 写入 _INDEX.md（wait=True 触发 SemanticProcessor L0/L1 生成）
        4. 设置表目录 tags（hdc_level、main_entity、table_type、pk）
        """
        table_dir = _table_dir_uri(database_name, table_desc.table_name)
        await self._ov.mkdir(table_dir)

        # 写入各列 .md 文件
        for col in table_desc.columns:
            col_content = _format_column_md(col)
            col_uri = f"{table_dir}/{col.column_name}.md"
            await self._ov.write(col_uri, col_content, mode="replace", wait=False)

        # 写入 _INDEX.md（wait=True 触发 SemanticProcessor）
        index_content = _format_table_index(table_desc)
        index_uri = f"{table_dir}/_INDEX.md"
        await self._ov.write(index_uri, index_content, mode="replace", wait=True)

        # 设置 tags
        tags = [
            "hdc_level:table",
            f"main_entity:{table_desc.main_entity}",
            f"table_type:{table_desc.table_type}",
            f"pk:{table_desc.primary_key}",
        ]
        await self._ov.set_tags(table_dir, tags, mode="replace")

        log.info(
            "HDCUploader: uploaded table %s.%s (%d columns)",
            database_name, table_desc.table_name, len(table_desc.columns),
        )

    async def delete_database(self, database_name: str) -> None:
        """递归删除整个数据库的 HDC 目录。

        需求 3.3：删除 table/database HDC 数据 via rm API。
        """
        db_uri = _db_uri(database_name)
        await self._ov.rm(db_uri, recursive=True)
        log.info("HDCUploader: deleted database %s", database_name)

    async def delete_table(self, database_name: str, table_name: str) -> None:
        """删除单张表的 HDC 目录。

        需求 3.3：删除 table/database HDC 数据 via rm API。
        """
        table_dir = _table_dir_uri(database_name, table_name)
        await self._ov.rm(table_dir, recursive=True)
        log.info("HDCUploader: deleted table %s.%s", database_name, table_name)