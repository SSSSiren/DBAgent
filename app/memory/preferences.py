"""
查询偏好存储 — 操作层记忆的持久化管理

设计：
- QueryPreferenceStore 管理 query_preferences 表的完整生命周期
- 工厂函数 get_preference_store() 返回进程级单例（持久连接）
- 与 SqliteStore 共享同一 SQLite 数据库文件，使用独立连接
- 所有方法通过 user_id 确保用户隔离
"""

from __future__ import annotations

import datetime
import re
import threading
from typing import Any, Optional, Protocol, runtime_checkable

from app.config import get_settings

# 每用户最大偏好记录数
DEFAULT_MAX_PER_USER = 50


@runtime_checkable
class PreferenceBackend(Protocol):
    """偏好存储抽象协议。

    定义偏好存储的最小契约接口，所有偏好存储实现必须满足此协议。
    支持通过 isinstance(store, PreferenceBackend) 进行运行时检查。
    """

    async def record_query(
        self,
        user_id: str,
        table_name: str,
        database_name: str,
        schema_id: int,
    ) -> None:
        """记录一次查询偏好（UPSERT 语义，含 LRU 淘汰）。"""
        ...

    async def retrieve_preferences(
        self,
        user_id: str,
        keywords: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """根据关键词检索匹配的偏好表。"""
        ...

    async def retrieve_top_preferences(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """返回用户最常用的偏好表（无关键词时的回退）。"""
        ...

    async def initialize(self) -> None:
        """初始化存储（创建表等）。"""
        ...

    async def close(self) -> None:
        """关闭存储连接。"""
        ...


# ============================================================================
# InMemoryPreferenceStore — 内存偏好存储实现
# ============================================================================

class InMemoryPreferenceStore:
    """
    进程内存偏好存储，实现 PreferenceBackend 协议。

    使用 (user_id, table_name, database_name) 复合键实现用户隔离。
    偏好数据在进程重启后丢失（生产环境建议使用 SqlitePreferenceStore）。
    threading.Lock 为防御性并发保护。

    与 QueryPreferenceStore（SQLite）保持相同的返回数据结构和排序语义。
    """

    def __init__(self, max_per_user: int | None = None) -> None:
        self._store: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._lock = threading.Lock()
        if max_per_user is None:
            from app.config import get_settings
            max_per_user = getattr(get_settings(), "preference_max_per_user", DEFAULT_MAX_PER_USER)
        self._max_per_user = max_per_user

    # ── 辅助方法 ──────────────────────────────────────────────

    def _get_user_records(self, user_id: str) -> list[dict[str, Any]]:
        """获取指定用户的所有记录，返回列表（带复合键信息的拷贝）。"""
        records: list[dict[str, Any]] = []
        with self._lock:
            for (uid, table, db), rec in self._store.items():
                if uid == user_id:
                    records.append({
                        "table_name": table,
                        "database_name": db,
                        "schema_id": rec["schema_id"],
                        "query_count": rec["query_count"],
                        "last_query_at": rec["last_query_at"],
                    })
        return records

    # ── PreferenceBackend 协议方法 ───────────────────────────────

    async def record_query(
        self,
        user_id: str,
        table_name: str,
        database_name: str,
        schema_id: int,
    ) -> None:
        """
        记录一次查询偏好（UPSERT 语义，含 LRU 淘汰）。

        如果 (user_id, table_name, database_name) 已存在，则 query_count+1
        并更新 last_query_at 和 schema_id；否则创建新记录。
        每用户上限控制：写入前检查记录数，若已达上限且新记录不命中已有行，
        则淘汰 query_count 最小的记录。
        """
        if not user_id or not table_name or not database_name:
            return

        now = datetime.datetime.now().isoformat()
        key = (user_id, table_name, database_name)

        with self._lock:
            if key in self._store:
                # 已存在：递增 query_count，更新 schema_id 和 last_query_at
                self._store[key]["query_count"] += 1
                self._store[key]["last_query_at"] = now
                self._store[key]["schema_id"] = schema_id
                return

            # 新记录：检查是否达到上限，需要则淘汰
            user_count = sum(1 for (uid, _, _) in self._store if uid == user_id)
            if user_count >= self._max_per_user:
                # 内联淘汰逻辑（避免嵌套锁死锁）
                user_records = [
                    (k, v) for k, v in self._store.items()
                    if k[0] == user_id
                ]
                if user_records:
                    user_records.sort(key=lambda item: (
                        item[1]["query_count"],
                        item[1]["last_query_at"],
                    ))
                    del self._store[user_records[0][0]]

            # 插入新记录
            self._store[key] = {
                "schema_id": schema_id,
                "query_count": 1,
                "last_query_at": now,
            }

    async def retrieve_preferences(
        self,
        user_id: str,
        keywords: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        根据关键词检索匹配的偏好表。

        从 keywords 中提取可能的关键词（按空格/标点分词），
        对 table_name 和 database_name 执行子串匹配（case-insensitive LIKE）。
        结果按 query_count 降序排列。

        Args:
            user_id: 用户标识
            keywords: 用户输入文本，从中提取关键词
            limit: 最大返回条数

        Returns:
            偏好记录列表，每项包含 table_name、database_name、schema_id、
            query_count、last_query_at。无匹配时返回空列表。
        """
        tokens = [t for t in re.split(r'[\s,，。！？、]+', keywords) if t]
        if not tokens:
            return await self.retrieve_top_preferences(user_id, limit)

        records = self._get_user_records(user_id)

        # 匹配：任一 token 在 table_name 或 database_name 中（case-insensitive）
        matched: list[dict[str, Any]] = []
        for rec in records:
            tbl_lower = rec["table_name"].lower()
            db_lower = rec["database_name"].lower()
            for token in tokens:
                token_lower = token.lower()
                if token_lower in tbl_lower or token_lower in db_lower:
                    matched.append(rec)
                    break  # 避免重复添加

        # 按 query_count 降序排列
        matched.sort(key=lambda r: r["query_count"], reverse=True)
        return matched[:limit]

    async def retrieve_top_preferences(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        返回用户最常用的偏好表（无关键词匹配时的回退策略）。

        Args:
            user_id: 用户标识
            limit: 最大返回条数

        Returns:
            按 query_count 降序排列的偏好记录列表。无记录时返回空列表。
        """
        records = self._get_user_records(user_id)
        records.sort(key=lambda r: r["query_count"], reverse=True)
        return records[:limit]

    async def initialize(self) -> None:
        """初始化存储（内存存储无需操作）。"""
        pass

    async def close(self) -> None:
        """关闭存储连接（内存存储无需操作）。"""
        pass


class QueryPreferenceStore:
    """查询偏好存储，管理 query_preferences 表的 CRUD 和检索。"""

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: SQLite 数据库文件路径（与 SqliteStore 共享同一文件）
        """
        self._db_path = db_path
        self._conn: Any = None

    async def initialize(self) -> None:
        """初始化存储：连接数据库、启用 WAL 模式、创建 query_preferences 表和索引。"""
        import aiosqlite

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        # 启用 WAL 模式以支持并发读写
        await self._conn.execute("PRAGMA journal_mode=WAL;")

        # 创建 query_preferences 表
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS query_preferences (
                user_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                database_name TEXT NOT NULL,
                schema_id INTEGER NOT NULL,
                query_count INTEGER NOT NULL DEFAULT 1,
                last_query_at TEXT NOT NULL DEFAULT (datetime('now')),
                sql_patterns TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (user_id, table_name, database_name)
            );
        """)

        # 创建索引
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pref_user_freq "
            "ON query_preferences(user_id, query_count DESC);"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pref_user_table "
            "ON query_preferences(user_id, table_name);"
        )

        await self._conn.commit()

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _count_user_records(self, user_id: str) -> int:
        """获取用户当前偏好记录数"""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) as cnt FROM query_preferences WHERE user_id = ?;",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def _evict_lru(self, user_id: str) -> None:
        """淘汰该用户 query_count 最小的记录（LRU 策略）"""
        await self._conn.execute(
            """
            DELETE FROM query_preferences
            WHERE rowid = (
                SELECT rowid FROM query_preferences
                WHERE user_id = ?
                ORDER BY query_count ASC, last_query_at ASC
                LIMIT 1
            );
            """,
            (user_id,),
        )

    async def record_query(
        self,
        user_id: str,
        table_name: str,
        database_name: str,
        schema_id: int,
    ) -> None:
        """
        记录一次成功的查询偏好。

        使用 UPSERT 语义：如果 (user_id, table_name, database_name) 已存在，
        则 query_count+1 并更新 last_query_at；否则创建新记录。
        多表 JOIN 场景由调用方逐表调用此方法。

        每用户上限控制：写入前检查记录数，若已达上限且新记录不命中已有行，
        则淘汰 query_count 最小的记录（LRU 策略）。

        Preconditions:
            - user_id 非空字符串
            - table_name 非空字符串
            - database_name 非空字符串
            - schema_id 为正整数
        """
        if not user_id or not table_name or not database_name:
            return

        max_per_user = getattr(get_settings(), "preference_max_per_user", DEFAULT_MAX_PER_USER)

        # 检查是否已有该记录
        cursor = await self._conn.execute(
            "SELECT query_count FROM query_preferences WHERE user_id = ? AND table_name = ? AND database_name = ?;",
            (user_id, table_name, database_name),
        )
        existing = await cursor.fetchone()

        if existing is None:
            # 新记录：检查是否达到上限
            count = await self._count_user_records(user_id)
            if count >= max_per_user:
                await self._evict_lru(user_id)

        now = datetime.datetime.now().isoformat()
        await self._conn.execute(
            """
            INSERT INTO query_preferences
                (user_id, table_name, database_name, schema_id, query_count, last_query_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id, table_name, database_name) DO UPDATE SET
                query_count = query_count + 1,
                last_query_at = excluded.last_query_at,
                schema_id = excluded.schema_id;
            """,
            (user_id, table_name, database_name, schema_id, now),
        )
        await self._conn.commit()

    async def retrieve_preferences(
        self,
        user_id: str,
        keywords: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        根据关键词检索匹配的偏好表。

        从 keywords 中提取可能的关键词（按空格/标点分词），
        对 table_name 和 database_name 执行 LIKE 匹配。
        结果按 query_count 降序排列。

        Args:
            user_id: 用户标识
            keywords: 用户输入文本，从中提取关键词
            limit: 最大返回条数

        Returns:
            偏好记录列表，每项包含 table_name、database_name、schema_id、
            query_count、last_query_at。无匹配时返回空列表。
        """
        tokens = [t for t in re.split(r'[\s,，。！？、]+', keywords) if t]
        if not tokens:
            return await self.retrieve_top_preferences(user_id, limit)

        clauses = " OR ".join(
            ["table_name LIKE ? OR database_name LIKE ?"] * len(tokens)
        )
        params: list[Any] = []
        for token in tokens:
            params.extend([f"%{token}%", f"%{token}%"])

        cursor = await self._conn.execute(
            f"""
            SELECT table_name, database_name, schema_id, query_count, last_query_at
            FROM query_preferences
            WHERE user_id = ? AND ({clauses})
            ORDER BY query_count DESC
            LIMIT ?;
            """,
            [user_id] + params + [limit],
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def retrieve_top_preferences(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        返回用户最常用的偏好表（无关键词匹配时的回退策略）。

        Args:
            user_id: 用户标识
            limit: 最大返回条数

        Returns:
            按 query_count 降序排列的偏好记录列表。无记录时返回空列表。
        """
        cursor = await self._conn.execute(
            """
            SELECT table_name, database_name, schema_id, query_count, last_query_at
            FROM query_preferences
            WHERE user_id = ?
            ORDER BY query_count DESC
            LIMIT ?;
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ============================================================================
# 工厂函数
# ============================================================================

_preference_store: Optional[QueryPreferenceStore] = None


def get_preference_store() -> QueryPreferenceStore:
    """
    获取偏好存储实例（进程级单例，持久连接）。

    与 get_store() 模式一致，在 lifespan 中初始化、关闭时释放。
    首次调用时自动从 Settings 读取数据库路径创建实例。

    Returns:
        QueryPreferenceStore 实例（单例）
    """
    global _preference_store
    if _preference_store is not None:
        return _preference_store

    settings = get_settings()
    _preference_store = QueryPreferenceStore(settings.storage_file_path)
    return _preference_store


def reset_preference_store() -> None:
    """重置全局偏好存储实例（仅用于测试）。"""
    global _preference_store
    _preference_store = None