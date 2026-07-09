"""
会话 CRUD REST 端点测试

测试 POST /api/sessions, GET /api/sessions, GET /api/sessions/{id}, DELETE /api/sessions/{id}
验证 user_id 校验、404 处理、完整生命周期。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.memory.store import reset_store


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_store():
    """每个测试前重置存储，确保测试隔离"""
    reset_store()
    yield
    reset_store()


@pytest.fixture
def client():
    """创建 TestClient"""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


# ── POST /api/sessions ────────────────────────────────────────────────

class TestCreateSession:
    """POST /api/sessions 端点测试"""

    def test_create_session_success(self, client):
        """验证创建会话成功返回 session_id、user_id、created_at"""
        response = client.post("/api/sessions", json={"user_id": "alice"})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["user_id"] == "alice"
        assert "created_at" in data
        # session_id 应为 UUID7 格式（36 字符，含连字符）
        assert len(data["session_id"]) == 36

    def test_create_session_empty_user_id(self, client):
        """验证 user_id 为空字符串时返回 422（Pydantic min_length=1 校验）"""
        response = client.post("/api/sessions", json={"user_id": ""})
        assert response.status_code == 422

    def test_create_session_missing_user_id(self, client):
        """验证缺少 user_id 字段时返回 422（Pydantic 校验）"""
        response = client.post("/api/sessions", json={})
        # Pydantic 会在请求体解析阶段拒绝，返回 422
        assert response.status_code == 422

    def test_create_session_unique_ids(self, client):
        """验证每次创建生成不同的 session_id"""
        r1 = client.post("/api/sessions", json={"user_id": "alice"})
        r2 = client.post("/api/sessions", json={"user_id": "alice"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["session_id"] != r2.json()["session_id"]

    def test_create_session_different_users(self, client):
        """验证不同用户可以创建各自的会话"""
        r1 = client.post("/api/sessions", json={"user_id": "alice"})
        r2 = client.post("/api/sessions", json={"user_id": "bob"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["user_id"] == "alice"
        assert r2.json()["user_id"] == "bob"


# ── GET /api/sessions ─────────────────────────────────────────────────

class TestListSessions:
    """GET /api/sessions 端点测试"""

    def test_list_sessions_empty(self, client):
        """验证新用户列表为空"""
        response = client.get("/api/sessions", params={"user_id": "new_user"})
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["total_count"] == 0

    def test_list_sessions_with_data(self, client):
        """验证创建会话后列表包含该会话"""
        # 创建会话
        client.post("/api/sessions", json={"user_id": "alice"})

        response = client.get("/api/sessions", params={"user_id": "alice"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["sessions"]) == 1
        session = data["sessions"][0]
        assert "session_id" in session
        assert "summary" in session
        assert "created_at" in session
        assert "last_active_at" in session
        assert "message_count" in session

    def test_list_sessions_user_isolation(self, client):
        """验证列表只返回指定用户的会话"""
        client.post("/api/sessions", json={"user_id": "alice"})
        client.post("/api/sessions", json={"user_id": "alice"})
        client.post("/api/sessions", json={"user_id": "bob"})

        alice = client.get("/api/sessions", params={"user_id": "alice"})
        bob = client.get("/api/sessions", params={"user_id": "bob"})

        assert alice.json()["total_count"] == 2
        assert bob.json()["total_count"] == 1

    def test_list_sessions_empty_user_id(self, client):
        """验证 user_id 为空时返回 400"""
        response = client.get("/api/sessions", params={"user_id": ""})
        assert response.status_code == 400

    def test_list_sessions_missing_user_id(self, client):
        """验证缺少 user_id 参数时返回 422（FastAPI Query(...) 校验）"""
        response = client.get("/api/sessions")
        assert response.status_code == 422


# ── GET /api/sessions/{session_id} ────────────────────────────────────

class TestGetSession:
    """GET /api/sessions/{session_id} 端点测试"""

    def test_get_session_success(self, client):
        """验证获取已存在的会话返回完整状态"""
        create_resp = client.post("/api/sessions", json={"user_id": "alice"})
        session_id = create_resp.json()["session_id"]

        response = client.get(
            f"/api/sessions/{session_id}",
            params={"user_id": "alice"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "chat_history" in data
        assert "summary" in data
        assert data["selected_schema_id"] is None

    def test_get_session_not_found(self, client):
        """验证获取不存在的会话返回 404"""
        response = client.get(
            "/api/sessions/nonexistent-id",
            params={"user_id": "alice"},
        )
        assert response.status_code == 404

    def test_get_session_wrong_user(self, client):
        """验证用户 A 无法访问用户 B 的会话（返回 404）"""
        create_resp = client.post("/api/sessions", json={"user_id": "alice"})
        session_id = create_resp.json()["session_id"]

        response = client.get(
            f"/api/sessions/{session_id}",
            params={"user_id": "bob"},
        )
        assert response.status_code == 404

    def test_get_session_empty_user_id(self, client):
        """验证 user_id 为空时返回 400"""
        response = client.get(
            "/api/sessions/some-id",
            params={"user_id": ""},
        )
        assert response.status_code == 400

    def test_get_session_missing_user_id(self, client):
        """验证缺少 user_id 参数时返回 422（FastAPI Query(...) 校验）"""
        response = client.get("/api/sessions/some-id")
        assert response.status_code == 422


# ── DELETE /api/sessions/{session_id} ─────────────────────────────────

class TestDeleteSession:
    """DELETE /api/sessions/{session_id} 端点测试"""

    def test_delete_session_success(self, client):
        """验证删除已存在的会话返回成功"""
        create_resp = client.post("/api/sessions", json={"user_id": "alice"})
        session_id = create_resp.json()["session_id"]

        response = client.delete(
            f"/api/sessions/{session_id}",
            params={"user_id": "alice"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["session_id"] == session_id

    def test_delete_session_not_found(self, client):
        """验证删除不存在的会话返回 404"""
        response = client.delete(
            "/api/sessions/nonexistent-id",
            params={"user_id": "alice"},
        )
        assert response.status_code == 404

    def test_delete_session_twice(self, client):
        """验证第二次删除同一会话返回 404"""
        create_resp = client.post("/api/sessions", json={"user_id": "alice"})
        session_id = create_resp.json()["session_id"]

        # 第一次删除成功
        r1 = client.delete(f"/api/sessions/{session_id}", params={"user_id": "alice"})
        assert r1.status_code == 200

        # 第二次删除返回 404
        r2 = client.delete(f"/api/sessions/{session_id}", params={"user_id": "alice"})
        assert r2.status_code == 404

    def test_delete_session_wrong_user(self, client):
        """验证用户 A 无法删除用户 B 的会话（返回 404）"""
        create_resp = client.post("/api/sessions", json={"user_id": "alice"})
        session_id = create_resp.json()["session_id"]

        response = client.delete(
            f"/api/sessions/{session_id}",
            params={"user_id": "bob"},
        )
        assert response.status_code == 404

    def test_delete_session_empty_user_id(self, client):
        """验证 user_id 为空时返回 400"""
        response = client.delete(
            "/api/sessions/some-id",
            params={"user_id": ""},
        )
        assert response.status_code == 400

    def test_delete_session_missing_user_id(self, client):
        """验证缺少 user_id 参数时返回 422（FastAPI Query(...) 校验）"""
        response = client.delete("/api/sessions/some-id")
        assert response.status_code == 422


# ── 完整生命周期 ──────────────────────────────────────────────────────

class TestSessionLifecycle:
    """会话完整生命周期测试"""

    def test_full_lifecycle(self, client):
        """验证创建 -> 列表 -> 获取 -> 删除 -> 404 的完整流程"""
        user_id = "alice"

        # 1. 创建会话
        create_resp = client.post("/api/sessions", json={"user_id": user_id})
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        # 2. 列表包含该会话
        list_resp = client.get("/api/sessions", params={"user_id": user_id})
        assert list_resp.status_code == 200
        assert list_resp.json()["total_count"] == 1
        assert list_resp.json()["sessions"][0]["session_id"] == session_id

        # 3. 获取会话详情
        get_resp = client.get(
            f"/api/sessions/{session_id}",
            params={"user_id": user_id},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["session_id"] == session_id

        # 4. 删除会话
        delete_resp = client.delete(
            f"/api/sessions/{session_id}",
            params={"user_id": user_id},
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

        # 5. 删除后列表为空
        list_resp2 = client.get("/api/sessions", params={"user_id": user_id})
        assert list_resp2.json()["total_count"] == 0

        # 6. 删除后获取返回 404
        get_resp2 = client.get(
            f"/api/sessions/{session_id}",
            params={"user_id": user_id},
        )
        assert get_resp2.status_code == 404

    def test_multi_user_lifecycle(self, client):
        """验证多用户场景下的会话隔离"""
        # alice 创建 2 个会话
        r1 = client.post("/api/sessions", json={"user_id": "alice"})
        sid1 = r1.json()["session_id"]
        r2 = client.post("/api/sessions", json={"user_id": "alice"})
        sid2 = r2.json()["session_id"]

        # bob 创建 1 个会话
        r3 = client.post("/api/sessions", json={"user_id": "bob"})
        sid3 = r3.json()["session_id"]

        # alice 看到 2 个
        alice_list = client.get("/api/sessions", params={"user_id": "alice"})
        assert alice_list.json()["total_count"] == 2

        # bob 看到 1 个
        bob_list = client.get("/api/sessions", params={"user_id": "bob"})
        assert bob_list.json()["total_count"] == 1

        # alice 删除自己的一个会话
        client.delete(f"/api/sessions/{sid1}", params={"user_id": "alice"})

        # alice 现在看到 1 个
        alice_list2 = client.get("/api/sessions", params={"user_id": "alice"})
        assert alice_list2.json()["total_count"] == 1

        # bob 仍然看到 1 个
        bob_list2 = client.get("/api/sessions", params={"user_id": "bob"})
        assert bob_list2.json()["total_count"] == 1