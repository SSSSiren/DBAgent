"""
SchemaCollector — 从 OneDBA 采集原始 schema 元数据（v1 API）

采集流程：
1. list_tables() → 获取表列表（表名、注释、引擎、行数估计）
   回退: execute_sql("SHOW TABLE STATUS")
2. 逐表 get_table_structure() → 获取列结构（字段名、类型、键等）
   回退: execute_sql("DESCRIBE")
3. 逐表 execute_sql("SELECT * LIMIT 3") → 获取采样数据（无 v1 替代）

单表采集失败时记录错误并继续处理其余表，不中断整体采集。
"""

from __future__ import annotations

import logging
from typing import Any

from app.client.onedba import OneDBAClient
from app.datavault.models import ColumnRaw, DatabaseRaw, TableRaw

logger = logging.getLogger(__name__)


def _parse_list_tables_row(row: dict[str, Any]) -> dict[str, str]:
    """Parse a single row from v1 list_tables API result.

    v1 API 返回的 items 字段格式：
    - tableName: 表名
    - tableComment: 表注释
    - engine: 存储引擎
    - tableRows: 估计行数
    """
    name = str(row.get("tableName") or "")
    comment = str(row.get("tableComment") or "")
    engine = str(row.get("engine") or "")
    row_count_str = str(row.get("tableRows") or "0")

    try:
        row_count = int(row_count_str)
    except (ValueError, TypeError):
        row_count = 0

    return {
        "name": name,
        "comment": comment,
        "engine": engine,
        "row_count": row_count,
    }


def _parse_show_table_status_row(row: dict[str, Any]) -> dict[str, str]:
    """Parse a single row from SHOW TABLE STATUS result (fallback).

    OneDBA 返回的 columnDatas 中，SHOW TABLE STATUS 的列索引：
    - col_1 (Name): 表名
    - col_18 (Comment): 表注释
    - col_2 (Engine): 存储引擎
    - col_5 (Rows): 估计行数

    也兼容使用命名键（Name, Comment, Engine, Rows）的返回格式。
    """
    name = str(row.get("col_1") or row.get("Name") or "")
    comment = str(row.get("col_18") or row.get("Comment") or "")
    engine = str(row.get("col_2") or row.get("Engine") or "")
    rows_str = str(row.get("col_5") or row.get("Rows") or "0")

    try:
        row_count = int(rows_str)
    except (ValueError, TypeError):
        row_count = 0

    return {
        "name": name,
        "comment": comment,
        "engine": engine,
        "row_count": row_count,
    }


def _parse_describe_row(row: dict[str, Any]) -> ColumnRaw:
    """Parse a single row from DESCRIBE result into a ColumnRaw.

    DESCRIBE 返回的列可能是命名键（Field/Type/Null/Key/Default/Extra）
    或数字键（col_1/col_2/col_3/col_4/col_5/col_6）。
    """
    name = str(row.get("Field") or row.get("col_1") or "")
    data_type = str(row.get("Type") or row.get("col_2") or "")
    nullable_str = str(row.get("Null") or row.get("col_3") or "YES")
    nullable = nullable_str.strip().upper() == "YES"
    key = str(row.get("Key") or row.get("col_4") or "")
    default = str(row.get("Default") or row.get("col_5") or "")
    extra = str(row.get("Extra") or row.get("col_6") or "")

    return ColumnRaw(
        name=name,
        data_type=data_type,
        nullable=nullable,
        key=key,
        default=default,
        extra=extra,
    )


