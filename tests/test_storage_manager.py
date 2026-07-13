"""
StorageManager 单元测试

验证：
- initialize() 按序初始化（先会话后偏好）
- close() 逆序关闭（先偏好后会话）
- 偏好禁用（preference_store=None）时优雅降级
- 初始化失败时异常向上传播
- get_storage() 工厂函数的配置分发
- reset_storage() 单例重置
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.memory.manager import StorageManager, get_storage, reset_storage
from app.memory.store import InMemoryStore, SqliteStore, StorageBackend
from app.memory.preferences import (
    InMemoryPreferenceStore,
    PreferenceBackend,
    SqlitePreferenceStore,
)


# ============================================================================
# Mock 后端工厂
# ============================================================================

def _make_mock_session_store() -> MagicMock:
    """创建模拟的会话存储后端"""
    mock = MagicMock(spec=StorageBackend)
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()
    return mock


def _make_mock_preference_store() -> MagicMock:
    """创建模拟的偏好存储后端"""
    mock = MagicMock(spec=PreferenceBackend)
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()
    return mock


# ============================================================================
# 构造函数测试
# ============================================================================

class TestStorageManagerConstruction:
    """验证 StorageManager 构造函数"""

    def test_accepts_session_and_preference_stores(self):
        """构造函数接受会话存储和偏好存储实例"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()

        manager = StorageManager(session_store=session, preference_store=pref)

        assert manager.session_store is session
        assert manager.preference_store is pref

    def test_preference_store_can_be_none(self):
        """偏好存储可以为 None（偏好禁用场景）"""
        session = _make_mock_session_store()

        manager = StorageManager(session_store=session, preference_store=None)

        assert manager.session_store is session
        assert manager.preference_store is None

    def test_does_not_create_backends(self):
        """StorageManager 不自行创建后端实例（依赖注入）"""
        session = _make_mock_session_store()

        manager = StorageManager(session_store=session)

        # session_store 应该是直接传入的同一个实例
        assert manager.session_store is session


# ============================================================================
# initialize() 测试
# ============================================================================

class TestInitialize:
    """验证 StorageManager.initialize() 行为"""

    @pytest.mark.asyncio
    async def test_initializes_session_first_then_preference(self):
        """initialize() 先初始化会话存储，再初始化偏好存储"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()

        manager = StorageManager(session_store=session, preference_store=pref)
        await manager.initialize()

        # 验证两者都被调用了
        session.initialize.assert_awaited_once()
        pref.initialize.assert_awaited_once()

        # 验证调用顺序：session 先于 preference
        parent_mock = MagicMock()
        parent_mock.attach_mock(session.initialize, "session_init")
        parent_mock.attach_mock(pref.initialize, "pref_init")

        # 重新创建以使用 parent_mock
        session2 = _make_mock_session_store()
        pref2 = _make_mock_preference_store()
        parent_mock.attach_mock(session2.initialize, "session_init")
        parent_mock.attach_mock(pref2.initialize, "pref_init")

        manager2 = StorageManager(session_store=session2, preference_store=pref2)
        await manager2.initialize()

        # 验证顺序：session_init 在 pref_init 之前
        calls = parent_mock.mock_calls
        session_idx = next(i for i, c in enumerate(calls) if "session_init" in str(c))
        pref_idx = next(i for i, c in enumerate(calls) if "pref_init" in str(c))
        assert session_idx < pref_idx, (
            f"Expected session.initialize() before preference.initialize(), "
            f"got session at {session_idx}, pref at {pref_idx}"
        )

    @pytest.mark.asyncio
    async def test_initializes_only_session_when_preference_none(self):
        """偏好存储为 None 时，只初始化会话存储"""
        session = _make_mock_session_store()

        manager = StorageManager(session_store=session, preference_store=None)
        await manager.initialize()

        session.initialize.assert_awaited_once()
        # 偏好存储不应该被调用（不存在）

    @pytest.mark.asyncio
    async def test_propagates_session_initialize_error(self):
        """会话存储初始化失败时，异常向上传播"""
        session = _make_mock_session_store()
        session.initialize.side_effect = RuntimeError("Session init failed")
        pref = _make_mock_preference_store()

        manager = StorageManager(session_store=session, preference_store=pref)

        with pytest.raises(RuntimeError, match="Session init failed"):
            await manager.initialize()

        # 偏好存储不应该被初始化
        pref.initialize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_propagates_preference_initialize_error(self):
        """偏好存储初始化失败时，异常向上传播"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()
        pref.initialize.side_effect = RuntimeError("Pref init failed")

        manager = StorageManager(session_store=session, preference_store=pref)

        with pytest.raises(RuntimeError, match="Pref init failed"):
            await manager.initialize()

        # 会话存储应该已经被初始化了
        session.initialize.assert_awaited_once()
        # 偏好存储初始化尝试过了
        pref.initialize.assert_awaited_once()


