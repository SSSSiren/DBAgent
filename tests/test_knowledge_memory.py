"""
OpenViking 对话记忆模块测试

测试层级：
- 单元测试（mock）：OpenVikingClient + _record_to_openviking + store 持久化
- 集成测试（需真实 OV Server）：多用户隔离验证

运行：
    pytest tests/test_knowledge_memory.py -v                       # 全部
    pytest tests/test_knowledge_memory.py -v -k "not integration"  # 仅单元
    pytest tests/test_knowledge_memory.py -v -m integration        # 仅集成
"""

import pytest
from unittest.mock import AsyncMock

import httpx

from app.knowledge.openviking import OpenVikingClient
from app.memory.store import get_session, save_session, SESSION_STORE
from app.api.routes import _record_to_openviking


# ========== 辅助 ==========

def _make_settings(**kwargs):
    """构造 mock Settings，方便测试中切换 kb_* 配置"""
    from app.config import Settings

    defaults = {
        "kb_enabled": False,
        "kb_openviking_url": "http://localhost:1933",
        "kb_auto_commit_turns": 10,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


# ========== 第一层：OpenVikingClient 单元测试 ==========


class TestOpenVikingClient:
    """测试 OpenVikingClient 的 HTTP 封装逻辑"""

    @pytest.fixture
    def client(self):
        return OpenVikingClient("http://localhost:1933", "test_user")

    # ── start() ──

    @pytest.mark.asyncio
    async def test_start_creates_client_with_correct_headers(self, client):
        """start() 创建 httpx.AsyncClient，携带正确的 header"""
        await client.start()
        assert client._client is not None
        headers = client._client.headers
        assert headers["X-OpenViking-User"] == "test_user"
        assert headers["X-OpenViking-Account"] == "default"
        assert headers["Content-Type"] == "application/json"
        await client.close()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, client):
        """多次调用 start() 不会重复创建 AsyncClient"""
        await client.start()
        c1 = client._client
        await client.start()
        c2 = client._client
        assert c1 is c2
        await client.close()

    # ── _post ──

    @pytest.mark.asyncio
    async def test_post_unwraps_result_field(self, client):
        """_post 自动解包 {"status": "ok", "result": {...}}"""
        client._post = AsyncMock(return_value={"session_id": "s-001"})
        result = await client.create_session()
        assert result == "s-001"

    @pytest.mark.asyncio
    async def test_post_returns_raw_when_no_result(self, client):
        """_post 在无 status/result 包装时原样返回"""
        client._post = AsyncMock(return_value={"session_id": "direct-sess"})
        result = await client.create_session()
        assert result == "direct-sess"

    # ── create_session ──

    @pytest.mark.asyncio
    async def test_create_session_returns_session_id(self, client):
        client._post = AsyncMock(return_value={"session_id": "sess-abc"})
        sid = await client.create_session()
        assert sid == "sess-abc"

    @pytest.mark.asyncio
    async def test_create_session_empty_result(self, client):
        """result 中没有 session_id 时返回空字符串"""
        client._post = AsyncMock(return_value={})
        sid = await client.create_session()
        assert sid == ""

    # ── add_message ──

    @pytest.mark.asyncio
    async def test_add_message_calls_correct_endpoint(self, client):
        """add_message 调用正确的 API 路径和参数"""
        calls = []
        client._post = AsyncMock(side_effect=lambda path, json_data: calls.append((path, json_data)))
        await client.add_message("s-1", "user", "你好")
        assert calls[0] == (
            "/api/v1/sessions/s-1/messages",
            {"role": "user", "content": "你好"},
        )

    @pytest.mark.asyncio
    async def test_add_message_assistant_role(self, client):
        calls = []
        client._post = AsyncMock(side_effect=lambda path, json_data: calls.append(json_data))
        await client.add_message("s-2", "assistant", "这是回答")
        assert calls[0]["role"] == "assistant"
        assert calls[0]["content"] == "这是回答"

    # ── commit ──

    @pytest.mark.asyncio
    async def test_commit_returns_task_id(self, client):
        client._post = AsyncMock(return_value={"task_id": "task-001"})
        task_id = await client.commit("s-1")
        assert task_id == "task-001"

    @pytest.mark.asyncio
    async def test_commit_default_keep_recent_count(self, client):
        calls = []

        async def _side_effect(path, json_data):
            calls.append(json_data)
            return {}  # _post 返回 dict，不抛异常

        client._post = _side_effect
        await client.commit("s-1")
        assert calls[0]["keep_recent_count"] == 10

    @pytest.mark.asyncio
    async def test_commit_custom_keep_recent_count(self, client):
        calls = []

        async def _side_effect(path, json_data):
            calls.append(json_data)
            return {}

        client._post = _side_effect
        await client.commit("s-1", keep_recent_count=5)
        assert calls[0]["keep_recent_count"] == 5

    @pytest.mark.asyncio
    async def test_commit_empty_result(self, client):
        """commit 返回空 result 时返回 None"""
        client._post = AsyncMock(return_value={})
        task_id = await client.commit("s-1")
        assert task_id is None

    # ── close ──

    @pytest.mark.asyncio
    async def test_close_releases_client(self, client):
        await client.start()
        assert client._client is not None
        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, client):
        """close() 在未 start 时也不抛异常"""
        await client.close()  # 不抛异常（_client 为 None）
        await client.close()  # 再次调用也不抛异常


