"""
StorageManager 单元测试

验证：
- initialize() 按序初始化（先会话后偏好）
- close() 逆序关闭（先偏好后会话）
- 偏好禁用（preference_store=None）时优雅降级
- 初始化失败时异常向上传播
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.manager import StorageManager
from app.memory.store import StorageBackend
from app.memory.preferences import PreferenceBackend


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
