"""
会话级取消事件注册表 — 管理 Agent 执行取消信号的注册、触发和清理

提供进程内单例 CancelEventRegistry，以 session_id 为 key 存储 asyncio.Event，
支持 TTL 过期机制防止内存泄漏。

使用方式：
    from app.agent.cancel import get_cancel_registry

    registry = get_cancel_registry()
    event = registry.create(session_id)   # 创建取消事件
    registry.cancel(session_id)           # 触发取消
    registry.remove(session_id)           # 清理事件
"""

import asyncio
import time


class CancelEventRegistry:
    """会话级取消事件注册表（进程内单例，含 TTL 过期机制）"""

    _TTL_SECONDS = 300  # 5 分钟

    def __init__(self) -> None:
        self._events: dict[str, tuple[asyncio.Event, float]] = {}

    def _purge_expired(self) -> None:
        """投机清理所有过期事件，在 create() 时调用"""
        now = time.monotonic()
        expired = [
            sid
            for sid, (_, created_at) in self._events.items()
            if now - created_at > self._TTL_SECONDS
        ]
        for sid in expired:
            del self._events[sid]

    def create(self, session_id: str) -> asyncio.Event:
        """为会话创建取消事件（自动清理过期条目）。若 session_id 已有事件则先清理旧的"""
        if not session_id:
            raise ValueError("session_id must not be empty")

        self._purge_expired()

        # 若已有事件，先清理旧的（防御性清理）
        if session_id in self._events:
            del self._events[session_id]

        event = asyncio.Event()
        self._events[session_id] = (event, time.monotonic())
        return event

    def cancel(self, session_id: str) -> bool:
        """触发取消信号。返回 True 表示事件存在并已触发"""
        entry = self._events.get(session_id)
        if entry is None:
            return False
        event, _ = entry
        event.set()
        return True

    def remove(self, session_id: str) -> None:
        """清理会话的取消事件"""
        self._events.pop(session_id, None)


# 模块级单例
_registry: CancelEventRegistry | None = None


def get_cancel_registry() -> CancelEventRegistry:
    """获取 CancelEventRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = CancelEventRegistry()
    return _registry


def reset_cancel_registry() -> None:
    """重置注册表单例（仅用于测试）"""
    global _registry
    _registry = None