class SchemaCollector:
    """从 OneDBA 采集数据库的原始 schema 元数据（v1 API 优先）。

    单表采集失败不中断整体采集，记录错误并继续。
    """

    def __init__(self, client: OneDBAClient) -> None:
        self._client = client

    async def collect_database(
        self, schema_id: int, tables: list[str] | None = None
    ) -> DatabaseRaw:
        """采集指定数据库的 schema 元数据。

        Args:
            schema_id: OneDBA schema ID
            tables: 可选的目标表名列表。None 时采集全库；指定后仅采集匹配的表

        Returns:
            DatabaseRaw 包含所有成功采集的表元数据

        Precondition: OneDBAClient 已初始化，schema_id 有效
        Postcondition: DatabaseRaw 包含所有成功采集的表；失败的表记录在日志中
        Invariant: DatabaseRaw.tables 不包含重复表名
        """
        # ── Step 1: 获取表列表（v1 API 优先，回退 SHOW TABLE STATUS）──
        table_infos: list[dict[str, str]] = []
        try:
            tables_raw = await self._client.list_tables(schema_id, size=2000)
            for row in tables_raw:
                if isinstance(row, dict):
                    info = _parse_list_tables_row(row)
                    if info["name"]:
                        table_infos.append(info)
        except Exception as e:
            logger.warning(
                "SchemaCollector: list_tables failed for schema_id=%d, "
                "falling back to SHOW TABLE STATUS: %s",
                schema_id, e,
            )
            try:
                result = await self._client.execute_sql(
                    schema_id, "SHOW TABLE STATUS"
                )
                rows: list[dict[str, Any]] = result.get("columnDatas") or []
                for row in rows:
                    if isinstance(row, dict):
                        info = _parse_show_table_status_row(row)
                        if info["name"]:
                            table_infos.append(info)
            except Exception as e2:
                logger.error(
                    "SchemaCollector: SHOW TABLE STATUS also failed "
                    "for schema_id=%d: %s",
                    schema_id, e2,
                )
                return DatabaseRaw(schema_id=schema_id)

        # ── 表名过滤（部分表模式）──
        if tables is not None:
            table_set = set(tables)
            # 检查不存在的表名并记录警告
            existing_names = {info["name"] for info in table_infos}
            for t in tables:
                if t not in existing_names:
                    logger.warning(
                        "SchemaCollector: table '%s' not found in schema_id=%d, skipped",
                        t,
                        schema_id,
                    )
            table_infos = [info for info in table_infos if info["name"] in table_set]

        if not table_infos:
            logger.info(
                "SchemaCollector: no tables found for schema_id=%d", schema_id
            )
            return DatabaseRaw(schema_id=schema_id)

        # ── Step 2 & 3: 逐表采集列结构和采样数据（v1 API 优先）──
        tables: list[TableRaw] = []
        seen_names: set[str] = set()

        for info in table_infos:
            table_name = info["name"]

            # Enforce invariant: no duplicate table names
            if table_name in seen_names:
                logger.warning(
                    "SchemaCollector: duplicate table name '%s' skipped", table_name
                )
                continue
            seen_names.add(table_name)

            table = TableRaw(
                name=table_name,
                comment=info["comment"],
                engine=info["engine"],
                row_count_estimate=int(info["row_count"]),
            )

            # ── Step 2: 采集列结构（v1 API 优先，回退 DESCRIBE）──
            try:
                desc_result = await self._client.get_table_structure(
                    schema_id, table_name
                )
                desc_rows = desc_result.get("columnDatas") or []
                for row in desc_rows:
                    if isinstance(row, dict):
                        col = _parse_describe_row(row)
                        if col.name:
                            table.columns.append(col)
            except Exception as e:
                logger.warning(
                    "SchemaCollector: get_table_structure failed for '%s', "
                    "falling back to DESCRIBE: %s",
                    table_name, e,
                )
                try:
                    safe_name = f"`{table_name}`"
                    desc_result = await self._client.execute_sql(
                        schema_id, f"DESCRIBE {safe_name}"
                    )
                    desc_rows = desc_result.get("columnDatas") or []
                    for row in desc_rows:
                        if isinstance(row, dict):
                            col = _parse_describe_row(row)
                            if col.name:
                                table.columns.append(col)
                except Exception as e2:
                    logger.error(
                        "SchemaCollector: DESCRIBE also failed for table '%s' "
                        "(schema_id=%d): %s",
                        table_name, schema_id, e2,
                    )

            # ── Step 3: 采集采样数据（无 v1 替代，仍用 execute_sql）──
            safe_name = f"`{table_name}`"
            try:
                sample_result = await self._client.execute_sql(
                    schema_id, f"SELECT * FROM {safe_name} LIMIT 3"
                )
                sample_rows = sample_result.get("columnDatas") or []
                table.sample_rows = [
                    row for row in sample_rows if isinstance(row, dict)
                ]
            except Exception as e:
                logger.error(
                    "SchemaCollector: SELECT * failed for table '%s' "
                    "(schema_id=%d): %s",
                    table_name,
                    schema_id,
                    e,
                )

            tables.append(table)

        logger.info(
            "SchemaCollector: collected %d tables for schema_id=%d",
            len(tables),
            schema_id,
        )
        return DatabaseRaw(schema_id=schema_id, tables=tables)
