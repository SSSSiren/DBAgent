"""Unit tests for HDC retriever and updater."""

import pytest

from app.datavault.models import HDCContext, TableMatch, ColumnSummary, TableDescription


class MockOVClient:
    """Mock OpenViking client for testing."""

    def __init__(self, find_responses=None, index_contents=None):
        self._responses = find_responses or {}
        self._indexes = index_contents or {}
        self._call_count = 0

    async def find(self, query="", target_uri="", tags=None, level=None, limit=10, **kwargs):
        self._call_count += 1
        key = target_uri.rstrip("/").split("/")[-1] if target_uri else "default"
        return self._responses.get(key, self._responses.get("default", {}))

    async def _get_raw(self, path, uri):
        """Mock content read for _INDEX.md and column .md files."""
        import re
        # Extract table_name from URI
        m = re.search(r'/_tables/([^/]+)/', uri)
        table = m.group(1) if m else ""
        if uri.endswith("_INDEX.md") and table in self._indexes:
            main_entity, table_type = self._indexes[table]
            return (
                f"{main_entity}\n\n"
                f"**{table}** 是 **{table_type}** 类型的表，主键为 `id`。\n\n"
                f"## 详细描述\n\n"
                f"{table}事实表描述。\n"
            )
        if ".md" in uri and table in self._indexes:
            col_name = uri.rstrip("/").split("/")[-1].replace(".md", "")
            # Map column names to their Chinese descriptions
            desc_map = {
                "refund_amount": "退款金额",
                "refund_status": "退款状态",
                "total_amount": "订单总金额",
            }
            desc = desc_map.get(col_name, f"{col_name} 的业务描述")
            return f"# {col_name}\n\n{desc}\n"
        return ""


def make_find_result(items):
    """Helper: create a find API result with list of item dicts."""
    return {"items": items}


def make_table_item(name, abstract="", tags=None):
    """Helper: create a table-level find result item."""
    return {
        "name": name,
        "uri": f"viking://resources/hdc/dwd_trade/_tables/{name}",
        "abstract": abstract,
        "tags": tags or [],
    }


def make_column_item(name, abstract=""):
    """Helper: create a column-level find result item."""
    return {
        "name": f"{name}.md",
        "uri": f"viking://resources/hdc/dwd_trade/_tables/after_sale_order/{name}.md",
        "abstract": abstract,
    }


class TestHDCRetriever:
    """Tests for HDCRetriever.retrieve() and format_context()."""

    @pytest.fixture
    def retriever(self):
        from app.datavault.retriever import HDCRetriever
        return HDCRetriever

    @pytest.mark.asyncio
    async def test_retrieve_with_matches(self, retriever):
        """Retrieval returns HDCContext with matched tables and columns."""
        ov = MockOVClient({
            "_tables": {
                "items": [
                    make_table_item("after_sale_order", "售后订单表",
                                    ["main_entity:售后/退货/退款", "table_type:fact", "pk:id"]),
                    make_table_item("order_info", "订单信息表",
                                    ["main_entity:订单/交易", "table_type:fact"]),
                ]
            },
            "after_sale_order": {
                "items": [
                    make_column_item("refund_amount", "退款金额"),
                    make_column_item("refund_status", "退款状态"),
                ]
            },
            "order_info": {
                "items": [
                    make_column_item("total_amount", "订单总金额"),
                ]
            },
        }, index_contents={
            "after_sale_order": ("售后/退货/退款", "fact"),
            "order_info": ("订单/交易", "fact"),
        })

        r = retriever(ov)
        result = await r.retrieve("退款金额", "dwd_trade")

        assert result is not None
        assert len(result.matched_tables) == 2
        assert result.matched_tables[0].table_name == "after_sale_order"
        assert result.matched_tables[0].main_entity == "售后/退货/退款"
        assert result.matched_tables[0].table_type == "fact"
        assert "退款金额" in result.matched_tables[0].relevant_columns[0]

    @pytest.mark.asyncio
    async def test_retrieve_empty_returns_none(self, retriever):
        """No matches returns None (degradation)."""
        ov = MockOVClient({
            "_tables": {"items": []},
        })

        r = retriever(ov)
        result = await r.retrieve("nonexistent_query", "dwd_trade")

        assert result is None

    def test_format_context_with_data(self, retriever):
        """format_context produces valid [数据底座] section."""
        r = retriever(MockOVClient())
        ctx = HDCContext(
            database_summary="电商交易核心数据库，涵盖订单、支付、退款全链路。",
            matched_tables=[
                TableMatch(
                    table_name="after_sale_order",
                    main_entity="售后/退货/退款",
                    table_type="fact",
                    description="售后订单事实表",
                    relevant_columns=["退款金额", "退款状态", "退款原因"],
                ),
            ],
        )

        result = r.format_context(ctx)

        assert "[数据底座 — 数据库知识]" in result
        assert "电商交易核心数据库" in result
        assert "after_sale_order" in result
        assert "售后/退货/退款" in result
        assert "退款金额" in result

    def test_format_context_none(self, retriever):
        """format_context(None) returns empty string."""
        r = retriever(MockOVClient())
        result = r.format_context(None)
        assert result == ""

    def test_format_context_empty_tables(self, retriever):
        """format_context with empty matched_tables still produces header."""
        r = retriever(MockOVClient())
        ctx = HDCContext(database_summary="测试库", matched_tables=[])

        result = r.format_context(ctx)

        assert "[数据底座 — 数据库知识]" in result
        assert "测试库" in result

    @pytest.mark.asyncio
    async def test_openviking_unavailable_returns_none(self, retriever):
        """OpenViking find returns empty dict → returns None (graceful degradation)."""
        ov = MockOVClient({"_tables": {}})  # empty response

        r = retriever(ov)
        result = await r.retrieve("退款", "dwd_trade")

        # Empty result from find() → _extract_matches returns [] → returns None
        assert result is None