# ============================================================================
# close() 测试
# ============================================================================

class TestClose:
    """验证 StorageManager.close() 行为"""

    @pytest.mark.asyncio
    async def test_closes_preference_first_then_session(self):
        """close() 先关闭偏好存储，再关闭会话存储（逆序）"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()

        parent_mock = MagicMock()
        parent_mock.attach_mock(session.close, "session_close")
        parent_mock.attach_mock(pref.close, "pref_close")

        manager = StorageManager(session_store=session, preference_store=pref)
        await manager.close()

        # 验证顺序：pref_close 在 session_close 之前（逆序）
        calls = parent_mock.mock_calls
        pref_idx = next(i for i, c in enumerate(calls) if "pref_close" in str(c))
        session_idx = next(i for i, c in enumerate(calls) if "session_close" in str(c))
        assert pref_idx < session_idx, (
            f"Expected preference.close() before session.close() (reverse order), "
            f"got pref at {pref_idx}, session at {session_idx}"
        )

    @pytest.mark.asyncio
    async def test_closes_only_session_when_preference_none(self):
        """偏好存储为 None 时，只关闭会话存储"""
        session = _make_mock_session_store()

        manager = StorageManager(session_store=session, preference_store=None)
        await manager.close()

        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_propagates_session_close_error(self):
        """会话存储关闭失败时，异常向上传播"""
        session = _make_mock_session_store()
        session.close.side_effect = RuntimeError("Session close failed")

        manager = StorageManager(session_store=session, preference_store=None)

        with pytest.raises(RuntimeError, match="Session close failed"):
            await manager.close()

    @pytest.mark.asyncio
    async def test_propagates_preference_close_error(self):
        """偏好存储关闭失败时，异常向上传播"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()
        pref.close.side_effect = RuntimeError("Pref close failed")

        manager = StorageManager(session_store=session, preference_store=pref)

        with pytest.raises(RuntimeError, match="Pref close failed"):
            await manager.close()

        # 会话存储不应该被关闭（偏好关闭失败后不再继续）
        session.close.assert_not_awaited()


# ============================================================================
# 集成场景测试
# ============================================================================

