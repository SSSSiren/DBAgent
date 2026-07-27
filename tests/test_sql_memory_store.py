"""
SQL 记忆存储单元测试 — 覆盖 InMemorySqlMemoryStore 和 SqliteSqlMemoryStore
"""

import asyncio
import pytest
import pytest_asyncio

from app.memory.sql_memory import (
    InMemorySqlMemoryStore,
    SqliteSqlMemoryStore,
    SqlMemoryBackend,
    _cosine_similarity,
    reset_sql_memory_store,
)


# ============================================================================
# Fixtures
# ============================================================================

def _make_execution_result(row_count=10, columns=None, status="success"):
    return {
        "row_count": row_count,
        "column_names": columns or ["id", "name"],
        "data_preview": [[1, "test"]],
        "execution_status": status,
    }


def _make_embedding(seed=0.5, dim=10):
    return [(seed + i * 0.01) % 1.0 for i in range(dim)]


@pytest_asyncio.fixture
async def mem_store():
    """内存存储实例"""
    store = InMemorySqlMemoryStore(max_per_user=50)
    return store


@pytest_asyncio.fixture
async def sqlite_store():
    """SQLite :memory: 存储实例"""
    store = SqliteSqlMemoryStore(":memory:")
    await store.initialize()
    yield store
    await store.close()


# 参数化：两个实现共享相同的测试
BACKENDS = pytest.mark.parametrize("backend", ["memory", "sqlite"])


async def _get_store(backend_type):
    """Helper: get store instance by type string"""
    if backend_type == "memory":
        return InMemorySqlMemoryStore(max_per_user=50)
    else:
        store = SqliteSqlMemoryStore(":memory:")
        await store.initialize()
        return store


async def _close_store(store, backend_type):
    if backend_type == "sqlite":
        await store.close()


# ============================================================================
# Tests: SqlMemoryBackend Protocol
# ============================================================================


def test_protocol_runtime_checkable():
    """验证 SqlMemoryBackend 支持 isinstance 运行时检查"""
    mem = InMemorySqlMemoryStore()
    assert isinstance(mem, SqlMemoryBackend)


# ============================================================================
# Tests: Cosine Similarity
# ============================================================================


def test_cosine_similarity_identical():
    """相同向量 → 相似度 1.0"""
    v = [0.1, 0.2, 0.3]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    """正交向量 → 相似度 0.0"""
    assert abs(_cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-6


def test_cosine_similarity_empty():
    """空向量 → 0.0"""
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1.0], []) == 0.0


def test_cosine_similarity_mismatched_dim():
    """维度不匹配 → 0.0"""
    assert _cosine_similarity([1.0, 2.0], [1.0]) == 0.0


