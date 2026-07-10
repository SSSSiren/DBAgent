"""
偏好检索和记录钩子集成测试

测试 _execute_agent_stream() 中的偏好检索、偏好记录和用户隔离逻辑。
使用 QueryPreferenceStore(":memory:") 实现测试隔离，
通过 monkeypatch mock run_agent_stream、get_settings、get_store 等依赖。

运行：
    pytest tests/test_preferences_integration.py -v
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from app.memory.preferences import (
    QueryPreferenceStore,
    reset_preference_store,
)
from app.config import Settings


# ========== 辅助函数 =======================================================

def _make_settings(**kwargs):
    """构造 mock Settings，方便测试中切换 preference_enabled 等配置"""
    defaults = {
        "kb_enabled": False,
        "preference_enabled": True,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def _patch_common(monkeypatch, pref_store, *, preference_enabled=True):
    """应用所有测试依赖的通用 patch"""
    # Patch get_settings — 控制 preference_enabled 和 kb_enabled
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: _make_settings(preference_enabled=preference_enabled),
    )
    # Patch get_preference_store — 返回 :memory: 实例
    monkeypatch.setattr(
        "app.memory.preferences.get_preference_store",
        lambda: pref_store,
    )
    # Patch get_store — save_session 是 no-op
    mock_store = MagicMock()
    mock_store.save_session = AsyncMock()
    monkeypatch.setattr("app.api.routes.get_store", lambda: mock_store)
    # Patch _record_to_openviking — no-op（避免真实的 OpenViking 调用）
    monkeypatch.setattr("app.api.routes._record_to_openviking", AsyncMock())


async def _mock_run_agent_stream_simple(user_input, session_state):
    """简单的 mock：仅 yield 一个 final 事件，无工具调用"""
    yield "final", {
        "response": "这是一个简单的回答。",
        "updated_state": session_state.copy(),
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": [],
        "stats": {"duration_ms": 100},
    }


async def _mock_run_agent_stream_with_query(user_input, session_state):
    """包含 query_database 成功调用的 mock"""
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


async def _mock_run_agent_stream_with_join(user_input, session_state):
    """包含多表 JOIN 查询的 mock（table_name 用逗号分隔）"""
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


async def _mock_run_agent_stream_with_describe_table(user_input, session_state):
    """包含 describe_table 成功调用的 mock（Agent 常用此工具查表结构）"""
    yield "final", {
        "response": "表结构如下...",
        "updated_state": session_state.copy(),
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": [
            {
                "tool": "describe_table",
                "args": {
                    "table_name": "users",
                    "schema_id": 2,
                },
                "result": "CREATE TABLE users (id INT, name VARCHAR)",
            }
        ],
        "stats": {"duration_ms": 150},
    }


async def _consume_stream(generator):
    """消费整个异步生成器，返回所有产出的 (event_type, data) 元组列表"""
    events = []
    async for event_type, data in generator:
        events.append((event_type, data))
    return events


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


# ========== Fixtures ========================================================

@pytest_asyncio.fixture
async def pref_store():
    """创建独立的 :memory: 偏好存储实例"""
    store = QueryPreferenceStore(":memory:")
    await store.initialize()
    yield store
    await store.close()
    reset_preference_store()


# ========== 检索钩子测试 ====================================================

class TestRetrievalHook:
    """测试 _execute_agent_stream 中的偏好检索钩子"""

    @pytest.mark.asyncio
    async def test_keyword_match_injects_preferences(self, pref_store, monkeypatch):
        """用户输入匹配已记录的表名关键词时，_preferences 应被注入 initial_state"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 预先记录偏好：orders 表
        await pref_store.record_query("alice", "orders", "mydb", 1)
        await pref_store.record_query("alice", "users", "mydb", 1)

        initial_state = _make_initial_state(user_input="帮我查一下 orders 表的数据")
        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        # 验证 final 事件包含 preference_count > 0
        final_event = events[-1]
        assert final_event[0] == "final"
        assert final_event[1]["preference_count"] > 0

        # 验证 _preferences 被注入 initial_state
        assert "_preferences" in initial_state
        prefs = initial_state["_preferences"]
        # 应至少匹配到 "orders"（关键词 "orders" LIKE 匹配 table_name="orders"）
        table_names = {p["table_name"] for p in prefs}
        assert "orders" in table_names

        # 验证 _preference_count 在 final payload 中
        assert initial_state.get("_preference_count", 0) > 0

    @pytest.mark.asyncio
    async def test_no_keyword_match_falls_back_to_top(self, pref_store, monkeypatch):
        """用户输入无匹配关键词时，应回退到返回最常用的偏好表"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 预先记录偏好
        await pref_store.record_query("alice", "orders", "mydb", 1)
        await pref_store.record_query("alice", "users", "mydb", 1)
        # orders 再查 2 次 → query_count=3（最常用）
        await pref_store.record_query("alice", "orders", "mydb", 1)
        await pref_store.record_query("alice", "orders", "mydb", 1)

        initial_state = _make_initial_state(
            user_input="今天天气怎么样"  # 无任何表名关键词
        )
        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        # 应回退到 top preferences
        assert final_event[1]["preference_count"] == 2

        assert "_preferences" in initial_state
        prefs = initial_state["_preferences"]
        # 按 query_count 降序排列
        assert prefs[0]["table_name"] == "orders"
        assert prefs[1]["table_name"] == "users"

    @pytest.mark.asyncio
    async def test_new_user_returns_empty_preferences(self, pref_store, monkeypatch):
        """新用户（无任何历史偏好）应返回空偏好列表"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        initial_state = _make_initial_state(
            user_input="查询订单", user_id="new_user"
        )
        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="new_user")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        assert final_event[1]["preference_count"] == 0
        # 空偏好不注入 _preferences
        assert "_preferences" not in initial_state

    @pytest.mark.asyncio
    async def test_preference_disabled_skips_retrieval(self, pref_store, monkeypatch):
        """preference_enabled=False 时跳过偏好检索，不注入 _preferences"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 即使有偏好记录
        await pref_store.record_query("alice", "orders", "mydb", 1)

        initial_state = _make_initial_state(user_input="查询 orders 表")
        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        # 偏好功能关闭，不应注入
        assert final_event[1]["preference_count"] == 0
        assert "_preferences" not in initial_state

    @pytest.mark.asyncio
    async def test_retrieval_exception_graceful_degradation(self, pref_store, monkeypatch):
        """偏好检索异常时静默降级，不阻塞对话，preference_count=0"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        # 让 retrieve_preferences 抛异常
        monkeypatch.setattr(
            pref_store,
            "retrieve_preferences",
            AsyncMock(side_effect=RuntimeError("DB connection lost")),
        )

        initial_state = _make_initial_state(user_input="查询 orders")
        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        # 异常时应返回正常的对话响应
        assert final_event[1]["reply"] != ""
        assert final_event[1]["preference_count"] == 0
        assert "_preferences" not in initial_state


