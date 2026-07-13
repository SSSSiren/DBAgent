"""
存储管理器 — 统一存储生命周期管理

StorageManager 拥有会话存储和偏好存储两个后端的生命周期，
提供单一访问入口。按依赖顺序初始化（先会话后偏好），
逆序关闭（先偏好后会话）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