# ============================================================================
# Tests: Record → Search Roundtrip (both backends)
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_record_and_search_basic(backend):
    """基本写后检索"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record(
            user_id="u1", question="查询已支付订单",
            sql="SELECT COUNT(*) FROM orders WHERE status = 'paid'",
            table_names=["orders"], database_name="db1", schema_id=1,
            execution_result=_make_execution_result(1234, ["COUNT(*)"]),
            embedding=emb,
        )
        results = await store.search_similar(
            user_id="u1", query_embedding=emb, limit=5, scope="user",
        )
        assert len(results) == 1
        assert results[0]["question"] == "查询已支付订单"
        assert results[0]["row_count"] == 1234
        assert results[0]["similarity"] == pytest.approx(1.0)
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_search_similarity_ordering(backend):
    """检索结果按相似度降序"""
    store = await _get_store(backend)
    try:
        emb1 = _make_embedding(0.1)
        emb2 = _make_embedding(0.5)
        emb3 = _make_embedding(0.9)
        await store.record("u1", "q1", "SELECT 1", ["t1"], "db1", 1, _make_execution_result(), emb1)
        await store.record("u1", "q2", "SELECT 2", ["t2"], "db1", 1, _make_execution_result(), emb2)
        await store.record("u1", "q3", "SELECT 3", ["t3"], "db1", 1, _make_execution_result(), emb3)

        # 查询向量接近 emb2
        results = await store.search_similar("u1", emb2, limit=5, scope="user")
        assert len(results) == 3
        assert results[0]["similarity"] >= results[1]["similarity"]
        assert results[0]["similarity"] == pytest.approx(1.0)  # emb2 匹配自己
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_search_empty_store(backend):
    """空存储检索 → 空列表"""
    store = await _get_store(backend)
    try:
        results = await store.search_similar("u1", [0.1, 0.2], limit=5, scope="user")
        assert results == []
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: Scope Isolation
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_user_scope_isolation(backend):
    """Per-user 作用域：用户间隔离"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record("u_a", "q_a", "SELECT 1", ["ta"], "db1", 1, _make_execution_result(), emb)
        await store.record("u_b", "q_b", "SELECT 2", ["tb"], "db1", 1, _make_execution_result(), emb)

        results_a = await store.search_similar("u_a", emb, limit=5, scope="user")
        assert len(results_a) == 1
        assert results_a[0]["question"] == "q_a"
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_database_scope_shared(backend):
    """Per-database 作用域：跨用户可见"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record("u_a", "q_a", "SELECT 1", ["ta"], "shared_db", 1, _make_execution_result(), emb)
        await store.record("u_b", "q_b", "SELECT 2", ["tb"], "shared_db", 1, _make_execution_result(), emb)

        results = await store.search_similar("u_a", emb, limit=5, scope="database", database_name="shared_db")
        assert len(results) == 2  # 两个用户的记录都可见
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_mixed_scope(backend):
    """混合作用域：同数据库 + 同用户"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record("u_a", "q_a1", "SELECT 1", ["ta"], "shared_db", 1, _make_execution_result(), emb)
        await store.record("u_b", "q_b", "SELECT 2", ["tb"], "shared_db", 1, _make_execution_result(), emb)
        await store.record("u_a", "q_a2", "SELECT 3", ["tc"], "other_db", 1, _make_execution_result(), emb)

        results = await store.search_similar("u_a", emb, limit=10, scope="mixed", database_name="shared_db")
        # shared_db 下 u_a + u_b 的记录 + u_a 的 other_db 记录
        assert len(results) == 3
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: Dedup
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_dedup_same_sql_skipped(backend):
    """相同 SQL 重复写入被跳过"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record("u1", "q1", "SELECT COUNT(*) FROM orders", ["orders"], "db1", 1, _make_execution_result(), emb)
        await store.record("u1", "q1", "SELECT COUNT(*) FROM orders", ["orders"], "db1", 1, _make_execution_result(), emb)

        records = await store.list_by_user("u1", limit=50)
        assert len(records) == 1
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: TTL Cleanup
# ============================================================================


@pytest.mark.asyncio
async def test_delete_expired_sqlite():
    """TTL 过期清理（SQLite）"""
    import datetime
    store = SqliteSqlMemoryStore(":memory:")
    await store.initialize()
    try:
        emb = _make_embedding(0.1)
        await store.record("u1", "q1", "SELECT 1", ["t1"], "db1", 1, _make_execution_result(), emb)

        # 手动将 created_at 改为 100 天前
        old_date = (datetime.datetime.now() - datetime.timedelta(days=100)).isoformat()
        await store._conn.execute(
            "UPDATE sql_memories SET created_at = ? WHERE user_id = ?;",
            (old_date, "u1"),
        )
        await store._conn.commit()

        deleted = await store.delete_expired(90)
        assert deleted == 1
        records = await store.list_by_user("u1")
        assert len(records) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_delete_expired_memory():
    """TTL 过期清理（内存）"""
    store = InMemorySqlMemoryStore()
    emb = _make_embedding(0.1)
    await store.record("u1", "q1", "SELECT 1", ["t1"], "db1", 1, _make_execution_result(), emb)
    # 内存实现使用 record 时的时间戳，delete_expired(0) 应该删除所有
    deleted = await store.delete_expired(0)
    assert deleted == 1


# ============================================================================
# Tests: list_by_user
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_list_by_user_empty(backend):
    """不存在的用户 → 空列表"""
    store = await _get_store(backend)
    try:
        records = await store.list_by_user("nonexistent")
        assert records == []
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_list_by_user_pagination(backend):
    """分页限制"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        for i in range(10):
            await store.record("u1", f"q{i}", f"SELECT {i}", ["t1"], "db1", 1, _make_execution_result(), emb)
        records = await store.list_by_user("u1", limit=5)
        assert len(records) == 5
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: Execution Status
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_record_execution_status_error(backend):
    """记录 SQL 执行失败状态"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record(
            "u1", "q_err", "SELECT * FROM nonexistent",
            ["nonexistent"], "db1", 1,
            _make_execution_result(0, [], "error"),
            emb,
        )
        records = await store.list_by_user("u1")
        assert len(records) == 1
        # execution_status 应该在结果的顶层（来自 record 内部）
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_record_execution_status_empty(backend):
    """记录空结果状态"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record(
            "u1", "q_empty", "SELECT * FROM orders WHERE 1=0",
            ["orders"], "db1", 1,
            _make_execution_result(0, ["id"], "empty"),
            emb,
        )
        records = await store.list_by_user("u1")
        assert len(records) == 1
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: Null Embedding Records (excluded from search)
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_null_embedding_excluded_from_search(backend):
    """无 embedding 的记录不参与检索"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record("u1", "q1", "SELECT 1", ["t1"], "db1", 1, _make_execution_result(), emb)
        await store.record("u1", "q2", "SELECT 2", ["t2"], "db1", 1, _make_execution_result(), embedding=None)

        results = await store.search_similar("u1", emb, limit=5, scope="user")
        assert len(results) == 1  # 只返回有 embedding 的记录
        assert results[0]["question"] == "q1"
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: Pattern Mining
# ============================================================================


@pytest.mark.asyncio
@BACKENDS
async def test_mine_patterns_insufficient_records(backend):
    """记录不足 → 返回提示"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        await store.record("u1", "q1", "SELECT 1", ["t1"], "db1", 1, _make_execution_result(), emb)

        result = await store.mine_patterns("db1", min_records=20)
        assert result["total_records"] == 1
        assert "记录不足" in result.get("message", "")
    finally:
        await _close_store(store, backend)


