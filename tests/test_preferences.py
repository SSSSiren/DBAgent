"""
SqlitePreferenceStore 单元测试

测试 SqlitePreferenceStore 的完整 CRUD 行为，使用 :memory: SQLite 数据库。
覆盖记录查询、LRU 淘汰、偏好检索、用户隔离、工厂单例等。
"""

import pytest
import pytest_asyncio
from unittest.mock import patch

from app.memory.preferences import (
    SqlitePreferenceStore,
    QueryPreferenceStore,
    InMemoryPreferenceStore,
    get_preference_store,
    reset_preference_store,
)
from app.config import Settings


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def store():
    """创建 SqlitePreferenceStore 实例并初始化（使用 :memory: 数据库）"""
    s = SqlitePreferenceStore(":memory:")
    await s.initialize()
    yield s
    await s.close()


async def _record_batch(store, user_id, tables, db="test_db", schema_id=1):
    """辅助函数：批量记录查询偏好"""
    for t in tables:
        await store.record_query(user_id, t, db, schema_id)


# ── record_query 测试 ─────────────────────────────────────────────────

class TestRecordQuery:
    """测试 record_query 方法"""

    @pytest.mark.asyncio
    async def test_new_record_creates_with_query_count_one(self, store):
        """新记录应创建 query_count=1 的行"""
        await store.record_query("user1", "orders", "mydb", 1)

        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["table_name"] == "orders"
        assert prefs[0]["database_name"] == "mydb"
        assert prefs[0]["query_count"] == 1

    @pytest.mark.asyncio
    async def test_repeat_record_increments_query_count(self, store):
        """同一用户重复查询同一张表，query_count 递增"""
        await store.record_query("user1", "orders", "mydb", 1)
        await store.record_query("user1", "orders", "mydb", 1)

        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["query_count"] == 2

        # 第三次确认持续递增
        await store.record_query("user1", "orders", "mydb", 1)
        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert prefs[0]["query_count"] == 3

    @pytest.mark.asyncio
    async def test_user_id_isolation(self, store):
        """不同 user_id 的记录互相隔离"""
        await store.record_query("user1", "orders", "mydb", 1)
        await store.record_query("user2", "orders", "mydb", 1)

        # user1 和 user2 各有自己的记录
        prefs_u1 = await store.retrieve_top_preferences("user1", limit=10)
        prefs_u2 = await store.retrieve_top_preferences("user2", limit=10)
        assert len(prefs_u1) == 1
        assert len(prefs_u2) == 1

        # 两个用户的查询次数互相独立
        await store.record_query("user1", "orders", "mydb", 1)
        prefs_u1 = await store.retrieve_top_preferences("user1", limit=10)
        prefs_u2 = await store.retrieve_top_preferences("user2", limit=10)
        assert prefs_u1[0]["query_count"] == 2
        assert prefs_u2[0]["query_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_user_id_returns_early(self, store):
        """空 user_id 应直接返回，不创建记录"""
        await store.record_query("", "orders", "mydb", 1)
        prefs = await store.retrieve_top_preferences("", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_empty_table_name_returns_early(self, store):
        """空 table_name 应直接返回，不创建记录"""
        await store.record_query("user1", "", "mydb", 1)
        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_empty_database_name_returns_early(self, store):
        """空 database_name 应直接返回，不创建记录"""
        await store.record_query("user1", "orders", "", 1)
        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_different_databases_same_table_independent(self, store):
        """同一表名在不同数据库中应独立记录"""
        await store.record_query("user1", "orders", "db_a", 1)
        await store.record_query("user1", "orders", "db_b", 1)

        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 2
        db_names = {p["database_name"] for p in prefs}
        assert db_names == {"db_a", "db_b"}

    @pytest.mark.asyncio
    async def test_schema_id_stored_correctly(self, store):
        """schema_id 应正确存储"""
        await store.record_query("user1", "orders", "mydb", 42)
        prefs = await store.retrieve_top_preferences("user1", limit=10)
        assert prefs[0]["schema_id"] == 42

    @pytest.mark.asyncio
    async def test_last_query_at_updated_on_repeat(self, store):
        """重复查询时应更新 last_query_at"""
        await store.record_query("user1", "orders", "mydb", 1)
        prefs_before = await store.retrieve_top_preferences("user1", limit=10)
        first_ts = prefs_before[0]["last_query_at"]

        # 短暂等待确保时间戳不同
        import asyncio
        await asyncio.sleep(0.01)

        await store.record_query("user1", "orders", "mydb", 1)
        prefs_after = await store.retrieve_top_preferences("user1", limit=10)
        second_ts = prefs_after[0]["last_query_at"]

        assert second_ts != first_ts


# ── LRU 淘汰测试 ──────────────────────────────────────────────────────

class TestLRUEviction:
    """测试 LRU 淘汰策略（默认上限 DEFAULT_MAX_PER_USER=50）"""

    @pytest.mark.asyncio
    async def test_evicts_least_used_when_over_limit(self, store):
        """超过上限时应淘汰 query_count 最小的记录"""
        # 插入 50 条记录（达到默认上限）
        for i in range(50):
            await store.record_query("user1", f"table_{i:03d}", "mydb", 1)

        # 将 table_000 查询次数提升到 6，使其不会被淘汰
        for _ in range(5):
            await store.record_query("user1", "table_000", "mydb", 1)
        # table_000 现在 query_count = 6

        # 插入第 51 条不同的表，应触发淘汰
        await store.record_query("user1", "new_table", "mydb", 1)

        prefs = await store.retrieve_top_preferences("user1", limit=100)
        table_names = {p["table_name"] for p in prefs}

        # 新表应在
        assert "new_table" in table_names
        # table_000（高频）不应被淘汰
        assert "table_000" in table_names
        # 总数应为 50（淘汰了 1 条 query_count=1 的记录）
        assert len(prefs) == 50

    @pytest.mark.asyncio
    async def test_existing_update_no_eviction(self, store):
        """更新已有记录不触发淘汰检查"""
        # 插入 50 条记录达到上限
        for i in range(50):
            await store.record_query("user1", f"table_{i:03d}", "mydb", 1)

        # 更新已存在的记录，不应触发淘汰
        await store.record_query("user1", "table_000", "mydb", 1)

        prefs = await store.retrieve_top_preferences("user1", limit=100)
        # 应仍有 50 条记录（无淘汰发生）
        assert len(prefs) == 50
        # table_000 的 query_count 应为 2
        t000 = [p for p in prefs if p["table_name"] == "table_000"][0]
        assert t000["query_count"] == 2

    @pytest.mark.asyncio
    async def test_eviction_respects_user_isolation(self, store):
        """淘汰仅影响触发淘汰的用户，不影响其他用户"""
        # user1 达到上限
        for i in range(50):
            await store.record_query("user1", f"t1_{i:03d}", "mydb", 1)
        # user2 只有 5 条记录
        for i in range(5):
            await store.record_query("user2", f"t2_{i:03d}", "mydb", 1)

        # user1 触发淘汰
        await store.record_query("user1", "new_table", "mydb", 1)

        # user2 的记录不应受影响
        prefs_u2 = await store.retrieve_top_preferences("user2", limit=100)
        assert len(prefs_u2) == 5


# ── retrieve_preferences 测试 ─────────────────────────────────────────

class TestRetrievePreferences:
    """测试 retrieve_preferences 方法"""

    @pytest.mark.asyncio
    async def test_exact_keyword_match(self, store):
        """精确关键词匹配应返回对应记录"""
        await _record_batch(store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")

        results = await store.retrieve_preferences("user1", "order_info")
        assert len(results) >= 1
        assert results[0]["table_name"] == "order_info"

    @pytest.mark.asyncio
    async def test_partial_match(self, store):
        """部分匹配（LIKE %keyword%）应返回包含关键词的记录"""
        await _record_batch(store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")

        # "order" 应 LIKE 匹配 order_info
        results = await store.retrieve_preferences("user1", "order")
        assert len(results) >= 1
        table_names = {r["table_name"] for r in results}
        assert "order_info" in table_names

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, store):
        """无任何匹配时应返回空列表"""
        await _record_batch(store, "user1", ["order_info", "user_profile"], "mydb")

        results = await store.retrieve_preferences("user1", "nonexistent_xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_results_sorted_by_query_count_desc(self, store):
        """结果应按 query_count 降序排列"""
        await _record_batch(store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")
        # order_info 查询 2 次额外 → query_count=3
        await store.record_query("user1", "order_info", "mydb", 1)
        await store.record_query("user1", "order_info", "mydb", 1)
        # user_profile 查询 1 次额外 → query_count=2
        await store.record_query("user1", "user_profile", "mydb", 1)
        # payment_log → query_count=1

        # 所有表名包含 "_" → 三个都匹配
        results = await store.retrieve_preferences("user1", "info profile log")
        assert len(results) == 3
        assert results[0]["table_name"] == "order_info"
        assert results[1]["table_name"] == "user_profile"
        assert results[2]["table_name"] == "payment_log"
        assert results[0]["query_count"] >= results[1]["query_count"] >= results[2]["query_count"]

    @pytest.mark.asyncio
    async def test_limit_respected(self, store):
        """limit 参数应生效"""
        for i in range(10):
            await store.record_query("user1", f"table_{i}", "mydb", 1)

        results = await store.retrieve_preferences("user1", "table", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_keywords_falls_back_to_top(self, store):
        """空关键词应回退到 retrieve_top_preferences"""
        await _record_batch(store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")

        results = await store.retrieve_preferences("user1", "")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_whitespace_only_keywords_falls_back(self, store):
        """仅空白字符的关键词应回退到 retrieve_top_preferences"""
        await _record_batch(store, "user1", ["order_info", "user_profile"], "mydb")

        results = await store.retrieve_preferences("user1", "   ")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_database_name_match(self, store):
        """关键词也应匹配 database_name"""
        await store.record_query("user1", "orders", "ecommerce_db", 1)
        await store.record_query("user1", "users", "analytics_db", 1)

        results = await store.retrieve_preferences("user1", "ecommerce")
        assert len(results) == 1
        assert results[0]["table_name"] == "orders"

    @pytest.mark.asyncio
    async def test_multiple_keywords_union_match(self, store):
        """多个关键词应使用 OR 语义匹配"""
        await store.record_query("user1", "order_info", "mydb", 1)
        await store.record_query("user1", "user_profile", "mydb", 1)
        await store.record_query("user1", "payment_log", "other_db", 1)

        # "order" 匹配 order_info，"other" 匹配 other_db → payment_log
        results = await store.retrieve_preferences("user1", "order other")
        assert len(results) == 2
        table_names = {r["table_name"] for r in results}
        assert table_names == {"order_info", "payment_log"}

    @pytest.mark.asyncio
    async def test_chinese_punctuation_tokenization(self, store):
        """中文标点应正确分词"""
        await store.record_query("user1", "order_info", "mydb", 1)
        await store.record_query("user1", "user_profile", "mydb", 1)

        # 中文逗号、句号等标点分词
        results = await store.retrieve_preferences("user1", "order_info，user_profile")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_user_isolation_in_retrieval(self, store):
        """检索结果应仅包含当前用户的数据"""
        await store.record_query("user1", "orders", "mydb", 1)
        await store.record_query("user2", "orders", "mydb", 1)
        # user2 的 orders 查询次数更高
        await store.record_query("user2", "orders", "mydb", 1)

        results_u1 = await store.retrieve_preferences("user1", "orders")
        assert len(results_u1) == 1
        # user1 的 query_count 应为 1，不受 user2 影响
        assert results_u1[0]["query_count"] == 1

        results_u2 = await store.retrieve_preferences("user2", "orders")
        assert len(results_u2) == 1
        assert results_u2[0]["query_count"] == 2


# ── retrieve_top_preferences 测试 ─────────────────────────────────────

class TestRetrieveTopPreferences:
    """测试 retrieve_top_preferences 方法"""

    @pytest.mark.asyncio
    async def test_returns_top_tables_sorted(self, store):
        """应返回按 query_count 降序排列的偏好表"""
        await _record_batch(store, "user1", ["table_a", "table_b", "table_c"], "mydb")
        await store.record_query("user1", "table_b", "mydb", 1)
        await store.record_query("user1", "table_b", "mydb", 1)
        await store.record_query("user1", "table_c", "mydb", 1)

        # table_b: 3, table_c: 2, table_a: 1
        results = await store.retrieve_top_preferences("user1", limit=10)
        assert len(results) == 3
        assert results[0]["table_name"] == "table_b"
        assert results[1]["table_name"] == "table_c"
        assert results[2]["table_name"] == "table_a"

    @pytest.mark.asyncio
    async def test_new_user_returns_empty(self, store):
        """新用户（无任何记录）应返回空列表"""
        results = await store.retrieve_top_preferences("new_user")
        assert results == []
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_limit_respected(self, store):
        """limit 参数应生效"""
        for i in range(10):
            await store.record_query("user1", f"table_{i}", "mydb", 1)

        results = await store.retrieve_top_preferences("user1", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_default_limit_is_five(self, store):
        """默认 limit=5"""
        for i in range(10):
            await store.record_query("user1", f"table_{i}", "mydb", 1)

        results = await store.retrieve_top_preferences("user1")
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_returns_all_when_fewer_than_limit(self, store):
        """记录数少于 limit 时返回全部"""
        await _record_batch(store, "user1", ["table_a", "table_b"], "mydb")

        results = await store.retrieve_top_preferences("user1", limit=10)
        assert len(results) == 2


# ── 工厂函数测试 ──────────────────────────────────────────────────────

class TestFactoryFunctions:
    """测试 get_preference_store 和 reset_preference_store"""

    def test_get_preference_store_returns_singleton(self):
        """get_preference_store 应返回同一实例（进程级单例）"""
        reset_preference_store()

        with patch("app.memory.preferences.get_settings") as mock_settings:
            mock_settings.return_value = Settings(storage_file_path=":memory:")

            store1 = get_preference_store()
            store2 = get_preference_store()
            assert store1 is store2

    def test_reset_preference_store_creates_new_instance(self):
        """reset 后 get 应返回新实例"""
        reset_preference_store()

        with patch("app.memory.preferences.get_settings") as mock_settings:
            mock_settings.return_value = Settings(storage_file_path=":memory:")

            store1 = get_preference_store()
            reset_preference_store()
            store2 = get_preference_store()
            assert store1 is not store2


# ── 初始化和生命周期测试 ──────────────────────────────────────────────

class TestInitialization:
    """测试 initialize 和 close 生命周期"""

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, store):
        """initialize 后表应存在且可写入"""
        await store.record_query("user1", "orders", "mydb", 1)
        prefs = await store.retrieve_top_preferences("user1")
        assert len(prefs) == 1

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, store):
        """重复 initialize 不应报错"""
        # store fixture 已经 initialize 过一次
        await store.initialize()
        # 应仍能正常操作
        await store.record_query("user1", "orders", "mydb", 1)
        prefs = await store.retrieve_top_preferences("user1")
        assert len(prefs) == 1

    @pytest.mark.asyncio
    async def test_close_disables_operations(self):
        """close 后 _conn 置为 None，后续操作应抛出异常"""
        s = SqlitePreferenceStore(":memory:")
        await s.initialize()
        await s.close()

        with pytest.raises(Exception):
            await s.record_query("user1", "orders", "mydb", 1)

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """重复 close 不应报错"""
        s = SqlitePreferenceStore(":memory:")
        await s.initialize()
        await s.close()
        await s.close()  # 第二次 close 应是安全的


# ============================================================================
# InMemoryPreferenceStore 测试
# ============================================================================

@pytest_asyncio.fixture
async def mem_store():
    """创建 InMemoryPreferenceStore 实例并初始化"""
    s = InMemoryPreferenceStore()
    await s.initialize()
    yield s
    await s.close()


async def _mem_record_batch(store, user_id, tables, db="test_db", schema_id=1):
    """辅助函数：批量记录查询偏好（内存版本）"""
    for t in tables:
        await store.record_query(user_id, t, db, schema_id)


class TestInMemoryRecordQuery:
    """测试 InMemoryPreferenceStore.record_query 方法"""

    @pytest.mark.asyncio
    async def test_new_record_creates_with_query_count_one(self, mem_store):
        """新记录应创建 query_count=1 的行"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["table_name"] == "orders"
        assert prefs[0]["database_name"] == "mydb"
        assert prefs[0]["query_count"] == 1
        assert prefs[0]["schema_id"] == 1

    @pytest.mark.asyncio
    async def test_repeat_record_increments_query_count(self, mem_store):
        """同一用户重复查询同一张表，query_count 递增"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["query_count"] == 2

        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert prefs[0]["query_count"] == 3

    @pytest.mark.asyncio
    async def test_user_id_isolation(self, mem_store):
        """不同 user_id 的记录互相隔离"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        await mem_store.record_query("user2", "orders", "mydb", 1)

        prefs_u1 = await mem_store.retrieve_top_preferences("user1", limit=10)
        prefs_u2 = await mem_store.retrieve_top_preferences("user2", limit=10)
        assert len(prefs_u1) == 1
        assert len(prefs_u2) == 1

        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs_u1 = await mem_store.retrieve_top_preferences("user1", limit=10)
        prefs_u2 = await mem_store.retrieve_top_preferences("user2", limit=10)
        assert prefs_u1[0]["query_count"] == 2
        assert prefs_u2[0]["query_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_user_id_returns_early(self, mem_store):
        """空 user_id 应直接返回，不创建记录"""
        await mem_store.record_query("", "orders", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_empty_table_name_returns_early(self, mem_store):
        """空 table_name 应直接返回，不创建记录"""
        await mem_store.record_query("user1", "", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_empty_database_name_returns_early(self, mem_store):
        """空 database_name 应直接返回，不创建记录"""
        await mem_store.record_query("user1", "orders", "", 1)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_different_databases_same_table_independent(self, mem_store):
        """同一表名在不同数据库中应独立记录"""
        await mem_store.record_query("user1", "orders", "db_a", 1)
        await mem_store.record_query("user1", "orders", "db_b", 1)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(prefs) == 2
        db_names = {p["database_name"] for p in prefs}
        assert db_names == {"db_a", "db_b"}

    @pytest.mark.asyncio
    async def test_schema_id_stored_correctly(self, mem_store):
        """schema_id 应正确存储"""
        await mem_store.record_query("user1", "orders", "mydb", 42)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert prefs[0]["schema_id"] == 42

    @pytest.mark.asyncio
    async def test_schema_id_updated_on_repeat(self, mem_store):
        """重复查询时 schema_id 应更新为最新值"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        await mem_store.record_query("user1", "orders", "mydb", 99)
        prefs = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert prefs[0]["schema_id"] == 99

    @pytest.mark.asyncio
    async def test_last_query_at_updated_on_repeat(self, mem_store):
        """重复查询时应更新 last_query_at"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs_before = await mem_store.retrieve_top_preferences("user1", limit=10)
        first_ts = prefs_before[0]["last_query_at"]

        import asyncio
        await asyncio.sleep(0.01)

        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs_after = await mem_store.retrieve_top_preferences("user1", limit=10)
        second_ts = prefs_after[0]["last_query_at"]

        assert second_ts != first_ts


class TestInMemoryLRUEviction:
    """测试 InMemoryPreferenceStore LRU 淘汰策略"""

    @pytest.mark.asyncio
    async def test_evicts_least_used_when_over_limit(self, mem_store):
        """超过上限时应淘汰 query_count 最小的记录"""
        for i in range(50):
            await mem_store.record_query("user1", f"table_{i:03d}", "mydb", 1)

        # 提升 table_000 到 query_count=6
        for _ in range(5):
            await mem_store.record_query("user1", "table_000", "mydb", 1)

        # 插入第 51 条，触发淘汰
        await mem_store.record_query("user1", "new_table", "mydb", 1)

        prefs = await mem_store.retrieve_top_preferences("user1", limit=100)
        table_names = {p["table_name"] for p in prefs}

        assert "new_table" in table_names
        assert "table_000" in table_names
        assert len(prefs) == 50

    @pytest.mark.asyncio
    async def test_existing_update_no_eviction(self, mem_store):
        """更新已有记录不触发淘汰检查"""
        for i in range(50):
            await mem_store.record_query("user1", f"table_{i:03d}", "mydb", 1)

        await mem_store.record_query("user1", "table_000", "mydb", 1)

        prefs = await mem_store.retrieve_top_preferences("user1", limit=100)
        assert len(prefs) == 50
        t000 = [p for p in prefs if p["table_name"] == "table_000"][0]
        assert t000["query_count"] == 2

    @pytest.mark.asyncio
    async def test_eviction_respects_user_isolation(self, mem_store):
        """淘汰仅影响触发淘汰的用户"""
        for i in range(50):
            await mem_store.record_query("user1", f"t1_{i:03d}", "mydb", 1)
        for i in range(5):
            await mem_store.record_query("user2", f"t2_{i:03d}", "mydb", 1)

        await mem_store.record_query("user1", "new_table", "mydb", 1)

        prefs_u2 = await mem_store.retrieve_top_preferences("user2", limit=100)
        assert len(prefs_u2) == 5

    @pytest.mark.asyncio
    async def test_eviction_prefers_older_when_same_count(self, mem_store):
        """当 query_count 相同时，应淘汰 last_query_at 更早的记录"""
        for i in range(50):
            await mem_store.record_query("user1", f"table_{i:03d}", "mydb", 1)

        # 提升 table_000 到 query_count=2
        await mem_store.record_query("user1", "table_000", "mydb", 1)
        # table_000 的 last_query_at 被更新

        # 提升 table_001 到 query_count=2（更新更晚）
        import asyncio
        await asyncio.sleep(0.01)
        await mem_store.record_query("user1", "table_001", "mydb", 1)

        # 插入第 51 条，所有 query_count=1 的记录中，淘汰 last_query_at 最早的
        await mem_store.record_query("user1", "new_table", "mydb", 1)

        prefs = await mem_store.retrieve_top_preferences("user1", limit=100)
        assert len(prefs) == 50
        assert "new_table" in {p["table_name"] for p in prefs}


class TestInMemoryRetrievePreferences:
    """测试 InMemoryPreferenceStore.retrieve_preferences 方法"""

    @pytest.mark.asyncio
    async def test_exact_keyword_match(self, mem_store):
        """精确关键词匹配应返回对应记录"""
        await _mem_record_batch(mem_store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")
        results = await mem_store.retrieve_preferences("user1", "order_info")
        assert len(results) >= 1
        assert results[0]["table_name"] == "order_info"

    @pytest.mark.asyncio
    async def test_partial_match(self, mem_store):
        """部分匹配应返回包含关键词的记录"""
        await _mem_record_batch(mem_store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")
        results = await mem_store.retrieve_preferences("user1", "order")
        assert len(results) >= 1
        table_names = {r["table_name"] for r in results}
        assert "order_info" in table_names

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, mem_store):
        """无任何匹配时应返回空列表"""
        await _mem_record_batch(mem_store, "user1", ["order_info", "user_profile"], "mydb")
        results = await mem_store.retrieve_preferences("user1", "nonexistent_xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_results_sorted_by_query_count_desc(self, mem_store):
        """结果应按 query_count 降序排列"""
        await _mem_record_batch(mem_store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")
        await mem_store.record_query("user1", "order_info", "mydb", 1)
        await mem_store.record_query("user1", "order_info", "mydb", 1)
        await mem_store.record_query("user1", "user_profile", "mydb", 1)

        results = await mem_store.retrieve_preferences("user1", "info profile log")
        assert len(results) == 3
        assert results[0]["table_name"] == "order_info"
        assert results[1]["table_name"] == "user_profile"
        assert results[2]["table_name"] == "payment_log"
        assert results[0]["query_count"] >= results[1]["query_count"] >= results[2]["query_count"]

    @pytest.mark.asyncio
    async def test_limit_respected(self, mem_store):
        """limit 参数应生效"""
        for i in range(10):
            await mem_store.record_query("user1", f"table_{i}", "mydb", 1)
        results = await mem_store.retrieve_preferences("user1", "table", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_keywords_falls_back_to_top(self, mem_store):
        """空关键词应回退到 retrieve_top_preferences"""
        await _mem_record_batch(mem_store, "user1", ["order_info", "user_profile", "payment_log"], "mydb")
        results = await mem_store.retrieve_preferences("user1", "")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_whitespace_only_keywords_falls_back(self, mem_store):
        """仅空白字符的关键词应回退到 retrieve_top_preferences"""
        await _mem_record_batch(mem_store, "user1", ["order_info", "user_profile"], "mydb")
        results = await mem_store.retrieve_preferences("user1", "   ")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_database_name_match(self, mem_store):
        """关键词也应匹配 database_name"""
        await mem_store.record_query("user1", "orders", "ecommerce_db", 1)
        await mem_store.record_query("user1", "users", "analytics_db", 1)
        results = await mem_store.retrieve_preferences("user1", "ecommerce")
        assert len(results) == 1
        assert results[0]["table_name"] == "orders"

    @pytest.mark.asyncio
    async def test_multiple_keywords_union_match(self, mem_store):
        """多个关键词应使用 OR 语义匹配"""
        await mem_store.record_query("user1", "order_info", "mydb", 1)
        await mem_store.record_query("user1", "user_profile", "mydb", 1)
        await mem_store.record_query("user1", "payment_log", "other_db", 1)
        results = await mem_store.retrieve_preferences("user1", "order other")
        assert len(results) == 2
        table_names = {r["table_name"] for r in results}
        assert table_names == {"order_info", "payment_log"}

    @pytest.mark.asyncio
    async def test_chinese_punctuation_tokenization(self, mem_store):
        """中文标点应正确分词"""
        await mem_store.record_query("user1", "order_info", "mydb", 1)
        await mem_store.record_query("user1", "user_profile", "mydb", 1)
        results = await mem_store.retrieve_preferences("user1", "order_info，user_profile")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_user_isolation_in_retrieval(self, mem_store):
        """检索结果应仅包含当前用户的数据"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        await mem_store.record_query("user2", "orders", "mydb", 1)
        await mem_store.record_query("user2", "orders", "mydb", 1)

        results_u1 = await mem_store.retrieve_preferences("user1", "orders")
        assert len(results_u1) == 1
        assert results_u1[0]["query_count"] == 1

        results_u2 = await mem_store.retrieve_preferences("user2", "orders")
        assert len(results_u2) == 1
        assert results_u2[0]["query_count"] == 2


class TestInMemoryRetrieveTopPreferences:
    """测试 InMemoryPreferenceStore.retrieve_top_preferences 方法"""

    @pytest.mark.asyncio
    async def test_returns_top_tables_sorted(self, mem_store):
        """应返回按 query_count 降序排列的偏好表"""
        await _mem_record_batch(mem_store, "user1", ["table_a", "table_b", "table_c"], "mydb")
        await mem_store.record_query("user1", "table_b", "mydb", 1)
        await mem_store.record_query("user1", "table_b", "mydb", 1)
        await mem_store.record_query("user1", "table_c", "mydb", 1)

        results = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(results) == 3
        assert results[0]["table_name"] == "table_b"
        assert results[1]["table_name"] == "table_c"
        assert results[2]["table_name"] == "table_a"

    @pytest.mark.asyncio
    async def test_new_user_returns_empty(self, mem_store):
        """新用户应返回空列表"""
        results = await mem_store.retrieve_top_preferences("new_user")
        assert results == []
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_limit_respected(self, mem_store):
        """limit 参数应生效"""
        for i in range(10):
            await mem_store.record_query("user1", f"table_{i}", "mydb", 1)
        results = await mem_store.retrieve_top_preferences("user1", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_default_limit_is_five(self, mem_store):
        """默认 limit=5"""
        for i in range(10):
            await mem_store.record_query("user1", f"table_{i}", "mydb", 1)
        results = await mem_store.retrieve_top_preferences("user1")
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_returns_all_when_fewer_than_limit(self, mem_store):
        """记录数少于 limit 时返回全部"""
        await _mem_record_batch(mem_store, "user1", ["table_a", "table_b"], "mydb")
        results = await mem_store.retrieve_top_preferences("user1", limit=10)
        assert len(results) == 2


class TestInMemoryLifecycle:
    """测试 InMemoryPreferenceStore 生命周期"""

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self, mem_store):
        """initialize 后 store 应可正常使用"""
        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("user1")
        assert len(prefs) == 1

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, mem_store):
        """重复 initialize 不应报错"""
        await mem_store.initialize()
        await mem_store.record_query("user1", "orders", "mydb", 1)
        prefs = await mem_store.retrieve_top_preferences("user1")
        assert len(prefs) == 1

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        """close 是无操作，不应报错"""
        s = InMemoryPreferenceStore()
        await s.initialize()
        await s.close()
        # 不应抛出异常

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """重复 close 不应报错"""
        s = InMemoryPreferenceStore()
        await s.initialize()
        await s.close()
        await s.close()


class TestInMemoryProtocolCompliance:
    """测试 InMemoryPreferenceStore 是否符合 PreferenceBackend Protocol"""

    def test_isinstance_check(self):
        """InMemoryPreferenceStore 应通过 PreferenceBackend 的 isinstance 检查"""
        from app.memory.preferences import PreferenceBackend
        store = InMemoryPreferenceStore()
        assert isinstance(store, PreferenceBackend)
