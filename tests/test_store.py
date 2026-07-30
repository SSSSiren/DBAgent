"""
SqliteStore 单元测试

测试 SqliteStore 的完整 CRUD 行为，使用 :memory: SQLite 数据库。
验证多用户隔离、会话生命周期、JSON 序列化等。
"""

import asyncio

import pytest
import pytest_asyncio

from app.memory.store import SqliteStore, InMemoryStore


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def store():
    """创建 SqliteStore 实例并初始化（使用 :memory: 数据库）"""
    s = SqliteStore(":memory:")
    await s.initialize()
    yield s
    await s.close()


# ── 初始化 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initialize_creates_tables(store):
    """验证 initialize() 创建了 sessions 表和索引"""
    await store.create_session("user1", "session1", {
        "chat_history": [],
        "summary": "",
    })

    state = await store.get_session("user1", "session1")
    assert state is not None
    assert state["session_id"] == "session1"


@pytest.mark.asyncio
async def test_wal_mode_enabled():
    """验证 WAL 模式在文件数据库上启用（:memory: 数据库不支持 WAL）"""
    import tempfile
    import os

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    s = SqliteStore(db_path)
    try:
        await s.initialize()
        cursor = await s._conn.execute("PRAGMA journal_mode;")
        row = await cursor.fetchone()
        assert row[0].upper() == "WAL"
    finally:
        await s.close()
        os.remove(db_path)
        os.rmdir(tmpdir)


# ── create_session ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_basic(store):
    """验证 create_session() 创建新会话并写入初始状态"""
    initial_state = {
        "chat_history": [],
        "summary": "test session",
        "selected_schema_id": 123,
        "selected_database": "test_db",
    }
    await store.create_session("alice", "sess-001", initial_state)

    state = await store.get_session("alice", "sess-001")
    assert state is not None
    assert state["session_id"] == "sess-001"
    assert state["user_id"] == "alice"
    assert state["summary"] == "test session"
    assert state["selected_schema_id"] == 123
    assert state["selected_database"] == "test_db"
    assert "created_at" in state
    assert "last_active_at" in state


@pytest.mark.asyncio
async def test_create_session_idempotent_overwrite(store):
    """验证 create_session() 在会话已存在时覆盖写入（幂等）"""
    await store.create_session("alice", "sess-001", {
        "summary": "first version",
    })

    await store.create_session("alice", "sess-001", {
        "summary": "second version",
    })

    state = await store.get_session("alice", "sess-001")
    assert state["summary"] == "second version"


# ── get_session ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_session_nonexistent(store):
    """验证 get_session() 对不存在的会话返回 None"""
    state = await store.get_session("alice", "nonexistent")
    assert state is None


@pytest.mark.asyncio
async def test_get_session_returns_full_state(store):
    """验证 get_session() 返回完整会话状态（含所有字段）"""
    await store.create_session("alice", "sess-001", {
        "chat_history": [{"role": "user", "content": "hello"}],
        "summary": "greeting session",
    })

    state = await store.get_session("alice", "sess-001")
    assert state is not None
    assert "session_id" in state
    assert "user_id" in state
    assert "created_at" in state
    assert "last_active_at" in state
    assert len(state["chat_history"]) == 1
    assert state["chat_history"][0]["content"] == "hello"


# ── save_session ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_session_updates_existing(store):
    """验证 save_session() 更新已存在会话的状态"""
    await store.create_session("alice", "sess-001", {
        "chat_history": [],
        "summary": "initial",
    })

    await store.save_session("alice", "sess-001", {
        "chat_history": [{"role": "user", "content": "query"}],
        "summary": "updated",
    })

    state = await store.get_session("alice", "sess-001")
    assert state["summary"] == "updated"
    assert len(state["chat_history"]) == 1
    # 创建时间不应改变
    assert state["created_at"] is not None


