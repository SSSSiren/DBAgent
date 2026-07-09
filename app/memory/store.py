"""
会话存储 — 支持多后端的会话持久化管理

设计：
- StorageBackend 协议定义标准会话 CRUD 接口，所有后端实现该协议
- InMemoryStore 将现有进程内存 dict 封装为协议实现（开发/测试用）
- 工厂函数 get_store() 根据 Settings.storage_backend 返回对应后端实例
- 所有方法接受 user_id 作为第一个参数，实现用户级命名空间隔离
- 保留原有同步函数作为向后兼容包装器，委托给全局 InMemoryStore 实例
"""

from __future__ import annotations

import asyncio
import datetime
import threading
from typing import Any, Optional, Protocol, runtime_checkable

from app.config import get_settings


# ============================================================================
# StorageBackend 协议
# ============================================================================

@runtime_checkable
class StorageBackend(Protocol):
    """会话存储抽象协议 — 所有存储后端必须实现此接口"""

    async def create_session(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """
        创建新会话并写入初始状态。

        Args:
            user_id: 用户标识
            session_id: 会话标识
            state: 初始会话状态字典
        """
        ...

    async def get_session(self, user_id: str, session_id: str) -> Optional[dict[str, Any]]:
        """
        获取会话状态。

        Args:
            user_id: 用户标识
            session_id: 会话标识

        Returns:
            会话状态字典，不存在时返回 None
        """
        ...

    async def save_session(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """
        保存或更新会话状态。

        Args:
            user_id: 用户标识
            session_id: 会话标识
            state: 会话状态字典
        """
        ...

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """
        删除会话。

        Args:
            user_id: 用户标识
            session_id: 会话标识

        Returns:
            True 表示成功删除，False 表示会话不存在
        """
        ...

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """
        列出属于该用户的所有会话摘要列表。

        Args:
            user_id: 用户标识

        Returns:
            会话摘要列表，每项包含 session_id、summary、created_at、last_active_at、message_count
        """
        ...

    async def initialize(self) -> None:
        """初始化存储（创建表等），启动时调用一次"""
        ...

    async def close(self) -> None:
        """关闭存储连接，关闭时调用一次"""
        ...


# ============================================================================
# InMemoryStore — 内存存储实现
# ============================================================================

# 默认会话模板
DEFAULT_SESSION: dict[str, Any] = {
    "chat_history": [],
    "summary": "",
    "selected_schema_id": None,
    "selected_database": None,
    "kb_session_id": "",       # OpenViking 会话 ID（首次对话时自动创建）
    "kb_turn_count": 0,        # 当前会话轮次（用于自动 commit）
}


class InMemoryStore:
    """
    进程内存会话存储，实现 StorageBackend 协议。

    使用 (user_id, session_id) 复合键实现用户隔离。
    会话在进程重启后丢失（生产环境建议使用 SqliteStore 或 Redis）。
    threading.Lock 为防御性并发保护（单线程 asyncio 下 dict 操作本身安全）。
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _make_session_summary(
        user_id: str,
        session_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """从会话状态构建摘要"""
        chat_history = state.get("chat_history", [])
        return {
            "session_id": session_id,
            "user_id": user_id,
            "summary": state.get("summary", ""),
            "created_at": state.get("created_at", ""),
            "last_active_at": state.get("last_active_at", ""),
            "message_count": len(chat_history),
        }

    # ── StorageBackend 协议方法 ───────────────────────────────

    async def create_session(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """
        创建新会话并写入初始状态。

        如果会话已存在，覆盖写入（幂等操作）。
        """
        now = datetime.datetime.now().isoformat()
        # 深拷贝 chat_history，避免多会话共享同一个可变列表
        chat_history = list(state.get("chat_history", []))
        with self._lock:
            self._store[(user_id, session_id)] = {
                **state,
                "chat_history": chat_history,
                "session_id": session_id,
                "user_id": user_id,
                "created_at": state.get("created_at", now),
                "last_active_at": state.get("last_active_at", now),
            }

    async def get_session(self, user_id: str, session_id: str) -> Optional[dict[str, Any]]:
        """
        获取会话状态。

        Returns:
            会话状态字典，不存在时返回 None
        """
        with self._lock:
            return self._store.get((user_id, session_id))

    async def save_session(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """
        保存或更新会话状态。

        会话不存在时自动创建（兼容旧行为）。
        """
        now = datetime.datetime.now().isoformat()
        with self._lock:
            key = (user_id, session_id)
            existing = self._store.get(key)
            created_at = existing.get("created_at", now) if existing else state.get("created_at", now)
            self._store[key] = {
                **state,
                "session_id": session_id,
                "user_id": user_id,
                "created_at": created_at,
                "last_active_at": now,
            }

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """
        删除会话。

        Returns:
            True 表示成功删除，False 表示会话不存在
        """
        with self._lock:
            key = (user_id, session_id)
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """
        列出属于该用户的所有会话摘要列表。

        Returns:
            会话摘要列表，按 last_active_at 降序排列
        """
        with self._lock:
            sessions = [
                self._make_session_summary(user_id, sid, state)
                for (uid, sid), state in self._store.items()
                if uid == user_id
            ]
        # 按 last_active_at 降序
        sessions.sort(key=lambda s: s.get("last_active_at", ""), reverse=True)
        return sessions

    async def initialize(self) -> None:
        """初始化存储（内存存储无需操作）"""
        pass

    async def close(self) -> None:
        """关闭存储连接（内存存储无需操作）"""
        pass


# ============================================================================
# SqliteStore — SQLite 持久化存储实现
# ============================================================================

class SqliteStore:
    """
    SQLite 持久化会话存储，实现 StorageBackend 协议。

    将会话数据持久化到 SQLite 数据库文件（或 :memory: 用于测试）。
    使用 WAL 模式支持并发读写，复合主键 (user_id, session_id) 确保用户隔离。

    数据库文件路径通过 Settings.storage_file_path 配置，默认为 data/sessions.db。
    """

    def __init__(self, db_path: str = "data/sessions.db") -> None:
        self._db_path = db_path
        self._conn: Any = None

    # ── StorageBackend 协议方法 ───────────────────────────────

    async def initialize(self) -> None:
        """
        初始化存储：连接数据库、启用 WAL 模式、创建表和索引。

        幂等操作 — 多次调用不会重复创建表。
        """
        import aiosqlite

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        # 启用 WAL 模式以支持并发读写
        await self._conn.execute("PRAGMA journal_mode=WAL;")

        # 创建 sessions 表（复合主键 user_id + session_id）
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                state_json TEXT NOT NULL DEFAULT '{}',
                summary TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_active_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, session_id)
            );
        """)

        # 创建索引
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(user_id, last_active_at DESC);"
        )

        await self._conn.commit()

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def create_session(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """
        创建新会话并写入初始状态。

        如果会话已存在，覆盖写入（幂等操作）。
        """
        import json

        now = datetime.datetime.now().isoformat()
        state_to_save = {
            **state,
            "session_id": session_id,
            "user_id": user_id,
            "created_at": state.get("created_at", now),
            "last_active_at": state.get("last_active_at", now),
        }
        summary = state.get("summary", "")

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO sessions (user_id, session_id, state_json, summary, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (user_id, session_id, json.dumps(state_to_save, ensure_ascii=False), summary,
             state_to_save["created_at"], state_to_save["last_active_at"]),
        )
        await self._conn.commit()

    async def get_session(self, user_id: str, session_id: str) -> Optional[dict[str, Any]]:
        """
        获取会话状态。

        Returns:
            会话状态字典，不存在时返回 None
        """
        import json

        cursor = await self._conn.execute(
            "SELECT state_json FROM sessions WHERE user_id = ? AND session_id = ?;",
            (user_id, session_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["state_json"])

    async def save_session(self, user_id: str, session_id: str, state: dict[str, Any]) -> None:
        """
        保存或更新会话状态。

        将会话状态序列化为 JSON 存入 state_json 列，
        同步更新 summary 和 last_active_at。
        会话不存在时自动创建。
        """
        import json

        now = datetime.datetime.now().isoformat()

        # 保留原有的 created_at（如果存在）
        existing = await self.get_session(user_id, session_id)
        created_at = existing.get("created_at", now) if existing else state.get("created_at", now)

        state_to_save = {
            **state,
            "session_id": session_id,
            "user_id": user_id,
            "created_at": created_at,
            "last_active_at": now,
        }
        summary = state.get("summary", "")

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO sessions (user_id, session_id, state_json, summary, created_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (user_id, session_id, json.dumps(state_to_save, ensure_ascii=False), summary,
             created_at, now),
        )
        await self._conn.commit()

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """
        删除会话。

        Returns:
            True 表示成功删除，False 表示会话不存在
        """
        cursor = await self._conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND session_id = ?;",
            (user_id, session_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """
        列出属于该用户的所有会话摘要列表。

        按 last_active_at 降序排列。

        Returns:
            会话摘要列表，每项包含 session_id、user_id、summary、created_at、
            last_active_at、message_count
        """
        import json

        cursor = await self._conn.execute(
            """
            SELECT session_id, state_json, summary, created_at, last_active_at
            FROM sessions
            WHERE user_id = ?
            ORDER BY last_active_at DESC;
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

        summaries: list[dict[str, Any]] = []
        for row in rows:
            try:
                state = json.loads(row["state_json"])
            except (json.JSONDecodeError, TypeError):
                state = {}
            chat_history = state.get("chat_history", [])
            summaries.append({
                "session_id": row["session_id"],
                "user_id": user_id,
                "summary": row["summary"] or "",
                "created_at": row["created_at"] or "",
                "last_active_at": row["last_active_at"] or "",
                "message_count": len(chat_history),
            })

        return summaries


# ============================================================================
# 工厂函数
# ============================================================================

_store: Optional[InMemoryStore] = None


def get_store() -> StorageBackend:
    """
    获取存储后端实例。

    根据 Settings.storage_backend 配置返回对应实现：
    - "memory"（默认）：InMemoryStore
    - "sqlite"：SqliteStore（后续任务实现）

    Returns:
        StorageBackend 实例（单例）
    """
    global _store
    if _store is not None:
        return _store

    settings = get_settings()
    backend = settings.storage_backend

    if backend == "memory":
        _store = InMemoryStore()
    elif backend == "sqlite":
        # 延迟导入 aiosqlite，避免未安装时崩溃
        try:
            import aiosqlite  # noqa: F401
            _store = SqliteStore(settings.storage_file_path)
        except ImportError:
            print(f"[store] aiosqlite 未安装，降级到 InMemoryStore")
            _store = InMemoryStore()
    else:
        print(f"[store] 未知存储后端 '{backend}'，使用默认 InMemoryStore")
        _store = InMemoryStore()

    return _store


def reset_store() -> None:
    """重置全局存储实例（仅用于测试）。总是使用 InMemoryStore 确保测试隔离。"""
    global _store
    _store = InMemoryStore()


# ============================================================================
# 向后兼容同步包装器
# ============================================================================
#
# 这些函数保持与旧代码的兼容性，供 app/api/routes.py 和 app/agent/context.py
# 等模块使用。它们委托给全局 InMemoryStore 实例的异步方法。
# session_id 直接映射（旧代码不区分 user_id，统一使用 "default"）。
#

def _run_async(coro: Any) -> Any:
    """在同步上下文中运行异步协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 在已有事件循环中，使用 run_coroutine_threadsafe 或直接创建新 loop
        import concurrent.futures
        future = concurrent.futures.Future()

        def _runner() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                new_loop.close()
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return future.result(timeout=30)
    else:
        return asyncio.run(coro)


def get_session(session_id: str, user_id: str = "default") -> dict[str, Any]:
    """
    获取或创建会话（向后兼容同步包装器）。

    行为：如果会话不存在，自动创建新会话。
    """
    store = get_store()
    if not isinstance(store, InMemoryStore):
        # 非 InMemoryStore 后端，使用异步方法
        state = _run_async(store.get_session(user_id, session_id))
        if state is None:
            new_state = {
                "session_id": session_id,
                "user_id": user_id,
                **DEFAULT_SESSION,
                "chat_history": [],  # 每个会话独立的 chat_history
            }
            _run_async(store.create_session(user_id, session_id, new_state))
            return new_state
        return state

    # InMemoryStore 快速路径：直接同步访问内部 dict
    key = (user_id, session_id)
    with store._lock:
        if key not in store._store:
            now = datetime.datetime.now().isoformat()
            store._store[key] = {
                "session_id": session_id,
                "user_id": user_id,
                **DEFAULT_SESSION,
                "created_at": now,
                "last_active_at": now,
            }
        return store._store[key]


def save_session(session_id: str, state: dict[str, Any], user_id: str = "default") -> None:
    """
    保存会话状态（向后兼容同步包装器）。

    合并 DEFAULT_SESSION 默认值，确保所有字段都存在。
    """
    store = get_store()
    merged = {
        **DEFAULT_SESSION,
        **state,
        "chat_history": list(state.get("chat_history", [])),  # 每个会话独立的 chat_history
        "session_id": session_id,
        "user_id": user_id,
    }
    if not isinstance(store, InMemoryStore):
        _run_async(store.save_session(user_id, session_id, merged))
        return

    now = datetime.datetime.now().isoformat()
    key = (user_id, session_id)
    with store._lock:
        existing = store._store.get(key)
        created_at = existing.get("created_at", now) if existing else merged.get("created_at", now)
        store._store[key] = {
            **merged,
            "created_at": created_at,
            "last_active_at": now,
        }


def delete_session(session_id: str, user_id: str = "default") -> bool:
    """
    删除会话（向后兼容同步包装器）。

    Returns:
        True 表示成功删除，False 表示会话不存在
    """
    store = get_store()
    if not isinstance(store, InMemoryStore):
        return _run_async(store.delete_session(user_id, session_id))

    key = (user_id, session_id)
    with store._lock:
        if key in store._store:
            del store._store[key]
            return True
        return False


def list_sessions(user_id: str = "default") -> list[str]:
    """
    列出所有会话 ID（向后兼容同步包装器）。

    Returns:
        会话 ID 列表
    """
    store = get_store()
    if not isinstance(store, InMemoryStore):
        summaries = _run_async(store.list_sessions(user_id))
        return [s["session_id"] for s in summaries]

    with store._lock:
        return [sid for (uid, sid) in store._store if uid == user_id]


def session_count(user_id: str = "default") -> int:
    """
    获取会话数量（向后兼容同步包装器）。
    """
    store = get_store()
    if not isinstance(store, InMemoryStore):
        summaries = _run_async(store.list_sessions(user_id))
        return len(summaries)

    with store._lock:
        return sum(1 for (uid, _) in store._store if uid == user_id)


# ============================================================================
# SESSION_STORE 代理 — 向后兼容
# ============================================================================

class _SessionStoreProxy:
    """
    代理对象，始终指向当前 InMemoryStore 的内部 dict。

    测试代码中直接使用 SESSION_STORE.clear() 清空存储，
    这个代理确保无论何时访问都指向最新的内部 dict。
    """

    def _get_dict(self) -> dict[str, dict[str, Any]]:
        store = get_store()
        if isinstance(store, InMemoryStore):
            return store._store
        # 后备：返回空 dict 避免崩溃
        return {}

    def __getitem__(self, key: Any) -> Any:
        return self._get_dict()[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._get_dict()[key] = value

    def __delitem__(self, key: Any) -> None:
        del self._get_dict()[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._get_dict()

    def __iter__(self) -> Any:
        return iter(self._get_dict())

    def __len__(self) -> int:
        return len(self._get_dict())

    def keys(self) -> Any:
        return self._get_dict().keys()

    def values(self) -> Any:
        return self._get_dict().values()

    def items(self) -> Any:
        return self._get_dict().items()

    def get(self, key: Any, default: Any = None) -> Any:
        return self._get_dict().get(key, default)

    def pop(self, key: Any, *args: Any) -> Any:
        return self._get_dict().pop(key, *args)

    def clear(self) -> None:
        self._get_dict().clear()

    def __repr__(self) -> str:
        return repr(self._get_dict())


SESSION_STORE: _SessionStoreProxy = _SessionStoreProxy()