# ========== 记录钩子测试 ====================================================

class TestRecordHook:
    """测试 _execute_agent_stream 中的偏好记录钩子"""

    @pytest.mark.asyncio
    async def test_query_database_success_records_preference(self, pref_store, monkeypatch):
        """query_database 成功执行后，偏好应被自动记录到存储中"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        # 验证对话响应正常返回
        final_event = events[-1]
        assert final_event[0] == "final"
        assert final_event[1]["reply"] != ""

        # 验证偏好已被记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["table_name"] == "orders"
        assert prefs[0]["database_name"] == "mydb"
        assert prefs[0]["schema_id"] == 1
        assert prefs[0]["query_count"] == 1

    @pytest.mark.asyncio
    async def test_describe_table_success_records_preference(self, pref_store, monkeypatch):
        """describe_table 成功执行后，偏好应被自动记录（Agent 常用此工具）"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_describe_table,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        assert final_event[1]["reply"] != ""

        # 验证偏好已被记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["table_name"] == "users"
        assert prefs[0]["database_name"] == "mydb"
        assert prefs[0]["schema_id"] == 2
        assert prefs[0]["query_count"] == 1

    @pytest.mark.asyncio
    async def test_multi_table_join_records_per_table(self, pref_store, monkeypatch):
        """多表 JOIN 场景（table_name="orders, customers"）应逐表分别记录"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_join,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        assert final_event[1]["reply"] != ""

        # 验证两张表均被记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 2
        table_names = {p["table_name"] for p in prefs}
        assert table_names == {"orders", "customers"}
        # 每张表的 query_count 各为 1
        for p in prefs:
            assert p["query_count"] == 1
            assert p["database_name"] == "mydb"

    @pytest.mark.asyncio
    async def test_repeat_query_increments_count(self, pref_store, monkeypatch):
        """同一用户对同一表多次查询，query_count 应递增"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        initial_state = _make_initial_state_with_db()

        # 第一次查询
        await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )
        # 第二次查询（同一张表）
        await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["query_count"] == 2

    @pytest.mark.asyncio
    async def test_no_query_database_no_record(self, pref_store, monkeypatch):
        """工具调用中不包含 query_database 时，不应记录任何偏好"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,  # tool_calls 为空
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"

        # 应无任何偏好被记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_query_database_null_result_no_record(self, pref_store, monkeypatch):
        """query_database 的 result 为 None 时（执行失败），不应记录偏好"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)

        async def _mock_failed_query(user_input, session_state):
            yield "final", {
                "response": "查询失败",
                "updated_state": session_state.copy(),
                "needs_confirmation": False,
                "pending_action": None,
                "tool_calls": [
                    {
                        "tool": "query_database",
                        "args": {
                            "table_name": "orders",
                            "schema_id": 1,
                            "question": "查询",
                        },
                        "result": None,  # 失败：结果为 None
                    }
                ],
                "stats": {},
            }

        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_failed_query,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"

        # result=None 不满足 tc.get("result") is not None 条件
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_record_exception_returns_normally(self, pref_store, monkeypatch):
        """偏好记录时抛异常，对话响应仍应正常返回（静默降级）"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )
        # 让 record_query 抛异常
        monkeypatch.setattr(
            pref_store,
            "record_query",
            AsyncMock(side_effect=RuntimeError("DB write failed")),
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"
        # 对话响应应正常返回
        assert final_event[1]["reply"] != ""
        # 未受异常影响
        assert "session_id" in final_event[1]

    @pytest.mark.asyncio
    async def test_preference_disabled_skips_record(self, pref_store, monkeypatch):
        """preference_enabled=False 时跳过偏好记录，不写入任何数据"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=False)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"

        # 不应有任何偏好被记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 0