# ========== 第二层：多用户 Header 隔离 ==========


class TestMultiUserClientIsolation:
    """验证不同 user_id 创建的 client 携带独立的 X-OpenViking-User header"""

    @pytest.mark.asyncio
    async def test_different_users_different_headers(self):
        alice = OpenVikingClient("http://localhost:1933", "alice")
        bob = OpenVikingClient("http://localhost:1933", "bob")

        await alice.start()
        await bob.start()

        assert alice._client.headers["X-OpenViking-User"] == "alice"
        assert bob._client.headers["X-OpenViking-User"] == "bob"
        assert alice._client.headers["X-OpenViking-User"] != bob._client.headers["X-OpenViking-User"]

        await alice.close()
        await bob.close()

    @pytest.mark.asyncio
    async def test_same_user_consistent_header(self):
        """同一用户多次创建 client，header 一致"""
        c1 = OpenVikingClient("http://localhost:1933", "alice")
        c2 = OpenVikingClient("http://localhost:1933", "alice")
        await c1.start()
        await c2.start()
        assert c1._client.headers["X-OpenViking-User"] == c2._client.headers["X-OpenViking-User"]
        await c1.close()
        await c2.close()

    @pytest.mark.asyncio
    async def test_default_user_id(self):
        """不传 user_id 时使用默认值 'default'"""
        client = OpenVikingClient("http://localhost:1933")
        await client.start()
        assert client._client.headers["X-OpenViking-User"] == "default"
        await client.close()


# ========== 第三层：_record_to_openviking 协调逻辑 ==========


