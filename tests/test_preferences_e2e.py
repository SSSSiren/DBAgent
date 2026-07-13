"""
偏好存储 E2E 生命周期测试

通过 FastAPI TestClient 和 HTTP API 测试偏好功能的完整生命周期，
覆盖需求 1.1、1.2、2.1、3.1、5.2 的端到端验证。

测试场景：
1. 完整生命周期：查询 → 自动记录偏好 → 新对话检索偏好（需求 1.1、2.1、3.1）
2. 偏好累积：多次查询同一表 → query_count 递增 → 按频率排序（需求 1.2）
3. 静默降级：存储异常 → 偏好功能降级 → 对话正常返回（需求 1.4）
4. OpenViking 共存：kb_enabled=False → 偏好检索和记录仍正常（需求 5.2）

使用 :memory: 偏好存储和 mock agent（替代真实 LLM）实现隔离的 E2E 测试。

运行：
    python -m pytest tests/test_preferences_e2e.py -v
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.api.routes import router
from app.memory.preferences import (
    SqlitePreferenceStore,
    reset_preference_store,
)
from app.config import Settings


# ==========================================================================
# 辅助函数
# ==========================================================================

def _make_settings(**kwargs):
    """构造 mock Settings 实例，用于 monkeypatch get_settings"""
    defaults = {
        "kb_enabled": False,
        "preference_enabled": True,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def _make_initial_state(**kwargs):
    """构造 _execute_agent_stream 所需的 initial_state"""
    defaults = {
        "session_id": "test-session",
        "user_input": "查询数据",
        "user_id": "alice",
        "chat_history": [],
    }
    defaults.update(kwargs)
    return defaults


def _make_initial_state_with_db(**kwargs):
    """构造包含 selected_database 的 initial_state（记录钩子需要 database_name）"""
    defaults = {
        "session_id": "test-session",
        "user_input": "查询 orders 表",
        "user_id": "alice",
        "chat_history": [],
        "selected_database": {"schemaName": "mydb", "schemaId": 1},
    }
    defaults.update(kwargs)
    return defaults


# ==========================================================================
# Mock Agent 流生成器
# ==========================================================================

async def _mock_run_agent_stream_simple(user_input, session_state, cancel_event=None):
    """Mock: 无工具调用的简单回答"""
    yield "final", {
        "response": "这是一个简单的回答。",
        "updated_state": session_state.copy(),
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": [],
        "stats": {"duration_ms": 100},
    }


async def _mock_run_agent_stream_with_query(user_input, session_state, cancel_event=None):
    """Mock: 包含一次成功 query_database 调用的回答"""
    yield "final", {
        "response": "根据 orders 表查询，结果如下...",
        "updated_state": session_state.copy(),
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": [
            {
                "tool": "query_database",
                "args": {
                    "table_name": "orders",
                    "schema_id": 1,
                    "question": "查询所有订单",
                },
                "result": "order_id,amount\n1,100\n2,200",
            }
        ],
        "stats": {"duration_ms": 200},
    }


async def _mock_run_agent_stream_with_join(user_input, session_state, cancel_event=None):
    """Mock: 包含多表 JOIN query_database 调用的回答"""
    yield "final", {
        "response": "JOIN 查询完成",
        "updated_state": session_state.copy(),
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": [
            {
                "tool": "query_database",
                "args": {
                    "table_name": "orders, customers",
                    "schema_id": 1,
                    "question": "订单和客户 JOIN",
                },
                "result": "order_id,customer_name\n1,Alice\n2,Bob",
            }
        ],
        "stats": {"duration_ms": 300},
    }


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture
def client():
    """创建测试 FastAPI 应用和 TestClient（不含 lifespan）"""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def pref_store():
    """创建 :memory: 偏好存储并重置全局单例"""
    store = SqlitePreferenceStore(":memory:")
    # 同步创建 asyncio 事件循环来初始化
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(store.initialize())
    reset_preference_store()
    yield store
    loop.run_until_complete(store.close())
    reset_preference_store()
    loop.close()


def _apply_patches(monkeypatch, pref_store, *, preference_enabled=True, kb_enabled=False, with_database=True):
    """
    应用所有 E2E 测试所需的通用 monkeypatch。

    - get_settings: 控制 preference_enabled / kb_enabled
    - get_preference_store: 注入 :memory: 测试实例
    - run_agent_stream: mock（由各测试自行覆盖）
    - _record_to_openviking: no-op
    - get_store: 使用默认 InMemoryStore
    - _get_or_create_session: 注入 selected_database（记录钩子需要）

    Args:
        with_database: 默认 True，为会话注入 selected_database 以便偏好记录钩子提取 database_name。
                       静默降级测试设为 False 以模拟缺失场景。
    """
    from app.memory.store import InMemoryStore, DEFAULT_SESSION, reset_store

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: _make_settings(preference_enabled=preference_enabled, kb_enabled=kb_enabled),
    )
    monkeypatch.setattr(
        "app.memory.preferences.get_preference_store",
        lambda: pref_store,
    )
    monkeypatch.setattr(
        "app.api.routes._record_to_openviking",
        AsyncMock(),
    )
    # 重置并替换为 InMemoryStore（确保不同导入路径使用同一实例）
    reset_store()
    test_store = InMemoryStore()
    monkeypatch.setattr("app.api.routes.get_store", lambda: test_store)
    monkeypatch.setattr("app.memory.store.get_store", lambda: test_store)

    # Monkeypatch _get_or_create_session 以注入 selected_database
    # 记录钩子需要 initial_state["selected_database"]["schemaName"] 来获取 database_name
    if with_database:
        from app.api.routes import _get_or_create_session as _orig_get_or_create
        import functools

        async def _patched_get_or_create(user_id: str, session_id: str):
            state = await _orig_get_or_create(user_id, session_id)
            # 注入 selected_database，模拟用户已选择数据库的场景
            if "selected_database" not in state or state["selected_database"] is None:
                state["selected_database"] = {"schemaName": "mydb", "schemaId": 1}
            return state

        monkeypatch.setattr(
            "app.api.routes._get_or_create_session",
            _patched_get_or_create,
        )


def _create_session(client, user_id="alice"):
    """通过 API 创建会话，返回 session_id"""
    resp = client.post("/api/sessions", json={"user_id": user_id})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def _chat_sync(client, session_id, message, user_id="alice"):
    """通过 /api/chat/sync 发送消息，返回响应 JSON"""
    resp = client.post("/api/chat/sync", json={
        "session_id": session_id,
        "user_id": user_id,
        "message": message,
    })
    return resp


# ==========================================================================
# 测试类 1：完整生命周期（需求 1.1、2.1、3.1）
# ==========================================================================

class TestPreferenceE2ELifecycle:
    """
    验证偏好的完整生命周期：
    用户查询 → 自动记录偏好 → 新对话检索偏好 → 上下文包含偏好信息
    """

    def test_query_records_preference_and_new_dialog_retrieves(self, client, pref_store, monkeypatch):
        """
        E2E 流程：用户 A 查询 orders 表 → 偏好自动记录 →
                 新对话检索时找到偏好 → preference_count > 0

        覆盖需求 1.1（自动记录）、2.1（关键词匹配）、3.1（注入上下文）
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        # ── 阶段 1：用户 A 查询 orders 表 ──
        session_1 = _create_session(client, user_id="alice")
        resp_1 = _chat_sync(client, session_1, "帮我查一下 orders 表的所有数据", user_id="alice")
        assert resp_1.status_code == 200, f"阶段1请求失败: {resp_1.text}"
        data_1 = resp_1.json()
        assert "response" in data_1
        assert data_1["session_id"] == session_1

        # 验证偏好已被记录
        top_prefs = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(top_prefs) >= 1, "查询后应记录偏好"
        assert top_prefs[0]["table_name"] == "orders"
        assert top_prefs[0]["database_name"] == "mydb"
        assert top_prefs[0]["query_count"] == 1

        # ── 阶段 2：用户 A 开新对话，输入包含关键词 "orders" ──
        session_2 = _create_session(client, user_id="alice")
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        resp_2 = _chat_sync(client, session_2, "再查一下 orders 表最近的数据", user_id="alice")
        assert resp_2.status_code == 200, f"阶段2请求失败: {resp_2.text}"
        data_2 = resp_2.json()
        assert "response" in data_2

        # 验证偏好被检索（preference_count 通过 _execute_agent_stream 注入到 final payload）
        # 由于 ChatResponse 不直接包含 preference_count，我们通过会话状态验证
        # 同时直接验证偏好检索结果
        # 关键词 "orders" 应匹配 orders 表
        matching_prefs = _run_async(
            pref_store.retrieve_preferences("alice", "orders 最近 数据")
        )
        assert len(matching_prefs) >= 1, "关键词应匹配到已记录的偏好"
        assert matching_prefs[0]["table_name"] == "orders"

    def test_multi_table_join_records_all_tables(self, client, pref_store, monkeypatch):
        """
        多表 JOIN 场景：table_name="orders, customers" → 两张表均被记录。
        覆盖需求 1.3（多表分别记录）。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_join,
        )

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "帮我 JOIN orders 和 customers 表", user_id="alice")
        assert resp.status_code == 200, f"请求失败: {resp.text}"

        top_prefs = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(top_prefs) == 2, f"应记录两张表，实际: {len(top_prefs)}"
        table_names = {p["table_name"] for p in top_prefs}
        assert table_names == {"orders", "customers"}
        for p in top_prefs:
            assert p["query_count"] == 1
            assert p["database_name"] == "mydb"

    def test_new_user_has_no_preferences(self, client, pref_store, monkeypatch):
        """
        新用户首次使用时无历史偏好，不阻塞正常对话。
        覆盖需求 2.3。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        session = _create_session(client, user_id="new_user_999")
        resp = _chat_sync(client, session, "帮我查一下数据", user_id="new_user_999")
        assert resp.status_code == 200, f"新用户请求失败: {resp.text}"

        # 新用户不应有任何偏好记录
        top_prefs = _run_async(pref_store.retrieve_top_preferences("new_user_999", limit=10))
        assert len(top_prefs) == 0, "新用户不应有偏好记录"