class TestFullLifecycle:
    """验证完整的初始化→关闭生命周期"""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_both_stores(self):
        """两个后端都启用时的完整生命周期"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()

        manager = StorageManager(session_store=session, preference_store=pref)

        # 初始化
        await manager.initialize()
        session.initialize.assert_awaited_once()
        pref.initialize.assert_awaited_once()

        # 关闭
        await manager.close()
        session.close.assert_awaited_once()
        pref.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_lifecycle_preference_disabled(self):
        """偏好禁用时的完整生命周期"""
        session = _make_mock_session_store()

        manager = StorageManager(session_store=session, preference_store=None)

        # 初始化
        await manager.initialize()
        session.initialize.assert_awaited_once()

        # 关闭
        await manager.close()
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_without_initialize(self):
        """未初始化也可以关闭（优雅处理）"""
        session = _make_mock_session_store()
        pref = _make_mock_preference_store()

        manager = StorageManager(session_store=session, preference_store=pref)
        await manager.close()

        # 两个都应该尝试关闭
        pref.close.assert_awaited_once()
        session.close.assert_awaited_once()


# ============================================================================
# get_storage() 工厂函数测试
# ============================================================================

class TestGetStorage:
    """验证 get_storage() 工厂函数的行为"""

    def test_returns_storage_manager_with_memory_backend(self, monkeypatch):
        """storage_backend="memory" 时返回包含 InMemoryStore + InMemoryPreferenceStore 的 StorageManager"""
        reset_storage()
        settings = Settings(storage_backend="memory", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        storage = get_storage()

        assert isinstance(storage, StorageManager)
        assert isinstance(storage.session_store, InMemoryStore)
        assert isinstance(storage.preference_store, InMemoryPreferenceStore)

    def test_returns_storage_manager_with_sqlite_backend(self, monkeypatch, tmp_path):
        """storage_backend="sqlite" 时返回包含 SqliteStore + SqlitePreferenceStore 的 StorageManager"""
        reset_storage()
        db_path = tmp_path / "test.db"
        settings = Settings(
            storage_backend="sqlite",
            storage_file_path=str(db_path),
            preference_enabled=True,
        )
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        storage = get_storage()

        assert isinstance(storage, StorageManager)
        assert isinstance(storage.session_store, SqliteStore)
        assert isinstance(storage.preference_store, SqlitePreferenceStore)

    def test_preference_none_when_disabled(self, monkeypatch):
        """preference_enabled=False 时 preference_store 应为 None"""
        reset_storage()
        settings = Settings(storage_backend="memory", preference_enabled=False)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        storage = get_storage()

        assert isinstance(storage, StorageManager)
        assert isinstance(storage.session_store, InMemoryStore)
        assert storage.preference_store is None

    def test_sqlite_preference_none_when_disabled(self, monkeypatch, tmp_path):
        """SQLite 后端 + preference_enabled=False 时 preference_store 应为 None"""
        reset_storage()
        db_path = tmp_path / "test.db"
        settings = Settings(
            storage_backend="sqlite",
            storage_file_path=str(db_path),
            preference_enabled=False,
        )
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        storage = get_storage()

        assert isinstance(storage, StorageManager)
        assert isinstance(storage.session_store, SqliteStore)
        assert storage.preference_store is None

    def test_raises_value_error_for_invalid_backend(self, monkeypatch):
        """storage_backend 值非法时抛出 ValueError"""
        reset_storage()
        settings = Settings(storage_backend="redis", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        with pytest.raises(ValueError, match="不支持的存储后端"):
            get_storage()

    def test_raises_value_error_for_empty_backend(self, monkeypatch):
        """storage_backend 为空字符串时抛出 ValueError"""
        reset_storage()
        settings = Settings(storage_backend="", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        with pytest.raises(ValueError, match="不支持的存储后端"):
            get_storage()

    def test_singleton_returns_same_instance(self, monkeypatch):
        """多次调用 get_storage() 返回同一个实例"""
        reset_storage()
        settings = Settings(storage_backend="memory", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        s1 = get_storage()
        s2 = get_storage()

        assert s1 is s2
        assert s1.session_store is s2.session_store
        assert s1.preference_store is s2.preference_store

    def test_preference_type_follows_session_backend(self, monkeypatch):
        """偏好后端类型跟随会话后端类型（memory → InMemory, sqlite → Sqlite）"""
        reset_storage()
        settings = Settings(storage_backend="memory", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        storage = get_storage()
        assert isinstance(storage.preference_store, InMemoryPreferenceStore)

        reset_storage()
        db_path = "/tmp/test_follow.db"
        settings2 = Settings(
            storage_backend="sqlite",
            storage_file_path=db_path,
            preference_enabled=True,
        )
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings2)

        storage2 = get_storage()
        assert isinstance(storage2.preference_store, SqlitePreferenceStore)


# ============================================================================
# reset_storage() 测试
# ============================================================================

class TestResetStorage:
    """验证 reset_storage() 行为"""

    def test_reset_creates_fresh_instance(self, monkeypatch):
        """reset_storage() 后 next get_storage() 创建新实例"""
        settings = Settings(storage_backend="memory", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        reset_storage()
        s1 = get_storage()

        reset_storage()
        s2 = get_storage()

        assert s1 is not s2, "reset_storage() 后应创建新实例"
        assert s1.session_store is not s2.session_store

    def test_reset_before_first_call_is_noop(self, monkeypatch):
        """首次调用前 reset_storage() 为无害操作"""
        reset_storage()
        reset_storage()  # 多次调用也不应出错

        settings = Settings(storage_backend="memory", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings)

        storage = get_storage()
        assert isinstance(storage, StorageManager)

    def test_reset_allows_backend_change(self, monkeypatch):
        """reset_storage() 后可以切换后端类型"""
        # 先用 memory 后端
        settings_mem = Settings(storage_backend="memory", preference_enabled=True)
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings_mem)
        reset_storage()
        s1 = get_storage()
        assert isinstance(s1.session_store, InMemoryStore)

        # reset 后切换到 sqlite
        reset_storage()
        db_path = "/tmp/test_reset_switch.db"
        settings_sqlite = Settings(
            storage_backend="sqlite",
            storage_file_path=db_path,
            preference_enabled=True,
        )
        monkeypatch.setattr("app.memory.manager.get_settings", lambda: settings_sqlite)
        s2 = get_storage()
        assert isinstance(s2.session_store, SqliteStore)
