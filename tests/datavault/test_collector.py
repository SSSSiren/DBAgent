"""Unit tests for SchemaCollector."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.datavault.collector import SchemaCollector
from app.datavault.models import ColumnRaw, TableRaw, DatabaseRaw


class MockOneDBAClient:
    """Mock OneDBA client for testing."""

    def __init__(self, tables_data=None, fail_table=None,
                 mock_list_tables=False, mock_get_structure=False):
        self._tables_data = tables_data or {}
        self._fail_table = fail_table
        self._mock_list_tables = mock_list_tables
        self._mock_get_structure = mock_get_structure
        self.execute_sql = AsyncMock(side_effect=self._mock_execute)
        self.list_tables = AsyncMock(side_effect=self._mock_list_tables_call)
        self.get_table_structure = AsyncMock(
            side_effect=self._mock_get_structure_call
        )

    async def _mock_list_tables_call(self, schema_id, keyword="", page=1, size=100):
        if self._mock_list_tables:
            return self._tables_data.get("list_tables", [])
        raise NotImplementedError("list_tables not mocked (triggers fallback)")

    async def _mock_get_structure_call(self, schema_id, table_name):
        if self._mock_get_structure:
            key = f"structure_{table_name}"
            return self._tables_data.get(key, {"columnDatas": []})
        raise NotImplementedError(
            "get_table_structure not mocked (triggers fallback)"
        )

    async def _mock_execute(self, schema_id, sql):
        sql_upper = sql.strip().upper()
        if sql_upper.startswith("SHOW TABLE STATUS"):
            return self._tables_data.get("show_table_status", {"columnDatas": []})
        elif sql_upper.startswith("DESCRIBE"):
            table_name = sql.split()[-1].strip("`")
            if self._fail_table == table_name:
                raise RuntimeError(f"Simulated DESCRIBE failure for {table_name}")
            return self._tables_data.get(f"describe_{table_name}", {"columnDatas": []})
        elif sql_upper.startswith("SELECT *"):
            table_name = sql.split("FROM")[-1].split("LIMIT")[0].strip().strip("`")
            return self._tables_data.get(f"sample_{table_name}", {"columnDatas": []})
        return {"columnDatas": []}


def make_status_row(name, comment="", engine="InnoDB", rows=1000):
    """Helper: create a SHOW TABLE STATUS row."""
    return {
        "col_1": name,
        "col_18": comment,
        "col_2": engine,
        "col_5": str(rows),
    }


def make_describe_row(field, type_, null="YES", key="", default="", extra=""):
    """Helper: create a DESCRIBE row."""
    return {
        "Field": field,
        "Type": type_,
        "Null": null,
        "Key": key,
        "Default": default,
        "Extra": extra,
    }


def make_sample_rows(rows):
    """Helper: create sample data rows."""
    return rows


def make_list_tables_row(name, comment="", engine="InnoDB", rows=1000):
    """Helper: create a v1 list_tables row."""
    return {
        "tableName": name,
        "tableComment": comment,
        "engine": engine,
        "tableRows": str(rows),
    }


class TestSchemaCollector:
    """Tests for SchemaCollector.collect_database()."""

    @pytest.mark.asyncio
    async def test_collect_basic(self):
        """Basic collection: one table with two columns and sample data."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("users", "用户表"),
                ]
            },
            "describe_users": {
                "columnDatas": [
                    make_describe_row("id", "bigint", "NO", "PRI", "", "auto_increment"),
                    make_describe_row("name", "varchar(64)", "YES", "", ""),
                ]
            },
            "sample_users": {
                "columnDatas": [
                    {"id": "1", "name": "Alice"},
                    {"id": "2", "name": "Bob"},
                ]
            },
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        assert isinstance(result, DatabaseRaw)
        assert result.schema_id == 142
        assert len(result.tables) == 1

        table = result.tables[0]
        assert table.name == "users"
        assert table.comment == "用户表"
        assert table.engine == "InnoDB"
        assert table.row_count_estimate == 1000
        assert len(table.columns) == 2
        assert table.columns[0].name == "id"
        assert table.columns[0].data_type == "bigint"
        assert table.columns[0].key == "PRI"
        assert table.columns[0].nullable is False
        assert len(table.sample_rows) == 2

    @pytest.mark.asyncio
    async def test_collect_empty_database(self):
        """Empty database: SHOW TABLE STATUS returns no tables."""
        client = MockOneDBAClient({
            "show_table_status": {"columnDatas": []},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        assert len(result.tables) == 0

    @pytest.mark.asyncio
    async def test_collect_no_column_datas(self):
        """SHOW TABLE STATUS returns no columnDatas key."""
        client = MockOneDBAClient({
            "show_table_status": {"other": "data"},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        assert len(result.tables) == 0

    @pytest.mark.asyncio
    async def test_single_table_failure_does_not_abort(self):
        """Single table DESCRIBE failure logs error, continues with other tables."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("good_table", "正常表"),
                    make_status_row("bad_table", "会失败的表"),
                ]
            },
            "describe_good_table": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_good_table": {"columnDatas": [{"id": "1"}]},
            "sample_bad_table": {"columnDatas": [{"id": "1"}]},
        }, fail_table="bad_table")

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        # Good table should still be collected
        assert len(result.tables) == 2
        good_table = next(t for t in result.tables if t.name == "good_table")
        assert len(good_table.columns) == 1
        assert len(good_table.sample_rows) == 1

        # Bad table should exist but with empty columns
        bad_table = next(t for t in result.tables if t.name == "bad_table")
        assert len(bad_table.columns) == 0

    @pytest.mark.asyncio
    async def test_duplicate_table_names_skipped(self):
        """Duplicate table names are skipped (invariant enforcement)."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("duplicate", "表1"),
                    make_status_row("duplicate", "表1重复"),
                ]
            },
            "describe_duplicate": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_duplicate": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        # Only first occurrence kept
        assert len(result.tables) == 1

    @pytest.mark.asyncio
    async def test_unparseable_row_count_defaults_zero(self):
        """Non-numeric row count defaults to 0."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [make_status_row("t", "test", rows="N/A")],
            },
            "describe_t": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_t": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        assert result.tables[0].row_count_estimate == 0

    @pytest.mark.asyncio
    async def test_describe_empty_fields(self):
        """Empty DESCRIBE row with no name is skipped."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [make_status_row("t", "")],
            },
            "describe_t": {
                "columnDatas": [{}],  # Empty row — no Field key
            },
            "sample_t": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        # Empty rows with no name are skipped
        assert len(result.tables[0].columns) == 0

    # ── 7.1: 部分表模式 ──

    @pytest.mark.asyncio
    async def test_tables_filter_only_collects_specified(self):
        """tables=["users"] only collects specified table, skips others."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("users", "用户表"),
                    make_status_row("orders", "订单表"),
                    make_status_row("products", "商品表"),
                ]
            },
            "describe_users": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_users": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142, tables=["users"])

        assert len(result.tables) == 1
        assert result.tables[0].name == "users"

    @pytest.mark.asyncio
    async def test_tables_none_collects_all(self):
        """tables=None (default) collects all tables — backward compatible."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("users", "用户表"),
                    make_status_row("orders", "订单表"),
                ]
            },
            "describe_users": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_users": {"columnDatas": [{"id": "1"}]},
            "describe_orders": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_orders": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142, tables=None)

        assert len(result.tables) == 2
        names = {t.name for t in result.tables}
        assert names == {"users", "orders"}

    @pytest.mark.asyncio
    async def test_nonexistent_table_name_warns_and_skips(self):
        """Non-existent table name in tables list logs warning, continues."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("users", "用户表"),
                ]
            },
            "describe_users": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_users": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142, tables=["users", "not_exist"])

        # Only the existing table is collected
        assert len(result.tables) == 1
        assert result.tables[0].name == "users"

    @pytest.mark.asyncio
    async def test_all_nonexistent_tables_returns_empty(self):
        """All specified tables don't exist — returns empty DatabaseRaw."""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [
                    make_status_row("users", "用户表"),
                ]
            },
            "describe_users": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_users": {"columnDatas": [{"id": "1"}]},
        })

        collector = SchemaCollector(client)
        result = await collector.collect_database(142, tables=["ghost_a", "ghost_b"])

        assert len(result.tables) == 0

    # ── v1 API 测试 ──

    @pytest.mark.asyncio
    async def test_collect_with_new_apis(self):
        """v1 API: list_tables + get_table_structure 正常采集。"""
        client = MockOneDBAClient({
            "list_tables": [
                make_list_tables_row("users", "用户表"),
            ],
            "structure_users": {
                "columnDatas": [
                    make_describe_row("id", "bigint", "NO", "PRI", "", "auto_increment"),
                    make_describe_row("name", "varchar(64)", "YES", "", ""),
                ]
            },
            "sample_users": {
                "columnDatas": [{"id": "1", "name": "Alice"}],
            },
        }, mock_list_tables=True, mock_get_structure=True)

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.name == "users"
        assert table.comment == "用户表"
        assert table.engine == "InnoDB"
        assert len(table.columns) == 2
        assert len(table.sample_rows) == 1

        # 确认调用了新 API 而非 execute_sql
        client.list_tables.assert_called_once()
        client.get_table_structure.assert_called_once_with(142, "users")

    @pytest.mark.asyncio
    async def test_new_api_fallback(self):
        """v1 API 抛异常时回退到 execute_sql。"""
        client = MockOneDBAClient({
            "show_table_status": {
                "columnDatas": [make_status_row("users", "用户表")],
            },
            "describe_users": {
                "columnDatas": [make_describe_row("id", "int", "NO", "PRI")],
            },
            "sample_users": {"columnDatas": [{"id": "1"}]},
        }, mock_list_tables=False, mock_get_structure=False)

        collector = SchemaCollector(client)
        result = await collector.collect_database(142)

        assert len(result.tables) == 1
        assert result.tables[0].name == "users"
        # 确认走了 execute_sql fallback
        client.execute_sql.assert_called()