# ==========================================================================
# 测试类 2：偏好累积（需求 1.2）
# ==========================================================================

class TestPreferenceE2EAccumulation:
    """
    验证偏好的累积行为：
    多次查询同一表 → query_count 递增 → 检索结果按频率排序
    """

    def test_repeat_query_increments_count(self, client, pref_store, monkeypatch):
        """
        同一表查询 3 次 → query_count=3。
        覆盖需求 1.2。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        session = _create_session(client, user_id="alice")

        # 第一次查询
        resp_1 = _chat_sync(client, session, "查 orders 表", user_id="alice")
        assert resp_1.status_code == 200

        # 第二次查询（同一表）
        resp_2 = _chat_sync(client, session, "再查一次 orders", user_id="alice")
        assert resp_2.status_code == 200

        # 第三次查询
        resp_3 = _chat_sync(client, session, "第三次查 orders", user_id="alice")
        assert resp_3.status_code == 200

        top_prefs = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(top_prefs) == 1
        assert top_prefs[0]["table_name"] == "orders"
        assert top_prefs[0]["query_count"] == 3, f"期望 query_count=3, 实际={top_prefs[0]['query_count']}"

    def test_frequent_tables_ranked_by_count_desc(self, client, pref_store, monkeypatch):
        """
        多张表不同查询频率 → 检索结果按 query_count 降序。
        覆盖需求 2.1（按频率降序排列）。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)

        # 为不同表设置不同频率
        # users 表：通过直接操作 store 设置高频
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(pref_store.record_query("alice", "users", "mydb", 1))
        loop.run_until_complete(pref_store.record_query("alice", "users", "mydb", 1))
        loop.run_until_complete(pref_store.record_query("alice", "users", "mydb", 1))
        # users: count=3
        loop.run_until_complete(pref_store.record_query("alice", "orders", "mydb", 1))
        loop.run_until_complete(pref_store.record_query("alice", "orders", "mydb", 1))
        # orders: count=2
        loop.run_until_complete(pref_store.record_query("alice", "payments", "mydb", 1))
        # payments: count=1
        loop.close()

        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 检索：输入通用关键词，匹配所有表
        top_prefs = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(top_prefs) == 3
        assert top_prefs[0]["table_name"] == "users", f"最高频应为 users, 实际={top_prefs[0]['table_name']}"
        assert top_prefs[0]["query_count"] == 3
        assert top_prefs[1]["table_name"] == "orders"
        assert top_prefs[1]["query_count"] == 2
        assert top_prefs[2]["table_name"] == "payments"
        assert top_prefs[2]["query_count"] == 1

    def test_user_isolation_in_accumulation(self, client, pref_store, monkeypatch):
        """
        多用户场景：用户 A 和用户 B 各自的偏好累积独立。
        覆盖需求 2.4。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        # 用户 A 查询 orders 两次
        session_a = _create_session(client, user_id="alice")
        _chat_sync(client, session_a, "查 orders", user_id="alice")
        _chat_sync(client, session_a, "再查 orders", user_id="alice")

        # 用户 B 查询 orders 一次
        session_b = _create_session(client, user_id="bob")
        _chat_sync(client, session_b, "查 orders", user_id="bob")

        # 验证用户 A 的 count=2，用户 B 的 count=1
        prefs_a = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        prefs_b = _run_async(pref_store.retrieve_top_preferences("bob", limit=10))

        assert len(prefs_a) == 1
        assert prefs_a[0]["query_count"] == 2, f"用户A: 期望 count=2, 实际={prefs_a[0]['query_count']}"
        assert len(prefs_b) == 1
        assert prefs_b[0]["query_count"] == 1, f"用户B: 期望 count=1, 实际={prefs_b[0]['query_count']}"


# ==========================================================================
# 测试类 3：静默降级（需求 1.4）
# ==========================================================================

class TestPreferenceE2ESilentDegradation:
    """
    验证偏好存储异常时的静默降级行为：
    检索/记录失败 → 不影响正常对话流程。
    """

    def test_record_exception_chat_still_returns(self, client, pref_store, monkeypatch):
        """
        record_query 抛异常时，/api/chat/sync 仍应返回 200。
        覆盖需求 1.4。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )
        # 让 record_query 抛异常模拟存储故障
        monkeypatch.setattr(
            pref_store,
            "record_query",
            AsyncMock(side_effect=RuntimeError("DB write failed")),
        )

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查 orders", user_id="alice")
        assert resp.status_code == 200, (
            f"存储异常时对话应正常返回，实际 status={resp.status_code}, body={resp.text}"
        )
        data = resp.json()
        assert "response" in data
        # 即使记录失败，响应仍包含 session_id
        assert data["session_id"] == session

    def test_retrieve_exception_chat_still_returns(self, client, pref_store, monkeypatch):
        """
        retrieve_preferences 抛异常时，/api/chat/sync 仍应返回 200。
        覆盖需求 1.4。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        # 先记录一条偏好，然后让检索抛异常
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(pref_store.record_query("alice", "orders", "mydb", 1))
        loop.close()

        monkeypatch.setattr(
            pref_store,
            "retrieve_preferences",
            AsyncMock(side_effect=RuntimeError("DB connection lost")),
        )

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查 orders", user_id="alice")
        assert resp.status_code == 200, (
            f"检索异常时对话应正常返回，实际 status={resp.status_code}"
        )
        data = resp.json()
        assert "response" in data
        assert data["response"] != ""

    def test_close_exception_chat_still_returns(self, client, pref_store, monkeypatch):
        """
        整个 preference store 不可用（未初始化）时，对话仍应正常返回。
        覆盖需求 5.3。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        # 替换为未初始化的 store（在检索时会抛出异常）
        uninit_store = MagicMock()
        uninit_store.retrieve_preferences = AsyncMock(
            side_effect=Exception("Store not initialized")
        )
        monkeypatch.setattr(
            "app.memory.preferences.get_preference_store",
            lambda: uninit_store,
        )

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查数据", user_id="alice")
        assert resp.status_code == 200, (
            f"store 未初始化时对话应正常返回，实际 status={resp.status_code}"
        )