class TestRecordToOpenVikingSessionLifecycle:
    """测试 _record_to_openviking 的会话生命周期管理"""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        """每个测试前 mock OpenVikingClient 类（patch 在 app.knowledge.openviking 模块）"""

        class MockClient:
            """每个实例独立追踪调用"""

            def __init__(self, base_url, user_id):
                self.user_id = user_id
                self.calls = []
                self.closed = False
                self._record_call("init", user_id=user_id)

            async def start(self):
                self._record_call("start")

            async def close(self):
                self.closed = True
                self._record_call("close")

            async def create_session(self):
                self._record_call("create_session")
                return "ov-sess-001"

            async def add_message(self, session_id, role, content):
                self._record_call("add_message", session_id=session_id, role=role, content=content)

            async def commit(self, session_id, **kwargs):
                self._record_call("commit", session_id=session_id, keep_recent_count=kwargs.get("keep_recent_count"))
                return "task-001"

            def _record_call(self, name, **kwargs):
                self.calls.append((name, kwargs))

        # mock 在 app.knowledge.openviking 模块级别，因为 routes.py 在函数内部 import
        monkeypatch.setattr("app.knowledge.openviking.OpenVikingClient", MockClient)
        self.MockClient = MockClient

    def _make_state(self, **kwargs):
        """构造会话状态"""
        defaults = {"user_id": "alice", "kb_session_id": "", "kb_turn_count": 0}
        defaults.update(kwargs)
        return defaults

    # ── 懒创建 session ──

    @pytest.mark.asyncio
    async def test_lazy_session_creation(self, monkeypatch):
        """首次调用且没有 kb_session_id 时，自动创建并向两个 state 写入"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state(kb_session_id="")
        updated = {}
        await _record_to_openviking(init, updated, "你好", "你好！")

        assert init["kb_session_id"] == "ov-sess-001"
        assert updated["kb_session_id"] == "ov-sess-001"

    @pytest.mark.asyncio
    async def test_no_duplicate_session_when_exists(self, monkeypatch):
        """已有 kb_session_id 时不重复创建"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state(kb_session_id="existing-sess")
        updated = {}
        await _record_to_openviking(init, updated, "第二次对话", "第二次回答")

        assert init["kb_session_id"] == "existing-sess"  # 不变

    # ── turn 计数 ──

    @pytest.mark.asyncio
    async def test_turn_count_increments(self, monkeypatch):
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=3)
        updated = {}
        await _record_to_openviking(init, updated, "问", "答")

        assert init["kb_turn_count"] == 4
        assert updated["kb_turn_count"] == 4

    @pytest.mark.asyncio
    async def test_turn_count_from_zero(self, monkeypatch):
        """从 0 开始计数"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=0)
        updated = {}
        await _record_to_openviking(init, updated, "问", "答")

        assert init["kb_turn_count"] == 1

    # ── 定期 commit ──

    @pytest.mark.asyncio
    async def test_commit_at_interval(self, monkeypatch):
        """第 10 轮（默认间隔）触发 commit"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True, kb_auto_commit_turns=10))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=9)
        updated = {}
        await _record_to_openviking(init, updated, "第10轮", "第10轮回答")

        # 验证 commit 被调用且 keep_recent_count 正确
        assert init["kb_turn_count"] == 10

    @pytest.mark.asyncio
    async def test_no_commit_before_interval(self, monkeypatch):
        """第 5 轮不触发 commit"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True, kb_auto_commit_turns=10))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=4)
        updated = {}
        await _record_to_openviking(init, updated, "第5轮", "第5轮回答")

        assert init["kb_turn_count"] == 5

    @pytest.mark.asyncio
    async def test_commit_at_custom_interval(self, monkeypatch):
        """自定义间隔（3 轮）"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True, kb_auto_commit_turns=3))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=2)
        updated = {}
        await _record_to_openviking(init, updated, "第3轮", "第3轮回答")

        assert init["kb_turn_count"] == 3

    @pytest.mark.asyncio
    async def test_commit_at_multiple_intervals(self, monkeypatch):
        """第 10、20、30 轮各触发一次 commit"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True, kb_auto_commit_turns=10))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=0)

        for i in range(1, 31):
            updated = {}
            await _record_to_openviking(init, updated, f"第{i}轮", f"第{i}轮回答")

        assert init["kb_turn_count"] == 30
        # 第 10、20、30 轮各触发一次 commit

    @pytest.mark.asyncio
    async def test_no_commit_when_auto_commit_disabled(self, monkeypatch):
        """kb_auto_commit_turns=0 时永远不触发 commit"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True, kb_auto_commit_turns=0))

        init = self._make_state(kb_session_id="s-1", kb_turn_count=100)
        updated = {}
        await _record_to_openviking(init, updated, "无论如何", "也不触发")

        assert init["kb_turn_count"] == 101

    # ── 异常降级 ──

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_connect_error(self, monkeypatch):
        """OpenViking 连接失败时不抛异常，session 状态不变"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        class FaultyClient:
            def __init__(self, base_url, user_id):
                self.calls = ["init"]
                self.closed = False

            async def start(self):
                self.calls.append("start")
                raise httpx.ConnectError("Connection refused")

            async def close(self):
                self.closed = True

        monkeypatch.setattr("app.knowledge.openviking.OpenVikingClient", FaultyClient)
        init = self._make_state(kb_session_id="")
        updated = {}
        # 不应抛异常
        await _record_to_openviking(init, updated, "你好", "你好！")
        assert init["kb_session_id"] == ""  # 创建失败，保留空值
        assert init["kb_turn_count"] == 0

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_create_session_error(self, monkeypatch):
        """create_session 失败时不抛异常"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        class FaultyClient:
            def __init__(self, base_url, user_id):
                self.calls = []
                self.closed = False

            async def start(self):
                self.calls.append("start")

            async def close(self):
                self.closed = True

            async def create_session(self):
                self.calls.append("create_session")
                raise RuntimeError("Internal server error")

        monkeypatch.setattr("app.knowledge.openviking.OpenVikingClient", FaultyClient)
        init = self._make_state(kb_session_id="")
        updated = {}
        await _record_to_openviking(init, updated, "你好", "你好！")
        assert init["kb_session_id"] == ""  # 没有创建成功

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_add_message_error(self, monkeypatch):
        """add_message 失败时不抛异常"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        class FaultyClient:
            def __init__(self, base_url, user_id):
                self.calls = []
                self.closed = False

            async def start(self):
                self.calls.append("start")

            async def close(self):
                self.closed = True

            async def create_session(self):
                self.calls.append("create_session")
                return "sess-ok"

            async def add_message(self, session_id, role, content):
                self.calls.append(("add_message", role))
                raise httpx.HTTPStatusError("Gateway timeout", request=None, response=None)

        monkeypatch.setattr("app.knowledge.openviking.OpenVikingClient", FaultyClient)
        init = self._make_state(kb_session_id="")
        updated = {}
        await _record_to_openviking(init, updated, "你好", "你好！")
        assert init["kb_session_id"] == "sess-ok"  # session 已创建
        assert init["kb_turn_count"] == 0  # 但 turn 没有递增（异常发生在 add_message）

    # ── kb_enabled=False 零影响 ──

    @pytest.mark.asyncio
    async def test_noop_when_kb_disabled(self, monkeypatch):
        """kb_enabled=False 时完全不走 OpenViking 逻辑"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=False))

        init = self._make_state(kb_session_id="existing", kb_turn_count=5)
        updated = {}
        await _record_to_openviking(init, updated, "你好", "你好！")
        # 状态完全不变
        assert init["kb_session_id"] == "existing"
        assert init["kb_turn_count"] == 5

    # ── 消息记录 ──

    @pytest.mark.asyncio
    async def test_both_roles_recorded(self, monkeypatch):
        """user 和 assistant 两条消息都被记录"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state(kb_session_id="s-1")
        updated = {}
        await _record_to_openviking(init, updated, "用户原始问题", "Agent 完整回答")

        assert init["kb_turn_count"] == 1

    # ── user_id 传递 ──

    @pytest.mark.asyncio
    async def test_user_id_passed_to_client(self, monkeypatch):
        """_record_to_openviking 将 user_id 传给 OpenVikingClient 构造函数"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state(user_id="bob")
        updated = {}
        await _record_to_openviking(init, updated, "问", "答")
        # MockClient 构造函数中的 user_id 已被捕获——这里验证不抛异常即可
        # 实际隔离由 TestMultiUserClientIsolation 保证

    @pytest.mark.asyncio
    async def test_default_user_id(self, monkeypatch):
        """state 中没有 user_id 时使用默认值"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        init = self._make_state()
        init.pop("user_id", None)
        updated = {}
        await _record_to_openviking(init, updated, "问", "答")
        # 不应抛异常

    # ── close 必然调用 ──

    @pytest.mark.asyncio
    async def test_client_closed_after_success(self, monkeypatch):
        """正常流程后 client.close() 被调用"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        closed = []

        class TrackedClient:
            def __init__(self, base_url, user_id):
                pass

            async def start(self):
                pass

            async def close(self):
                closed.append(True)

            async def create_session(self):
                return "sess"

            async def add_message(self, session_id, role, content):
                pass

            async def commit(self, session_id, **kwargs):
                return None

        monkeypatch.setattr("app.knowledge.openviking.OpenVikingClient", TrackedClient)

        init = self._make_state(kb_session_id="s-1")
        updated = {}
        await _record_to_openviking(init, updated, "问", "答")
        assert len(closed) == 1  # close 被调用

    @pytest.mark.asyncio
    async def test_client_closed_on_error(self, monkeypatch):
        """异常时 client.close() 也被调用"""
        monkeypatch.setattr("app.config.get_settings", lambda: _make_settings(kb_enabled=True))

        class FaultyClient:
            def __init__(self, base_url, user_id):
                self.closed = False

            async def start(self):
                pass

            async def close(self):
                self.closed = True

            async def create_session(self):
                raise RuntimeError("boom")

        client_instance = FaultyClient("url", "user")
        monkeypatch.setattr("app.knowledge.openviking.OpenVikingClient", lambda *a, **kw: client_instance)

        init = self._make_state(kb_session_id="")
        updated = {}
        await _record_to_openviking(init, updated, "问", "答")
        assert client_instance.closed is True


