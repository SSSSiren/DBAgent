from app.memory.store import (
    DEFAULT_SESSION,
    InMemoryStore,
    SqliteStore,
    StorageBackend,
)
from app.memory.preferences import (
    InMemoryPreferenceStore,
    PreferenceBackend,
    QueryPreferenceStore,
    SqlitePreferenceStore,
)
from app.memory.manager import (
    StorageManager,
    get_storage,
    reset_storage,
)


# ============================================================================
# 向后兼容包装 — 委托给 StorageManager 统一入口
# ============================================================================


def get_store():
    """兼容包装：委托给 get_storage().session_store。

    旧代码通过 ``from app.memory import get_store`` 调用时，
    自动路由到统一 StorageManager 管理的会话后端实例。
    """
    return get_storage().session_store


def get_preference_store():
    """兼容包装：委托给 get_storage().preference_store。

    旧代码通过 ``from app.memory import get_preference_store`` 调用时，
    自动路由到统一 StorageManager 管理的偏好后端实例。
    偏好被禁用时返回 None。
    """
    return get_storage().preference_store


def reset_store():
    """兼容包装：委托给 reset_storage() 重置全局 StorageManager 单例。"""
    reset_storage()


def reset_preference_store():
    """兼容包装：委托给 reset_storage() 重置全局 StorageManager 单例。"""
    reset_storage()


__all__ = [
    # 会话存储
    "DEFAULT_SESSION",
    "InMemoryStore",
    "SqliteStore",
    "StorageBackend",
    "get_store",
    "reset_store",
    # 偏好存储
    "InMemoryPreferenceStore",
    "PreferenceBackend",
    "QueryPreferenceStore",
    "SqlitePreferenceStore",
    "get_preference_store",
    "reset_preference_store",
    # 统一存储管理
    "StorageManager",
    "get_storage",
    "reset_storage",
]