# ========== 用户隔离测试 ====================================================

class TestUserIsolation:
    """测试多用户场景下的偏好检索和记录隔离"""

    @pytest.mark.asyncio
    async def test_user_a_retrieval_excludes_user_b_data(self, pref_store, monkeypatch):
        """用户 A 的偏好检索结果不应包含用户 B 的数据"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 用户 A 的偏好
        await pref_store.record_query("alice", "orders", "mydb", 1)
        await pref_store.record_query("alice", "users", "mydb", 1)
        # 用户 B 的偏好（不同的表）
        await pref_store.record_query("bob", "payments", "mydb", 1)
        await pref_store.record_query("bob", "invoices", "mydb", 1)

        # 用户 A 检索：输入匹配 "orders"
        state_a = _make_initial_state(
            user_input="查询 orders", user_id="alice"
        )
        events_a = await _consume_stream(
            _execute_agent_stream(state_a, user_id="alice")
        )

        final_a = events_a[-1]
        assert final_a[0] == "final"
        assert "_preferences" in state_a
        prefs_a = state_a["_preferences"]
        a_tables = {p["table_name"] for p in prefs_a}
        # 应只包含 alice 的表
        assert "orders" in a_tables or "users" in a_tables
        # 不应包含 bob 的表
        assert "payments" not in a_tables
        assert "invoices" not in a_tables

    @pytest.mark.asyncio
    async def test_user_a_records_dont_affect_user_b_retrieval(self, pref_store, monkeypatch):
        """用户 A 的记录操作不应影响用户 B 的偏好检索"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        # 用户 A 执行查询（记录偏好）
        state_a = _make_initial_state_with_db(
            user_id="alice", user_input="查询 orders"
        )
        await _consume_stream(
            _execute_agent_stream(state_a, user_id="alice")
        )

        # 验证用户 A 的偏好已记录
        prefs_a = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs_a) == 1
        assert prefs_a[0]["table_name"] == "orders"

        # 用户 B 检索（应有空结果）
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        state_b = _make_initial_state(
            user_input="查询 orders", user_id="bob"
        )
        events_b = await _consume_stream(
            _execute_agent_stream(state_b, user_id="bob")
        )

        final_b = events_b[-1]
        assert final_b[0] == "final"
        # 用户 B 的 preference_count 应为 0（无记录）
        assert final_b[1]["preference_count"] == 0
        assert "_preferences" not in state_b

    @pytest.mark.asyncio
    async def test_both_users_have_independent_preferences(self, pref_store, monkeypatch):
        """两个用户各自有偏好记录，检索时各自独立"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        # 为两个用户分别记录偏好
        # NOTE: 由于 _mock_run_agent_stream_with_query 固定返回 orders，
        # 这里直接通过 store 操作来设置两个用户不同的偏好
        await pref_store.record_query("alice", "orders", "mydb", 1)
        await pref_store.record_query("alice", "orders", "mydb", 1)  # count=2
        await pref_store.record_query("alice", "users", "mydb", 1)

        await pref_store.record_query("bob", "payments", "mydb", 1)
        await pref_store.record_query("bob", "invoices", "mydb", 1)

        # 用户 A 检索
        state_a = _make_initial_state(
            user_input="查一下 orders users payments invoices",
            user_id="alice",
        )
        events_a = await _consume_stream(
            _execute_agent_stream(state_a, user_id="alice")
        )
        final_a = events_a[-1]
        assert final_a[1]["preference_count"] > 0
        prefs_a = initial_state_a = state_a.get("_preferences", [])
        a_tables = {p["table_name"] for p in prefs_a}
        # alice 应只能看到自己的表
        assert a_tables <= {"orders", "users"}

        # 用户 B 检索
        state_b = _make_initial_state(
            user_input="查一下 orders users payments invoices",
            user_id="bob",
        )
        events_b = await _consume_stream(
            _execute_agent_stream(state_b, user_id="bob")
        )
        final_b = events_b[-1]
        assert final_b[1]["preference_count"] > 0
        prefs_b = state_b.get("_preferences", [])
        b_tables = {p["table_name"] for p in prefs_b}
        # bob 应只能看到自己的表
        assert b_tables <= {"payments", "invoices"}

        # 两个用户的偏好表集合应不重叠
        assert a_tables.isdisjoint(b_tables)

    @pytest.mark.asyncio
    async def test_user_isolation_with_record_hook(self, pref_store, monkeypatch):
        """完整场景：用户 A 记录偏好后，用户 B 的检索不受影响"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        # 用户 A 执行一次查询（记录 orders 偏好）
        state_a = _make_initial_state_with_db(
            user_id="alice", user_input="查询 orders"
        )
        await _consume_stream(
            _execute_agent_stream(state_a, user_id="alice")
        )

        # 用户 A 的偏好应被记录
        prefs_a = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs_a) == 1
        assert prefs_a[0]["table_name"] == "orders"
        assert prefs_a[0]["query_count"] == 1

        # 用户 B 的偏好应为空
        prefs_b = await pref_store.retrieve_top_preferences("bob", limit=10)
        assert len(prefs_b) == 0

        # 用户 B 执行检索，不应看到用户 A 的数据
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )
        state_b = _make_initial_state(
            user_input="查询 orders", user_id="bob"
        )
        events_b = await _consume_stream(
            _execute_agent_stream(state_b, user_id="bob")
        )
        final_b = events_b[-1]
        assert final_b[1]["preference_count"] == 0
        assert "_preferences" not in state_b