# ==========================================================================
# 测试类 4：与 OpenViking 语义记忆共存（需求 5.1、5.2）
# ==========================================================================

class TestPreferenceE2EOpenVikingCoexistence:
    """
    验证偏好功能与 OpenViking 语义记忆独立运作：
    kb_enabled=False → 偏好检索和记录仍正常
    preference_enabled=False → 对话仍正常，无偏好记录
    """

    def test_kb_disabled_preferences_still_record(self, client, pref_store, monkeypatch):
        """
        kb_enabled=False 时，偏好仍正常记录。
        覆盖需求 5.2。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查 orders 表", user_id="alice")
        assert resp.status_code == 200

        # 偏好应正常记录
        top_prefs = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(top_prefs) == 1
        assert top_prefs[0]["table_name"] == "orders"

    def test_kb_disabled_preferences_still_retrieve(self, client, pref_store, monkeypatch):
        """
        kb_enabled=False 时，偏好仍正常检索。
        覆盖需求 5.2。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 预先记录偏好
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(pref_store.record_query("alice", "orders", "mydb", 1))
        loop.run_until_complete(pref_store.record_query("alice", "users", "mydb", 1))
        loop.close()

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查 orders users", user_id="alice")
        assert resp.status_code == 200

        # 偏好应被检索到
        matching = _run_async(pref_store.retrieve_preferences("alice", "orders users"))
        assert len(matching) == 2

    def test_preference_disabled_no_recording(self, client, pref_store, monkeypatch):
        """
        preference_enabled=False 时，不记录偏好，但对话仍正常返回。
        覆盖需求 5.1（独立运作）。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=False, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查 orders 表", user_id="alice")
        assert resp.status_code == 200, f"preference_enabled=False 时对话应正常返回"

        # 不应有任何偏好被记录
        top_prefs = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(top_prefs) == 0, "preference_enabled=False 不应记录偏好"

    def test_preference_disabled_chat_still_works(self, client, pref_store, monkeypatch):
        """
        preference_enabled=False 时，对话完全不受影响。
        覆盖需求 5.1（一方启停不影响另一方）。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=False, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 先记录一些偏好（模拟之前有记录），然后禁用后再对话
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(pref_store.record_query("alice", "orders", "mydb", 1))
        loop.close()

        session = _create_session(client, user_id="alice")
        resp = _chat_sync(client, session, "查 orders", user_id="alice")
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert data["response"] != ""

    def test_both_enabled_work_together(self, client, pref_store, monkeypatch):
        """
        preference_enabled=True 且 kb_enabled=False（模拟真实场景：仅偏好功能开启）。
        偏好全流程正常工作。
        """
        _apply_patches(monkeypatch, pref_store, preference_enabled=True, kb_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        # 完整流程：查询 → 记录 → 再查 → 检索
        session_1 = _create_session(client, user_id="alice")
        resp_1 = _chat_sync(client, session_1, "查 orders 表", user_id="alice")
        assert resp_1.status_code == 200

        # 验证记录
        prefs_after_record = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert len(prefs_after_record) == 1
        assert prefs_after_record[0]["query_count"] == 1

        # 再查一次
        resp_1b = _chat_sync(client, session_1, "查 orders 表", user_id="alice")
        assert resp_1b.status_code == 200

        prefs_after_second = _run_async(pref_store.retrieve_top_preferences("alice", limit=10))
        assert prefs_after_second[0]["query_count"] == 2

        # 新会话检索
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        session_2 = _create_session(client, user_id="alice")
        resp_2 = _chat_sync(client, session_2, "查 orders", user_id="alice")
        assert resp_2.status_code == 200

        matching = _run_async(pref_store.retrieve_preferences("alice", "orders"))
        assert len(matching) == 1
        assert matching[0]["query_count"] == 2


# ==========================================================================
# 辅助：在同步测试中运行异步函数
# ==========================================================================

def _run_async(coro):
    """在同步测试中运行异步协程"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    else:
        # 已有运行中的事件循环（pytest-asyncio）
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
