"""
会话存储 — 进程内存会话管理

设计：
- 使用进程内存字典存储会话状态
- 会话在进程重启后丢失（生产环境建议替换为 Redis）
- 消息格式为纯 dict（JSON 可序列化），不依赖任何框架特定类型
- threading.Lock 为防御性并发保护（单线程 asyncio 下 dict 操作本身安全）
"""

import threading
from typing import Any


# 进程内存会话存储
# key: session_id (str)
# value: session state dict
SESSION_STORE: dict[str, dict[str, Any]] = {}
_store_lock = threading.Lock()

# 默认会话设置
DEFAULT_SESSION: dict[str, Any] = {
    "chat_history": [],
    "summary": "",
    "selected_schema_id": None,
    "selected_database": None,
    "kb_session_id": "",       # OpenViking 会话 ID（首次对话时自动创建）
    "kb_turn_count": 0,        # 当前会话轮次（用于自动 commit）
}


def get_session(session_id: str) -> dict[str, Any]:
    """
    获取或创建会话。如果会话不存在，自动创建新会话。
    """
    with _store_lock:
        if session_id not in SESSION_STORE:
            SESSION_STORE[session_id] = {
                "session_id": session_id,
                **DEFAULT_SESSION,
            }
        return SESSION_STORE[session_id]


def save_session(session_id: str, state: dict[str, Any]) -> None:
    """保存会话状态"""
    with _store_lock:
        SESSION_STORE[session_id] = {
            "session_id": session_id,
            "chat_history": state.get("chat_history", []),
            "summary": state.get("summary", ""),
            "selected_schema_id": state.get("selected_schema_id"),
            "selected_database": state.get("selected_database"),
            "kb_session_id": state.get("kb_session_id", ""),
            "kb_turn_count": state.get("kb_turn_count", 0),
        }


def delete_session(session_id: str) -> None:
    """删除会话"""
    with _store_lock:
        SESSION_STORE.pop(session_id, None)


def list_sessions() -> list[str]:
    """列出所有会话 ID"""
    with _store_lock:
        return list(SESSION_STORE.keys())


def session_count() -> int:
    """获取会话数量"""
    with _store_lock:
        return len(SESSION_STORE)