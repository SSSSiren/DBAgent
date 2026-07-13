"""
存储管理器 — 统一存储生命周期管理

StorageManager 拥有会话存储和偏好存储两个后端的生命周期，
提供单一访问入口。按依赖顺序初始化（先会话后偏好），
逆序关闭（先偏好后会话）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.config import get_settings

if TYPE_CHECKING:
    from app.memory.store import StorageBackend
    from app.memory.preferences import PreferenceBackend


class StorageManager:
    """统一存储生命周期管理器。

    拥有会话存储和偏好存储两个后端的 initialize / close 生命周期。
    按依赖顺序初始化（先会话后偏好），逆序关闭。
    偏好被禁用时 preference_store 为 None，不阻断会话存储。

    通过依赖注入接受已创建的后端实例，不自行创建后端。
    """

    def __init__(
        self,
        *,
        session_store: StorageBackend,
        preference_store: PreferenceBackend | None = None,
    ) -> None:
        """
        Args:
            session_store: 会话存储后端实例（必需）
            preference_store: 偏好存储后端实例（可选，禁用时为 None）
        """
        self.session_store = session_store
        self.preference_store = preference_store

    async def initialize(self) -> None:
        """按序初始化所有已注册的存储后端。

        先初始化会话存储，若偏好存储存在则随后初始化。
        任一后端初始化失败时异常向上传播。
        """
        await self.session_store.initialize()
        if self.preference_store is not None:
            await self.preference_store.initialize()

    async def close(self) -> None:
        """按逆序关闭所有已初始化的存储后端。

        先关闭偏好存储（若存在），再关闭会话存储。
        任一后端关闭失败时异常向上传播。
        """
        if self.preference_store is not None:
            await self.preference_store.close()
        await self.session_store.close()


# ============================================================================
# 工厂函数
# ============================================================================

_storage: Optional[StorageManager] = None


def get_storage() -> StorageManager:
    """
    获取 StorageManager 单例。

    根据 Settings.storage_backend 配置创建对应的会话和偏好后端实例，
    注入 StorageManager 并返回模块级单例。

    后端选择规则：
    - "memory" → InMemoryStore + InMemoryPreferenceStore
    - "sqlite"  → SqliteStore + SqlitePreferenceStore

    偏好后端类型跟随会话后端类型选择。
    preference_enabled=False 时跳过偏好后端创建，preference_store 为 None。
    storage_backend 值非法时抛出 ValueError。

    Returns:
        StorageManager 实例（单例）
    """
    global _storage
    if _storage is not None:
        return _storage

    settings = get_settings()
    backend = settings.storage_backend

    # 创建会话后端
    if backend == "memory":
        from app.memory.store import InMemoryStore
        session_store = InMemoryStore()
    elif backend == "sqlite":
        from app.memory.store import SqliteStore
        session_store = SqliteStore(settings.storage_file_path)
    else:
        raise ValueError(
            f"不支持的存储后端类型: '{backend}'。"
            f"支持的后端: 'memory', 'sqlite'。"
            f"请检查 STORAGE_BACKEND 环境变量配置。"
        )

    # 创建偏好后端（类型跟随会话后端）
    preference_store = None
    if settings.preference_enabled:
        if backend == "memory":
            from app.memory.preferences import InMemoryPreferenceStore
            preference_store = InMemoryPreferenceStore()
        elif backend == "sqlite":
            from app.memory.preferences import SqlitePreferenceStore
            preference_store = SqlitePreferenceStore(settings.storage_file_path)

    _storage = StorageManager(
        session_store=session_store,
        preference_store=preference_store,
    )
    return _storage


def reset_storage() -> None:
    """重置全局 StorageManager 实例（仅用于测试隔离）。

    将模块级单例设为 None，下次 get_storage() 调用时会创建新实例。
    """
    global _storage
    _storage = None
