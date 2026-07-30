"""
会话存储 — 支持多后端的会话持久化管理

设计：
- StorageBackend 协议定义标准会话 CRUD 接口，所有后端实现该协议
- InMemoryStore 将进程内存 dict 封装为协议实现（开发/测试用）
- 工厂函数 get_store() 根据 Settings.storage_backend 返回对应后端实例
- 所有方法接受 user_id 作为第一个参数，实现用户级命名空间隔离
"""

from __future__ import annotations

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

    async def count_sessions(self) -> int:
        """
        返回跨所有用户的会话总数。

        Returns:
            会话总数
        """
        ...

    async def count_distinct_users(self) -> int:
        """
        返回至少拥有一个会话的不重复用户数。

        Returns:
            不重复用户数
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

    async def count_sessions(self) -> int:
        """
        返回跨所有用户的会话总数。

        遍历内存字典计算条目数。
        """
        with self._lock:
            return len(self._store)

    async def count_distinct_users(self) -> int:
        """
        返回至少拥有一个会话的不重复用户数。

        遍历内存字典提取不重复的 user_id。
        """
        with self._lock:
            return len({uid for (uid, _) in self._store})

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

    async def count_sessions(self) -> int:
        """
        返回跨所有用户的会话总数。

        使用 SQL 聚合查询 COUNT(*) 计算。
        """
        cursor = await self._conn.execute("SELECT COUNT(*) FROM sessions;")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def count_distinct_users(self) -> int:
        """
        返回至少拥有一个会话的不重复用户数。

        使用 SQL 聚合查询 COUNT(DISTINCT user_id) 计算。
        """
        cursor = await self._conn.execute("SELECT COUNT(DISTINCT user_id) FROM sessions;")
        row = await cursor.fetchone()
        return row[0] if row else 0


# ============================================================================
# 工厂函数
# ============================================================================

_store: Optional[StorageBackend] = None


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