# ========== 边界场景测试 ====================================================

class TestEdgeCases:
    """测试偏好钩子的边界场景"""

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_mixed_results(self, pref_store, monkeypatch):
        """混合工具调用：只有成功的 query_database 被记录"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)

        async def _mock_mixed_tools(user_input, session_state):
            yield "final", {
                "response": "完成",
                "updated_state": session_state.copy(),
                "needs_confirmation": False,
                "pending_action": None,
                "tool_calls": [
                    {
                        "tool": "find_table",
                        "args": {"question": "查找表"},
                        "result": "找到表 orders",
                    },
                    {
                        "tool": "query_database",
                        "args": {
                            "table_name": "orders",
                            "schema_id": 1,
                            "question": "查询",
                        },
                        "result": "order_id\n1\n2",
                    },
                    {
                        "tool": "query_database",
                        "args": {
                            "table_name": "users",
                            "schema_id": 1,
                            "question": "查询",
                        },
                        "result": None,  # 失败
                    },
                ],
                "stats": {},
            }

        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_mixed_tools,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"

        # 只有成功的 query_database（orders）被记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 1
        assert prefs[0]["table_name"] == "orders"
        # users 的 query_database 因 result=None 不应被记录

    @pytest.mark.asyncio
    async def test_empty_table_name_after_split_skipped(self, pref_store, monkeypatch):
        """table_name 拆分后有空字符串应跳过"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)

        async def _mock_trailing_comma(user_input, session_state):
            yield "final", {
                "response": "完成",
                "updated_state": session_state.copy(),
                "needs_confirmation": False,
                "pending_action": None,
                "tool_calls": [
                    {
                        "tool": "query_database",
                        "args": {
                            "table_name": "orders, , customers,",
                            "schema_id": 1,
                            "question": "查询",
                        },
                        "result": "data",
                    }
                ],
                "stats": {},
            }

        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_trailing_comma,
        )

        initial_state = _make_initial_state_with_db()

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"

        # 应记录 orders 和 customers（空字符串被 strip 后跳过）
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 2
        table_names = {p["table_name"] for p in prefs}
        assert table_names == {"orders", "customers"}

    @pytest.mark.asyncio
    async def test_missing_database_name_no_record(self, pref_store, monkeypatch):
        """initial_state 中缺少 selected_database 时不应记录偏好"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_with_query,
        )

        # initial_state 不包含 selected_database
        initial_state = _make_initial_state(user_input="查询 orders")

        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        assert final_event[0] == "final"

        # 无 database_name，不应记录
        prefs = await pref_store.retrieve_top_preferences("alice", limit=10)
        assert len(prefs) == 0

    @pytest.mark.asyncio
    async def test_preference_count_in_final_yield(self, pref_store, monkeypatch):
        """验证 final yield 中始终包含 preference_count 字段"""
        from app.api.routes import _execute_agent_stream

        _patch_common(monkeypatch, pref_store, preference_enabled=True)
        monkeypatch.setattr(
            "app.api.routes.run_agent_stream",
            _mock_run_agent_stream_simple,
        )

        await pref_store.record_query("alice", "orders", "mydb", 1)
        await pref_store.record_query("alice", "users", "mydb", 1)
        await pref_store.record_query("alice", "payments", "mydb", 1)

        initial_state = _make_initial_state(
            user_input="查询 orders users payments",
        )
        events = await _consume_stream(
            _execute_agent_stream(initial_state, user_id="alice")
        )

        final_event = events[-1]
        # preference_count 应在 final yield 中
        assert "preference_count" in final_event[1]
        assert final_event[1]["preference_count"] == 3

        # 同时 updated_state 中也应持久化（通过 final_payload["updated_state"]）
        # 但 mock 中 updated_state 是 session_state.copy()，所以不包含 preference_count
        # 真实的 run_agent_stream 会通过 build_context 处理，此处仅验证 final yield
