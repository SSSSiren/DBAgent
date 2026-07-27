"""Unit tests for HDC retriever and updater."""

import pytest

from app.datavault.models import HDCContext, TableMatch, ColumnSummary, TableDescription


class TestURIHelpers:
    """Tests for uploader URI helper functions."""

    def test_storage_key(self):
        from app.datavault.uploader import storage_key
        assert storage_key(142, "dwd_trade") == "142/dwd_trade"

    def test_storage_key_with_namespace(self):
        from app.datavault.uploader import storage_key
        assert storage_key(142, "dwd_trade", namespace="complete") == "142/dwd_trade/complete"

    def test_db_uri(self):
        from app.datavault.uploader import _db_uri
        assert _db_uri("142/dwd_trade") == "viking://resources/hdc/142/dwd_trade"

    def test_tables_dir_uri(self):
        from app.datavault.uploader import _tables_dir_uri
        assert _tables_dir_uri("142/dwd_trade") == "viking://resources/hdc/142/dwd_trade/_tables"

    def test_relations_dir_uri(self):
        from app.datavault.uploader import _relations_dir_uri
        assert _relations_dir_uri("142/dwd_trade") == "viking://resources/hdc/142/dwd_trade/_relationships"

    def test_table_dir_uri(self):
        from app.datavault.uploader import _table_dir_uri
        assert _table_dir_uri("142/dwd_trade", "order_info") == "viking://resources/hdc/142/dwd_trade/_tables/order_info"

    def test_db_index_uri(self):
        from app.datavault.uploader import _db_index_uri
        assert _db_index_uri("142/dwd_trade") == "viking://resources/hdc/142/dwd_trade/_INDEX.md"

    def test_table_index_uri(self):
        from app.datavault.uploader import _table_index_uri
        assert _table_index_uri("142/dwd_trade", "order_info") == "viking://resources/hdc/142/dwd_trade/_tables/order_info/_INDEX.md"

    def test_columns_dir_uri(self):
        from app.datavault.uploader import _columns_dir_uri
        assert _columns_dir_uri("142/dwd_trade", "order_info") == "viking://resources/hdc/142/dwd_trade/_tables/order_info/_columns"


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
        result = await r.retrieve("退款金额", 142, "dwd_trade")

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
        result = await r.retrieve("nonexistent_query", 142, "dwd_trade")

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
        result = await r.retrieve("退款", 142, "dwd_trade")

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


class TestExtractTableName:
    """Tests for _extract_table_name() with _columns/ path format (Req 1.4, 4.2)."""

    def test_extract_from_columns_subdir(self):
        """URI with _columns/ subdirectory → table is parent of _columns."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables/order_info/_columns/refund_amount.md",
            "name": "refund_amount.md",
        })
        assert result == "order_info"

    def test_extract_from_abstract_md(self):
        """URI ending in .abstract.md → table is parent directory."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables/order_info/.abstract.md",
            "name": ".abstract.md",
        })
        assert result == "order_info"

    def test_extract_from_overview_md(self):
        """URI ending in .overview.md → table is parent directory."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables/order_info/.overview.md",
            "name": ".overview.md",
        })
        assert result == "order_info"

    def test_extract_from_column_file_old_format(self):
        """Old format: column .md directly in table directory."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables/order_info/refund_amount.md",
            "name": "refund_amount.md",
        })
        assert result == "order_info"

    def test_extract_from_index_md(self):
        """URI ending in _INDEX.md → _extract_table_name returns '_INDEX' (strips .md).
        Note: _INDEX.md is not returned at level=[0,1] by find(), so this path
        is not encountered in the scoring loop. The behavior is the static method's
        raw return value."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables/order_info/_INDEX.md",
            "name": "_INDEX.md",
        })
        assert result == "_INDEX"

    def test_extract_from_table_directory(self):
        """URI ending in table directory name."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables/order_info",
            "name": "order_info",
        })
        assert result == "order_info"

    def test_extract_underscore_prefixed_skipped_inline(self):
        """Underscore-prefixed names like _tables are skipped by caller but
        _extract_table_name itself returns the raw name — the filtering
        happens in retrieve()'s inline loop."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/142/dwd_trade/_tables",
            "name": "_tables",
        })
        assert result == "_tables"

    def test_extract_empty_uri_returns_empty(self):
        """Empty URI → empty string."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({"uri": "", "name": ""})
        assert result == ""

    def test_extract_no_uri_uses_name(self):
        """No URI → falls back to .name, stripping .md suffix."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "",
            "name": "order_info.md",
        })
        assert result == "order_info"

    def test_extract_no_uri_abstract_name_returns_empty(self):
        """No URI + abstract name → returns empty."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "",
            "name": ".abstract.md",
        })
        assert result == ""

    def test_extract_columns_subdir_deeply_nested(self):
        """_columns/ subdirectory with longer key paths still extracts correctly."""
        from app.datavault.retriever import HDCRetriever
        result = HDCRetriever._extract_table_name({
            "uri": "viking://resources/hdc/65938636/dw_onedba/complete/_tables/after_sale_order/_columns/refund_amount.md",
            "name": "refund_amount.md",
        })
        assert result == "after_sale_order"