class TestHDCUpdater:
    """Tests for HDCUpdater._compute_columns_hash()."""

    def test_same_columns_same_hash(self):
        """Same column structure produces same hash."""
        from app.datavault.updater import HDCUpdater
        from app.datavault.models import ColumnRaw

        cols1 = [
            ColumnRaw(name="id", data_type="bigint", nullable=False),
            ColumnRaw(name="name", data_type="varchar(64)", nullable=True),
        ]
        cols2 = [
            ColumnRaw(name="id", data_type="bigint", nullable=False),
            ColumnRaw(name="name", data_type="varchar(64)", nullable=True),
        ]

        h1 = HDCUpdater._compute_columns_hash(cols1)
        h2 = HDCUpdater._compute_columns_hash(cols2)

        assert h1 == h2

    def test_reordered_columns_same_hash(self):
        """Column order change produces same hash (stable sort)."""
        from app.datavault.updater import HDCUpdater
        from app.datavault.models import ColumnRaw

        cols1 = [
            ColumnRaw(name="id", data_type="bigint", nullable=False),
            ColumnRaw(name="name", data_type="varchar(64)", nullable=True),
        ]
        cols2 = [
            ColumnRaw(name="name", data_type="varchar(64)", nullable=True),
            ColumnRaw(name="id", data_type="bigint", nullable=False),
        ]

        assert HDCUpdater._compute_columns_hash(cols1) == HDCUpdater._compute_columns_hash(cols2)

    def test_different_type_different_hash(self):
        """Changed data type produces different hash."""
        from app.datavault.updater import HDCUpdater
        from app.datavault.models import ColumnRaw

        cols1 = [ColumnRaw(name="id", data_type="int", nullable=False)]
        cols2 = [ColumnRaw(name="id", data_type="bigint", nullable=False)]

        assert HDCUpdater._compute_columns_hash(cols1) != HDCUpdater._compute_columns_hash(cols2)

    def test_added_column_different_hash(self):
        """Added column produces different hash."""
        from app.datavault.updater import HDCUpdater
        from app.datavault.models import ColumnRaw

        cols1 = [ColumnRaw(name="id", data_type="bigint", nullable=False)]
        cols2 = [
            ColumnRaw(name="id", data_type="bigint", nullable=False),
            ColumnRaw(name="name", data_type="varchar(64)", nullable=True),
        ]

        assert HDCUpdater._compute_columns_hash(cols1) != HDCUpdater._compute_columns_hash(cols2)

    def test_removed_column_different_hash(self):
        """Removed column produces different hash."""
        from app.datavault.updater import HDCUpdater
        from app.datavault.models import ColumnRaw

        cols1 = [
            ColumnRaw(name="id", data_type="bigint", nullable=False),
            ColumnRaw(name="name", data_type="varchar(64)", nullable=True),
        ]
        cols2 = [ColumnRaw(name="id", data_type="bigint", nullable=False)]

        assert HDCUpdater._compute_columns_hash(cols1) != HDCUpdater._compute_columns_hash(cols2)

    def test_empty_columns_hash(self):
        """Empty column list produces a hash."""
        from app.datavault.updater import HDCUpdater

        h = HDCUpdater._compute_columns_hash([])
        assert isinstance(h, str)
        assert len(h) > 0


class TestModels:
    """Tests for HDC data model constraints."""

    def test_table_description_defaults(self):
        """TableDescription has sensible defaults."""
        td = TableDescription()
        assert td.table_type == "fact"
        assert td.main_entity == ""
        assert td.key_attributes == []

    def test_table_description_with_synonyms(self):
        """main_entity supports /-separated synonyms."""
        td = TableDescription(
            table_name="after_sale_order",
            main_entity="售后/退货/退款/换货",
            table_type="fact",
            primary_key="id",
            key_attributes=["order_id", "refund_amount", "refund_status"],
            description="售后订单事实表",
        )
        assert "/" in td.main_entity
        assert len(td.main_entity.split("/")) == 4

    def test_hdc_context_empty(self):
        """Empty HDCContext has sensible defaults."""
        ctx = HDCContext()
        assert ctx.database_summary == ""
        assert ctx.matched_tables == []

    def test_table_match_default(self):
        """TableMatch defaults."""
        tm = TableMatch(table_name="test", main_entity="test", table_type="fact", description="")
        assert tm.relevant_columns == []