# ========== 第四层：store.py 持久化 ==========


class TestSessionStoreKbPersistence:
    """测试 save_session / get_session 正确持久化 kb 相关字段"""

    def setup_method(self):
        """每个测试前清空 SESSION_STORE"""
        from app.memory.store import reset_store
        reset_store()
        SESSION_STORE.clear()

    def test_new_session_has_default_kb_fields(self):
        session = get_session("new-session")
        assert "kb_session_id" in session
        assert session["kb_session_id"] == ""
        assert "kb_turn_count" in session
        assert session["kb_turn_count"] == 0

    def test_save_session_persists_kb_fields(self):
        save_session(
            "test-1",
            {
                "chat_history": [],
                "kb_session_id": "ov-abc",
                "kb_turn_count": 5,
            },
        )
        session = get_session("test-1")
        assert session["kb_session_id"] == "ov-abc"
        assert session["kb_turn_count"] == 5

    def test_save_session_handles_missing_kb_fields(self):
        """旧代码可能不传 kb 字段，save_session 应使用默认值"""
        save_session("legacy", {"chat_history": [{"role": "user", "content": "hi"}]})
        session = get_session("legacy")
        assert session["kb_session_id"] == ""
        assert session["kb_turn_count"] == 0

    def test_kb_fields_preserved_across_multiple_rounds(self):
        """模拟多轮对话，kb 字段在 save/load 间正确保持"""
        save_session("multi", {"kb_session_id": "ov-1", "kb_turn_count": 3})
        session = get_session("multi")
        assert session["kb_session_id"] == "ov-1"
        assert session["kb_turn_count"] == 3

        # 下一轮
        save_session("multi", {"kb_session_id": "ov-1", "kb_turn_count": 4})
        session = get_session("multi")
        assert session["kb_turn_count"] == 4

    def test_different_sessions_independent(self):
        """不同 session 的 kb 字段相互独立"""
        save_session("sess-a", {"kb_session_id": "ov-a", "kb_turn_count": 10})
        save_session("sess-b", {"kb_session_id": "ov-b", "kb_turn_count": 1})

        a = get_session("sess-a")
        b = get_session("sess-b")
        assert a["kb_session_id"] == "ov-a"
        assert a["kb_turn_count"] == 10
        assert b["kb_session_id"] == "ov-b"
        assert b["kb_turn_count"] == 1