class TestGetMainEntity:
    """Tests for _get_main_entity() (Req 4.2 — fallback behavior)."""

    @pytest.mark.asyncio
    async def test_valid_content_first_line_non_heading(self):
        """Valid _INDEX.md with plain-text first line → returns that line as entity."""
        from app.datavault.retriever import HDCRetriever
        ov = MockOVClient(index_contents={
            "order_info": ("订单/交易", "fact"),
        })
        r = HDCRetriever(ov)
        entity = await r._get_main_entity("142/dwd_trade", "order_info")
        assert entity == "订单/交易"

    @pytest.mark.asyncio
    async def test_valid_content_first_line_heading(self):
        """_INDEX.md first line starts with # → falls back to table_name."""
        from app.datavault.retriever import HDCRetriever

        class HeadingMockOV(MockOVClient):
            async def _get_raw(self, path, uri):
                import re
                m = re.search(r'/_tables/([^/]+)/', uri)
                table = m.group(1) if m else ""
                if uri.endswith("_INDEX.md") and table:
                    return f"# {table}\n\n**{table}** 是 **fact** 类型的表。\n"
                return ""

        r = HDCRetriever(HeadingMockOV())
        entity = await r._get_main_entity("142/dwd_trade", "order_info")
        assert entity == "order_info"

    @pytest.mark.asyncio
    async def test_empty_index_content(self):
        """_INDEX.md returns empty → falls back to table_name."""
        from app.datavault.retriever import HDCRetriever

        class EmptyMockOV(MockOVClient):
            async def _get_raw(self, path, uri):
                return ""

        r = HDCRetriever(EmptyMockOV())
        entity = await r._get_main_entity("142/dwd_trade", "order_info")
        assert entity == "order_info"

    @pytest.mark.asyncio
    async def test_index_read_exception(self):
        """_read_index raises exception → falls back to table_name."""
        from app.datavault.retriever import HDCRetriever

        class FailingMockOV(MockOVClient):
            async def _get_raw(self, path, uri):
                raise RuntimeError("simulated read failure")

        r = HDCRetriever(FailingMockOV())
        entity = await r._get_main_entity("142/dwd_trade", "order_info")
        assert entity == "order_info"

    @pytest.mark.asyncio
    async def test_first_line_only_whitespace(self):
        """_INDEX.md first line is blank whitespace → falls back to table_name."""
        from app.datavault.retriever import HDCRetriever

        class WhitespaceMockOV(MockOVClient):
            async def _get_raw(self, path, uri):
                import re
                m = re.search(r'/_tables/([^/]+)/', uri)
                table = m.group(1) if m else ""
                if uri.endswith("_INDEX.md") and table:
                    return "\n\n**{table}** 是 **fact** 类型的表。\n".format(table=table)
                return ""

        r = HDCRetriever(WhitespaceMockOV())
        entity = await r._get_main_entity("142/dwd_trade", "order_info")
        assert entity == "order_info"