@pytest.mark.asyncio
async def test_save_session_creates_if_not_exists(store):
    """验证 save_session() 在会话不存在时自动创建"""
    await store.save_session("bob", "new-session", {
        "chat_history": [{"role": "user", "content": "new"}],
        "summary": "auto-created",
    })

    state = await store.get_session("bob", "new-session")
    assert state is not None
    assert state["summary"] == "auto-created"
    assert state["session_id"] == "new-session"
    assert state["user_id"] == "bob"


# ── delete_session ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_existing(store):
    """验证 delete_session() 删除已存在的会话并返回 True"""
    await store.create_session("alice", "sess-001", {"summary": "to delete"})
    result = await store.delete_session("alice", "sess-001")
    assert result is True

    # 验证会话确实已删除
    state = await store.get_session("alice", "sess-001")
    assert state is None


@pytest.mark.asyncio
async def test_delete_session_nonexistent(store):
    """验证 delete_session() 对不存在的会话返回 False"""
    result = await store.delete_session("alice", "nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_delete_session_only_target_session(store):
    """验证 delete_session() 只删除目标会话，不影响同用户的其他会话"""
    await store.create_session("alice", "sess-001", {"summary": "keep"})
    await store.create_session("alice", "sess-002", {"summary": "delete me"})

    await store.delete_session("alice", "sess-002")

    # sess-001 应仍然存在
    state = await store.get_session("alice", "sess-001")
    assert state is not None

    # sess-002 应已被删除
    state = await store.get_session("alice", "sess-002")
    assert state is None


# ── list_sessions ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sessions_returns_all_for_user(store):
    """验证 list_sessions() 返回用户的所有会话"""
    await store.create_session("alice", "sess-001", {"summary": "first"})
    await store.create_session("alice", "sess-002", {"summary": "second"})
    await store.create_session("alice", "sess-003", {"summary": "third"})

    sessions = await store.list_sessions("alice")
    assert len(sessions) == 3
    session_ids = {s["session_id"] for s in sessions}
    assert session_ids == {"sess-001", "sess-002", "sess-003"}


@pytest.mark.asyncio
async def test_list_sessions_empty_for_new_user(store):
    """验证 list_sessions() 对新用户返回空列表"""
    sessions = await store.list_sessions("unknown_user")
    assert sessions == []


@pytest.mark.asyncio
async def test_list_sessions_sorted_by_last_active_desc(store):
    """验证 list_sessions() 按 last_active_at 降序排列"""
    await store.create_session("alice", "sess-001", {"summary": "oldest"})
    # 稍后再创建第二个会话，使其 last_active_at 更晚
    await asyncio.sleep(0.01)
    await store.create_session("alice", "sess-002", {"summary": "newest"})

    sessions = await store.list_sessions("alice")
    assert len(sessions) == 2
    # 最近创建的应排在前面
    assert sessions[0]["session_id"] == "sess-002"
    assert sessions[1]["session_id"] == "sess-001"


@pytest.mark.asyncio
async def test_list_sessions_summary_fields(store):
    """验证 list_sessions() 返回正确的摘要字段"""
    await store.create_session("alice", "sess-001", {
        "chat_history": [{"role": "user"}, {"role": "assistant"}],
        "summary": "my summary",
    })

    sessions = await store.list_sessions("alice")
    assert len(sessions) == 1
    s = sessions[0]
    assert s["session_id"] == "sess-001"
    assert s["user_id"] == "alice"
    assert s["summary"] == "my summary"
    assert "created_at" in s
    assert "last_active_at" in s
    assert s["message_count"] == 2


# ── 多用户隔离 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_isolation_get_session(store):
    """验证用户 A 无法通过 get_session() 访问用户 B 的会话"""
    await store.create_session("alice", "sess-001", {"summary": "alice data"})
    await store.create_session("bob", "sess-001", {"summary": "bob data"})

    # alice 应能访问自己的会话
    alice_state = await store.get_session("alice", "sess-001")
    assert alice_state is not None
    assert alice_state["summary"] == "alice data"

    # bob 应能访问自己的会话
    bob_state = await store.get_session("bob", "sess-001")
    assert bob_state is not None
    assert bob_state["summary"] == "bob data"

    # 不同命名空间隔离验证
    assert alice_state["user_id"] == "alice"
    assert bob_state["user_id"] == "bob"


@pytest.mark.asyncio
async def test_user_isolation_list_sessions(store):
    """验证 list_sessions() 只返回指定用户的会话"""
    await store.create_session("alice", "sess-001", {"summary": "alice"})
    await store.create_session("alice", "sess-002", {"summary": "alice2"})
    await store.create_session("bob", "sess-001", {"summary": "bob"})

    alice_sessions = await store.list_sessions("alice")
    bob_sessions = await store.list_sessions("bob")

    assert len(alice_sessions) == 2
    assert len(bob_sessions) == 1

    # alice 的会话列表不应包含 bob 的会话
    alice_ids = {s["session_id"] for s in alice_sessions}
    assert alice_ids == {"sess-001", "sess-002"}
    assert all(s["user_id"] == "alice" for s in alice_sessions)

    # bob 的会话列表仅包含自己的会话
    assert bob_sessions[0]["session_id"] == "sess-001"
    assert bob_sessions[0]["user_id"] == "bob"


@pytest.mark.asyncio
async def test_user_isolation_delete_session(store):
    """验证 delete_session() 不会跨用户误删"""
    await store.create_session("alice", "sess-001", {"summary": "alice"})
    await store.create_session("bob", "sess-001", {"summary": "bob"})

    # 删除 alice 的会话
    result = await store.delete_session("alice", "sess-001")
    assert result is True

    # alice 的会话应被删除
    assert await store.get_session("alice", "sess-001") is None

    # bob 的会话应不受影响
    bob_state = await store.get_session("bob", "sess-001")
    assert bob_state is not None
    assert bob_state["summary"] == "bob"


# ── 特殊场景 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_state_preserves_complex_data(store):
    """验证会话状态能正确保留复杂数据结构"""
    complex_state = {
        "chat_history": [
            {"role": "user", "content": "find all errors", "metadata": {"priority": "high"}},
            {"role": "assistant", "content": "SELECT * FROM errors;", "sql": True},
        ],
        "summary": "complex data test",
        "selected_schema_id": 42,
        "selected_database": "production_logs",
        "kb_session_id": "kb-uuid-123",
        "kb_turn_count": 5,
    }
    await store.create_session("alice", "complex-sess", complex_state)

    state = await store.get_session("alice", "complex-sess")
    assert state is not None
    assert state["selected_schema_id"] == 42
    assert state["selected_database"] == "production_logs"
    assert state["kb_session_id"] == "kb-uuid-123"
    assert state["kb_turn_count"] == 5
    assert len(state["chat_history"]) == 2
    assert state["chat_history"][0]["metadata"]["priority"] == "high"
    assert state["chat_history"][1]["sql"] is True


@pytest.mark.asyncio
async def test_initialize_is_idempotent(store):
    """验证 initialize() 是幂等的（多次调用不报错）"""
    await store.initialize()  # fixture 已调用一次，再调用应不报错

    # 验证表仍然正常工作
    await store.create_session("alice", "sess-001", {"summary": "after reinit"})
    state = await store.get_session("alice", "sess-001")
    assert state is not None


# ============================================================================
# Parametrized tests: both InMemoryStore and SqliteStore
# ============================================================================

@pytest_asyncio.fixture(params=["InMemoryStore", "SqliteStore"])
async def any_store(request):
    """Fixture that yields both backends for parametrized testing."""
    if request.param == "InMemoryStore":
        s = InMemoryStore()
        await s.initialize()
        yield s
        await s.close()
    else:
        s = SqliteStore(":memory:")
        await s.initialize()
        yield s
        await s.close()


# ── 初始化 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_initialize_idempotent(any_store):
    """验证两种后端的 initialize() 都是幂等的"""
    await any_store.initialize()  # fixture 已调用一次

    await any_store.create_session("alice", "sess-001", {"summary": "after reinit"})
    state = await any_store.get_session("alice", "sess-001")
    assert state is not None
    assert state["summary"] == "after reinit"


# ── create_session ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_create_session_basic(any_store):
    """验证两种后端的 create_session() 行为一致"""
    initial_state = {
        "chat_history": [{"role": "user", "content": "hello"}],
        "summary": "test session",
        "selected_schema_id": 123,
        "selected_database": "test_db",
        "kb_session_id": "kb-001",
        "kb_turn_count": 3,
    }
    await any_store.create_session("alice", "sess-001", initial_state)

    state = await any_store.get_session("alice", "sess-001")
    assert state is not None
    assert state["session_id"] == "sess-001"
    assert state["user_id"] == "alice"
    assert state["summary"] == "test session"
    assert state["selected_schema_id"] == 123
    assert state["selected_database"] == "test_db"
    assert state["kb_session_id"] == "kb-001"
    assert state["kb_turn_count"] == 3
    assert len(state["chat_history"]) == 1
    assert "created_at" in state
    assert "last_active_at" in state


@pytest.mark.asyncio
async def test_any_store_create_session_idempotent_overwrite(any_store):
    """验证两种后端的 create_session() 覆盖写入行为一致"""
    await any_store.create_session("alice", "sess-001", {"summary": "first version"})
    await any_store.create_session("alice", "sess-001", {"summary": "second version"})

    state = await any_store.get_session("alice", "sess-001")
    assert state["summary"] == "second version"


# ── get_session ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_get_session_nonexistent(any_store):
    """验证两种后端的 get_session() 对不存在的会话返回 None"""
    state = await any_store.get_session("alice", "nonexistent")
    assert state is None


# ── save_session ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_save_session_updates_existing(any_store):
    """验证两种后端的 save_session() 更新已存在会话"""
    await any_store.create_session("alice", "sess-001", {
        "chat_history": [],
        "summary": "initial",
    })

    await any_store.save_session("alice", "sess-001", {
        "chat_history": [{"role": "user", "content": "query"}],
        "summary": "updated",
    })

    state = await any_store.get_session("alice", "sess-001")
    assert state["summary"] == "updated"
    assert len(state["chat_history"]) == 1


@pytest.mark.asyncio
async def test_any_store_save_session_preserves_created_at(any_store):
    """验证两种后端的 save_session() 保留原始 created_at"""
    await any_store.create_session("alice", "sess-001", {
        "chat_history": [],
        "summary": "initial",
        "created_at": "2024-01-01T00:00:00",
    })

    await any_store.save_session("alice", "sess-001", {
        "chat_history": [{"role": "user", "content": "q"}],
        "summary": "updated",
    })

    state = await any_store.get_session("alice", "sess-001")
    assert state["created_at"] == "2024-01-01T00:00:00"
    assert state["summary"] == "updated"


@pytest.mark.asyncio
async def test_any_store_save_session_creates_if_not_exists(any_store):
    """验证两种后端的 save_session() 在会话不存在时自动创建"""
    await any_store.save_session("bob", "new-session", {
        "chat_history": [{"role": "user", "content": "new"}],
        "summary": "auto-created",
    })

    state = await any_store.get_session("bob", "new-session")
    assert state is not None
    assert state["summary"] == "auto-created"
    assert state["session_id"] == "new-session"
    assert state["user_id"] == "bob"


# ── delete_session ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_delete_session_existing(any_store):
    """验证两种后端的 delete_session() 删除已存在会话并返回 True"""
    await any_store.create_session("alice", "sess-001", {"summary": "to delete"})
    result = await any_store.delete_session("alice", "sess-001")
    assert result is True

    state = await any_store.get_session("alice", "sess-001")
    assert state is None


@pytest.mark.asyncio
async def test_any_store_delete_session_nonexistent(any_store):
    """验证两种后端的 delete_session() 对不存在的会话返回 False"""
    result = await any_store.delete_session("alice", "nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_any_store_delete_session_only_target(any_store):
    """验证两种后端的 delete_session() 只删除目标会话"""
    await any_store.create_session("alice", "sess-001", {"summary": "keep"})
    await any_store.create_session("alice", "sess-002", {"summary": "delete me"})

    await any_store.delete_session("alice", "sess-002")

    # sess-001 应仍然存在
    state = await any_store.get_session("alice", "sess-001")
    assert state is not None
    assert state["summary"] == "keep"

    # sess-002 应已被删除
    state = await any_store.get_session("alice", "sess-002")
    assert state is None


# ── list_sessions ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_list_sessions_returns_all_for_user(any_store):
    """验证两种后端的 list_sessions() 返回用户的所有会话"""
    await any_store.create_session("alice", "sess-001", {"summary": "first"})
    await any_store.create_session("alice", "sess-002", {"summary": "second"})
    await any_store.create_session("alice", "sess-003", {"summary": "third"})

    sessions = await any_store.list_sessions("alice")
    assert len(sessions) == 3
    session_ids = {s["session_id"] for s in sessions}
    assert session_ids == {"sess-001", "sess-002", "sess-003"}


@pytest.mark.asyncio
async def test_any_store_list_sessions_empty_for_new_user(any_store):
    """验证两种后端的 list_sessions() 对新用户返回空列表"""
    sessions = await any_store.list_sessions("unknown_user")
    assert sessions == []


@pytest.mark.asyncio
async def test_any_store_list_sessions_sorted_desc(any_store):
    """验证两种后端的 list_sessions() 按 last_active_at 降序"""
    await any_store.create_session("alice", "sess-001", {"summary": "oldest"})
    await asyncio.sleep(0.01)
    await any_store.create_session("alice", "sess-002", {"summary": "newest"})

    sessions = await any_store.list_sessions("alice")
    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "sess-002"
    assert sessions[1]["session_id"] == "sess-001"


@pytest.mark.asyncio
async def test_any_store_list_sessions_summary_fields(any_store):
    """验证两种后端的 list_sessions() 返回正确的摘要字段"""
    await any_store.create_session("alice", "sess-001", {
        "chat_history": [{"role": "user"}, {"role": "assistant"}],
        "summary": "my summary",
    })

    sessions = await any_store.list_sessions("alice")
    assert len(sessions) == 1
    s = sessions[0]
    assert s["session_id"] == "sess-001"
    assert s["user_id"] == "alice"
    assert s["summary"] == "my summary"
    assert "created_at" in s
    assert "last_active_at" in s
    assert s["message_count"] == 2


# ── 多用户隔离（parametrized） ────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_user_isolation_get_session(any_store):
    """验证两种后端：用户 A 无法通过 get_session() 访问用户 B 的会话"""
    await any_store.create_session("alice", "sess-001", {"summary": "alice data"})
    await any_store.create_session("bob", "sess-001", {"summary": "bob data"})

    alice_state = await any_store.get_session("alice", "sess-001")
    assert alice_state is not None
    assert alice_state["summary"] == "alice data"
    assert alice_state["user_id"] == "alice"

    bob_state = await any_store.get_session("bob", "sess-001")
    assert bob_state is not None
    assert bob_state["summary"] == "bob data"
    assert bob_state["user_id"] == "bob"


@pytest.mark.asyncio
async def test_any_store_user_isolation_list_sessions(any_store):
    """验证两种后端：list_sessions() 只返回指定用户的会话"""
    await any_store.create_session("alice", "sess-001", {"summary": "alice"})
    await any_store.create_session("alice", "sess-002", {"summary": "alice2"})
    await any_store.create_session("bob", "sess-001", {"summary": "bob"})

    alice_sessions = await any_store.list_sessions("alice")
    bob_sessions = await any_store.list_sessions("bob")

    assert len(alice_sessions) == 2
    assert len(bob_sessions) == 1

    alice_ids = {s["session_id"] for s in alice_sessions}
    assert alice_ids == {"sess-001", "sess-002"}
    assert all(s["user_id"] == "alice" for s in alice_sessions)

    assert bob_sessions[0]["session_id"] == "sess-001"
    assert bob_sessions[0]["user_id"] == "bob"


@pytest.mark.asyncio
async def test_any_store_user_isolation_delete_session(any_store):
    """验证两种后端：delete_session() 不会跨用户误删"""
    await any_store.create_session("alice", "sess-001", {"summary": "alice"})
    await any_store.create_session("bob", "sess-001", {"summary": "bob"})

    result = await any_store.delete_session("alice", "sess-001")
    assert result is True

    assert await any_store.get_session("alice", "sess-001") is None

    bob_state = await any_store.get_session("bob", "sess-001")
    assert bob_state is not None
    assert bob_state["summary"] == "bob"


@pytest.mark.asyncio
async def test_any_store_user_isolation_delete_only_target_user(any_store):
    """验证两种后端：delete_session() 只删除目标用户会话，不同用户同一 session_id 互不影响"""
    await any_store.create_session("alice", "shared-id", {"summary": "alice shared"})
    await any_store.create_session("alice", "alice-only", {"summary": "alice only"})
    await any_store.create_session("bob", "shared-id", {"summary": "bob shared"})

    # 删除 alice 的 shared-id
    result = await any_store.delete_session("alice", "shared-id")
    assert result is True

    # alice 的 shared-id 已删除, alice-only 仍存在
    assert await any_store.get_session("alice", "shared-id") is None
    alice_only = await any_store.get_session("alice", "alice-only")
    assert alice_only is not None
    assert alice_only["summary"] == "alice only"

    # bob 的 shared-id 不受影响
    bob_shared = await any_store.get_session("bob", "shared-id")
    assert bob_shared is not None
    assert bob_shared["summary"] == "bob shared"

    # bob 的列表只有自己的 shared-id
    bob_sessions = await any_store.list_sessions("bob")
    assert len(bob_sessions) == 1
    assert bob_sessions[0]["session_id"] == "shared-id"


# ── 复杂数据保留（parametrized） ──────────────────────────────────────

@pytest.mark.asyncio
async def test_any_store_preserves_complex_data(any_store):
    """验证两种后端能正确保留复杂嵌套数据结构"""
    complex_state = {
        "chat_history": [
            {"role": "user", "content": "find all errors", "metadata": {"priority": "high"}},
            {"role": "assistant", "content": "SELECT * FROM errors;", "sql": True},
        ],
        "summary": "complex data test",
        "selected_schema_id": 42,
        "selected_database": "production_logs",
        "kb_session_id": "kb-uuid-123",
        "kb_turn_count": 5,
    }
    await any_store.create_session("alice", "complex-sess", complex_state)

    state = await any_store.get_session("alice", "complex-sess")
    assert state is not None
    assert state["selected_schema_id"] == 42
    assert state["selected_database"] == "production_logs"
    assert state["kb_session_id"] == "kb-uuid-123"
    assert state["kb_turn_count"] == 5
    assert len(state["chat_history"]) == 2
    assert state["chat_history"][0]["metadata"]["priority"] == "high"
    assert state["chat_history"][1]["sql"] is True


# ============================================================================
# count_sessions 和 count_distinct_users 测试
# ============================================================================

@pytest.mark.asyncio
async def test_count_sessions_empty_store(store):
    """验证空存储中 count_sessions() 返回 0"""
    assert await store.count_sessions() == 0


@pytest.mark.asyncio
async def test_count_distinct_users_empty_store(store):
    """验证空存储中 count_distinct_users() 返回 0"""
    assert await store.count_distinct_users() == 0


@pytest.mark.asyncio
async def test_count_sessions_basic(store):
    """验证 count_sessions() 返回跨所有用户的会话总数"""
    await store.create_session("alice", "sess-001", {"summary": "a1"})
    await store.create_session("alice", "sess-002", {"summary": "a2"})
    await store.create_session("bob", "sess-001", {"summary": "b1"})

    assert await store.count_sessions() == 3


@pytest.mark.asyncio
async def test_count_distinct_users_basic(store):
    """验证 count_distinct_users() 返回至少有一个会话的不重复用户数"""
    await store.create_session("alice", "sess-001", {"summary": "a1"})
    await store.create_session("alice", "sess-002", {"summary": "a2"})
    await store.create_session("bob", "sess-001", {"summary": "b1"})

    assert await store.count_distinct_users() == 2


@pytest.mark.asyncio
async def test_count_sessions_after_delete(store):
    """验证删除会话后 count_sessions() 正确减少"""
    await store.create_session("alice", "sess-001", {"summary": "a1"})
    await store.create_session("alice", "sess-002", {"summary": "a2"})

    assert await store.count_sessions() == 2

    await store.delete_session("alice", "sess-001")

    assert await store.count_sessions() == 1


@pytest.mark.asyncio
async def test_count_distinct_users_after_delete_all(store):
    """验证删除某用户所有会话后 count_distinct_users() 正确减少"""
    await store.create_session("alice", "sess-001", {"summary": "a1"})
    await store.create_session("bob", "sess-001", {"summary": "b1"})

    assert await store.count_distinct_users() == 2

    await store.delete_session("alice", "sess-001")

    assert await store.count_distinct_users() == 1


# ── Parametrized: count_sessions 和 count_distinct_users ──────────────────

@pytest.mark.asyncio
async def test_any_store_count_sessions_empty(any_store):
    """验证两种后端：空存储 count_sessions() 返回 0"""
    assert await any_store.count_sessions() == 0


@pytest.mark.asyncio
async def test_any_store_count_distinct_users_empty(any_store):
    """验证两种后端：空存储 count_distinct_users() 返回 0"""
    assert await any_store.count_distinct_users() == 0


@pytest.mark.asyncio
async def test_any_store_count_sessions_basic(any_store):
    """验证两种后端：count_sessions() 返回跨用户总数"""
    await any_store.create_session("alice", "sess-001", {"summary": "a1"})
    await any_store.create_session("alice", "sess-002", {"summary": "a2"})
    await any_store.create_session("bob", "sess-001", {"summary": "b1"})

    assert await any_store.count_sessions() == 3


@pytest.mark.asyncio
async def test_any_store_count_distinct_users_basic(any_store):
    """验证两种后端：count_distinct_users() 返回不重复用户数"""
    await any_store.create_session("alice", "sess-001", {"summary": "a1"})
    await any_store.create_session("alice", "sess-002", {"summary": "a2"})
    await any_store.create_session("bob", "sess-001", {"summary": "b1"})
    await any_store.create_session("charlie", "sess-001", {"summary": "c1"})

    assert await any_store.count_distinct_users() == 3


@pytest.mark.asyncio
async def test_any_store_count_sessions_after_delete(any_store):
    """验证两种后端：删除后 count_sessions() 正确减少"""
    await any_store.create_session("alice", "sess-001", {"summary": "a1"})
    await any_store.create_session("alice", "sess-002", {"summary": "a2"})

    assert await any_store.count_sessions() == 2
    await any_store.delete_session("alice", "sess-001")
    assert await any_store.count_sessions() == 1


@pytest.mark.asyncio
async def test_any_store_count_distinct_users_after_delete_all(any_store):
    """验证两种后端：删除某用户所有会话后 count_distinct_users() 减少"""
    await any_store.create_session("alice", "sess-001", {"summary": "a1"})
    await any_store.create_session("bob", "sess-001", {"summary": "b1"})

    assert await any_store.count_distinct_users() == 2
    await any_store.delete_session("alice", "sess-001")
    assert await any_store.count_distinct_users() == 1


@pytest.mark.asyncio
async def test_any_store_counts_consistent(any_store):
    """验证两种后端：count_sessions 和 count_distinct_users 的一致性"""
    # 空存储
    assert await any_store.count_sessions() == 0
    assert await any_store.count_distinct_users() == 0

    # 一个用户一个会话
    await any_store.create_session("alice", "sess-001", {"summary": "a1"})
    assert await any_store.count_sessions() == 1
    assert await any_store.count_distinct_users() == 1

    # 同一用户再加一个会话
    await any_store.create_session("alice", "sess-002", {"summary": "a2"})
    assert await any_store.count_sessions() == 2
    assert await any_store.count_distinct_users() == 1

    # 新增用户
    await any_store.create_session("bob", "sess-001", {"summary": "b1"})
    assert await any_store.count_sessions() == 3
    assert await any_store.count_distinct_users() == 2