@pytest.mark.asyncio
@BACKENDS
async def test_mine_patterns_sufficient_records(backend):
    """记录充足 → 返回模式"""
    store = await _get_store(backend)
    try:
        emb = _make_embedding(0.1)
        tables = ["order_record", "account", "order_record", "account", "order_record"]
        for i in range(25):
            t = tables[i % len(tables)]
            sql = f"SELECT * FROM {t} WHERE status = 'active' AND id > {i*10}"
            if i % 5 == 0:
                sql = f"SELECT * FROM {t} LEFT JOIN account ON {t}.user_id = account.id WHERE {t}.status = 'active' AND {t}.id > {i*10}"
            await store.record("u1", f"q{i}", sql, [t], "db1", 1, _make_execution_result(), emb)

        result = await store.mine_patterns("db1", min_records=20)
        assert result["total_records"] == 25
        assert len(result["top_tables"]) > 0
        assert len(result["top_condition_patterns"]) > 0
        assert len(result["common_joins"]) > 0
    finally:
        await _close_store(store, backend)


# ============================================================================
# Tests: Factory and Module-Level Singleton
# ============================================================================


def test_reset_sql_memory_store():
    """重置工厂单例"""
    from app.memory.sql_memory import get_sql_memory_store, reset_sql_memory_store
    reset_sql_memory_store()
    store1 = get_sql_memory_store()
    store2 = get_sql_memory_store()
    assert store1 is store2  # 单例
    reset_sql_memory_store()
    store3 = get_sql_memory_store()
    assert store1 is not store3  # 重置后新实例
    reset_sql_memory_store()