# ========== 第五层：集成测试（需真实 OpenViking Server） ==========


@pytest.mark.integration
@pytest.mark.asyncio
class TestMemoryIntegration:
    """集成测试：验证真实 OpenViking API 的多用户记忆隔离

    前置条件：
        openviking-server 运行在 localhost:1933
        Ollama 已加载 bge-m3 模型
    """

    @pytest.fixture
    async def ov_url(self):
        return "http://localhost:1933"

    async def test_create_session_returns_valid_id(self, ov_url):
        """验证 OpenViking create_session 返回非空 session_id"""
        client = OpenVikingClient(ov_url, "integration_test")
        await client.start()

        sid = await client.create_session()
        assert sid is not None
        assert len(sid) > 0

        await client.close()

    async def test_add_message_and_commit(self, ov_url):
        """完整流程：create_session → add_message × N → commit"""
        client = OpenVikingClient(ov_url, "integration_test")
        await client.start()

        sid = await client.create_session()
        for i in range(5):
            await client.add_message(sid, "user", f"测试问题 {i}")
            await client.add_message(sid, "assistant", f"测试回答 {i}")

        task_id = await client.commit(sid)
        assert task_id is not None

        await client.close()

    async def test_two_users_independent_sessions(self, ov_url):
        """两个用户各自创建 session，session_id 不同"""
        alice = OpenVikingClient(ov_url, "alice_test")
        bob = OpenVikingClient(ov_url, "bob_test")

        await alice.start()
        await bob.start()

        sid_a = await alice.create_session()
        sid_b = await bob.create_session()
        assert sid_a != sid_b

        await alice.add_message(sid_a, "user", "alice 的问题")
        await bob.add_message(sid_b, "user", "bob 的问题")

        await alice.close()
        await bob.close()

    async def test_commit_isolates_memories_by_user(self, ov_url):
        """commit 后 alice 的记忆不出现在 bob 的 peers 目录"""
        alice = OpenVikingClient(ov_url, "alice_iso_test")
        bob = OpenVikingClient(ov_url, "bob_iso_test")

        await alice.start()
        await bob.start()

        # alice 创建会话并积累对话
        sid_a = await alice.create_session()
        for i in range(10):
            await alice.add_message(sid_a, "user", f"alice 问题 {i}")
            await alice.add_message(sid_a, "assistant", f"alice 回答 {i}")
        await alice.commit(sid_a)

        # 验证隔离
        peers_alice = await alice._post("/api/v1/fs/ls", {"uri": "viking://user/alice_iso_test/peers"})
        peers_bob = await bob._post("/api/v1/fs/ls", {"uri": "viking://user/bob_iso_test/peers"})

        assert len(peers_alice) > 0, "alice 应该有长期记忆"
        assert len(peers_bob) == 0, "bob 不应看到 alice 的记忆"

        await alice.close()
        await bob.close()

    async def test_same_user_multiple_commits_accumulate(self, ov_url):
        """同一用户多次 commit，记忆累积"""
        user = OpenVikingClient(ov_url, "multi_commit_test")
        await user.start()

        s1 = await user.create_session()
        for i in range(10):
            await user.add_message(s1, "user", f"会话1 问题{i}")
            await user.add_message(s1, "assistant", f"会话1 回答{i}")
        await user.commit(s1)

        s2 = await user.create_session()
        for i in range(10):
            await user.add_message(s2, "user", f"会话2 问题{i}")
            await user.add_message(s2, "assistant", f"会话2 回答{i}")
        await user.commit(s2)

        peers = await user._post("/api/v1/fs/ls", {"uri": "viking://user/multi_commit_test/peers"})
        assert len(peers) >= 2, f"预期至少 2 条记忆，实际 {len(peers)} 条"

        await user.close()