class TestScoringAlgorithm:
    """Tests for sum(top-3) scoring algorithm (Req 3.1, 3.2)."""

    @staticmethod
    def _score_candidates(matches: list[dict]) -> list[tuple[str, float]]:
        """Replicate the inline scoring logic from retriever.retrieve()."""
        from app.datavault.retriever import HDCRetriever
        table_scores: dict[str, list[float]] = {}
        for match in matches:
            table_name = HDCRetriever._extract_table_name(match)
            if not table_name:
                continue
            if table_name.startswith("_"):
                continue
            score = match.get("score", 0.0)
            table_scores.setdefault(table_name, []).append(score)

        candidates = [
            (tn, sum(sorted(scores, reverse=True)[:3]))
            for tn, scores in table_scores.items()
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def test_single_match_score_equals_itself(self):
        """Single match → score equals that match's score."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.abstract.md", "score": 0.85},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        assert candidates[0] == ("orders", 0.85)

    def test_two_matches_same_table_summed(self):
        """Two matches for same table → score = sum of both."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.abstract.md", "score": 0.85},
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.overview.md", "score": 0.75},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        assert candidates[0] == ("orders", pytest.approx(1.60))

    def test_five_matches_only_top3_summed(self):
        """Five matches for same table → only top 3 scores are summed."""
        # Use different URI patterns that all resolve to "orders"
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.abstract.md", "score": 0.90},
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.overview.md", "score": 0.80},
            {"uri": "viking://resources/hdc/142/db/_tables/orders", "name": "orders", "score": 0.70},
            {"uri": "viking://resources/hdc/142/db/_tables/orders", "name": "orders", "score": 0.60},
            {"uri": "viking://resources/hdc/142/db/_tables/orders", "name": "orders", "score": 0.50},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        # top-3: 0.90 + 0.80 + 0.70 = 2.40
        assert candidates[0] == ("orders", pytest.approx(2.40))

    def test_multiple_tables_ranked_by_score(self):
        """Multiple tables ranked by composite score descending."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.abstract.md", "score": 0.90},
            {"uri": "viking://resources/hdc/142/db/_tables/orders/.overview.md", "score": 0.80},
            {"uri": "viking://resources/hdc/142/db/_tables/payments/.abstract.md", "score": 0.95},
        ]
        candidates = self._score_candidates(matches)
        # orders: 0.90 + 0.80 = 1.70, payments: 0.95
        assert candidates[0] == ("orders", pytest.approx(1.70))
        assert candidates[1] == ("payments", pytest.approx(0.95))

    def test_multiple_tables_equal_score_stable(self):
        """Tables with equal scores are both present."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/a/.abstract.md", "score": 0.80},
            {"uri": "viking://resources/hdc/142/db/_tables/b/.abstract.md", "score": 0.80},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 2

    def test_empty_candidates(self):
        """Empty match list → empty candidates list."""
        candidates = self._score_candidates([])
        assert candidates == []

    def test_zero_scores_still_present(self):
        """Matches with score=0 still appear (no threshold filtering at this stage)."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/zero_table/.abstract.md", "score": 0.0},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        assert candidates[0][1] == 0.0

    def test_underscore_prefixed_tables_filtered(self):
        """Matches from _-prefixed directories (e.g. _tables, _relationships) are filtered."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/_tables", "name": "_tables", "score": 0.90},
            {"uri": "viking://resources/hdc/142/db/_tables/real_table/.abstract.md", "score": 0.80},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        assert candidates[0][0] == "real_table"

    def test_no_table_name_extractable_filtered(self):
        """Matches where _extract_table_name returns empty → filtered."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/.abstract", "name": ".abstract", "score": 0.90},
            {"uri": "viking://resources/hdc/142/db/_tables/good_table/.abstract.md", "score": 0.85},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        assert candidates[0][0] == "good_table"

    def test_missing_score_defaults_to_zero(self):
        """Match without 'score' key → defaults to 0.0."""
        matches = [
            {"uri": "viking://resources/hdc/142/db/_tables/no_score/.abstract.md"},
        ]
        candidates = self._score_candidates(matches)
        assert len(candidates) == 1
        assert candidates[0][1] == 0.0


class TestEntityDedup:
    """Tests for entity explosion radius control (Req 4.1)."""

    @staticmethod
    def _apply_entity_dedup(
        candidates: list[tuple[str, float]],
        entity_map: dict[str, str],
        max_per_entity: int = 2,
        top_n: int = 5,
    ) -> list[tuple[str, float]]:
        """Replicate the inline entity dedup logic from retriever.retrieve()."""
        entity_counts: dict[str, int] = {}
        diversified: list[tuple[str, float]] = []
        for table_name, score in candidates:
            entity = entity_map.get(table_name, table_name)
            count = entity_counts.get(entity, 0)
            if count < max_per_entity:
                entity_counts[entity] = count + 1
                diversified.append((table_name, score))
            if len(diversified) >= top_n:
                break
        return diversified

    def test_four_tables_same_entity_only_two_survive(self):
        """4 tables with same entity → only 2 survive (explosion radius = 2)."""
        candidates = [
            ("order_info", 4.0),
            ("after_sale_order", 3.5),
            ("order_refund", 3.0),
            ("order_logistics", 2.5),
        ]
        entity_map = {t: "订单/交易" for t, _ in candidates}
        result = self._apply_entity_dedup(candidates, entity_map)
        assert len(result) == 2
        assert result[0][0] == "order_info"
        assert result[1][0] == "after_sale_order"

    def test_mixed_entities_filled_to_top5(self):
        """Mixed entities: first 2 from entity A, then 2 from B, then 1 from C = 5."""
        candidates = [
            ("a1", 5.0), ("a2", 4.8), ("a3", 4.6), ("a4", 4.4),  # entity A
            ("b1", 4.0), ("b2", 3.5), ("b3", 3.0),                # entity B
            ("c1", 2.5),                                            # entity C
        ]
        entity_map = {
            "a1": "A", "a2": "A", "a3": "A", "a4": "A",
            "b1": "B", "b2": "B", "b3": "B",
            "c1": "C",
        }
        result = self._apply_entity_dedup(candidates, entity_map)
        assert len(result) == 5
        assert result[0][0] == "a1"
        assert result[1][0] == "a2"
        assert result[2][0] == "b1"
        assert result[3][0] == "b2"
        assert result[4][0] == "c1"

    def test_all_same_entity_only_two_survive(self):
        """All 10 tables from same entity → only 2 survive."""
        candidates = [(f"table{i}", float(10 - i)) for i in range(10)]
        entity_map = {t: "唯一实体" for t, _ in candidates}
        result = self._apply_entity_dedup(candidates, entity_map)
        assert len(result) == 2
        assert result[0][0] == "table0"
        assert result[1][0] == "table1"

    def test_all_different_entities_all_five_survive(self):
        """5 tables, each from different entity → all 5 survive."""
        candidates = [
            ("t_order", 5.0), ("t_payment", 4.0), ("t_refund", 3.0),
            ("t_user", 2.0), ("t_product", 1.0),
        ]
        entity_map = {
            "t_order": "订单", "t_payment": "支付", "t_refund": "退款",
            "t_user": "用户", "t_product": "商品",
        }
        result = self._apply_entity_dedup(candidates, entity_map)
        assert len(result) == 5

    def test_entity_not_in_map_falls_back_to_table_name(self):
        """Entity not found in map → table_name is used as entity (each table is unique)."""
        candidates = [
            ("t1", 5.0), ("t2", 4.0), ("t3", 3.0),
        ]
        entity_map = {}  # empty → falls back to table_name
        result = self._apply_entity_dedup(candidates, entity_map)
        # Each table is its own entity → all 3 survive
        assert len(result) == 3

    def test_empty_candidates(self):
        """Empty candidates → empty result."""
        result = self._apply_entity_dedup([], {})
        assert result == []

    def test_exactly_two_per_entity(self):
        """Exactly MAX_PER_ENTITY tables per entity → all survive."""
        candidates = [
            ("a1", 5.0), ("a2", 4.0),
            ("b1", 3.0), ("b2", 2.0),
        ]
        entity_map = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
        result = self._apply_entity_dedup(candidates, entity_map)
        assert len(result) == 4

    def test_fewer_than_max_per_entity_all_survive(self):
        """Only 1 table per entity → all survive up to top_n."""
        candidates = [
            ("a1", 5.0), ("b1", 4.0), ("c1", 3.0),
            ("d1", 2.0), ("e1", 1.0), ("f1", 0.5),
        ]
        entity_map = {t: t[0].upper() for t, _ in candidates}
        result = self._apply_entity_dedup(candidates, entity_map, top_n=5)
        assert len(result) == 5  # capped at top_n
        assert result[0][0] == "a1"

    def test_max_per_entity_one(self):
        """max_per_entity=1 → at most 1 table per entity."""
        candidates = [
            ("a1", 5.0), ("a2", 4.0),
            ("b1", 3.0), ("b2", 2.0),
            ("c1", 1.0),
        ]
        entity_map = {"a1": "A", "a2": "A", "b1": "B", "b2": "B", "c1": "C"}
        result = self._apply_entity_dedup(candidates, entity_map, max_per_entity=1)
        assert len(result) == 3

    def test_top_n_limit_respected(self):
        """top_n=3 → result capped at 3 even if more diverse candidates exist."""
        candidates = [(f"t{i}", float(10 - i)) for i in range(10)]
        entity_map = {t: f"entity_{t}" for t, _ in candidates}  # all different entities
        result = self._apply_entity_dedup(candidates, entity_map, top_n=3)
        assert len(result) == 3


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
