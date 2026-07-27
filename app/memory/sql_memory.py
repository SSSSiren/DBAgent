"""
SQL 历史记忆存储 — Agent 成功执行的 SQL 记录的持久化与语义检索

设计：
- SqlMemoryBackend Protocol 定义 SQL 记忆存储的最小契约接口
- InMemorySqlMemoryStore 提供进程内存实现（开发/测试用）
- SqliteSqlMemoryStore 提供 aiosqlite 持久化实现（生产用）
- 工厂函数 get_sql_memory_store() 根据 storage_backend 配置返回对应后端
- 与 SqliteStore / SqlitePreferenceStore 共享同一 SQLite 数据库文件，使用独立表
- 支持 per-user 和 per-database 混合作用域
"""

from __future__ import annotations

import datetime
import json
import math
import logging
import threading
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from app.config import get_settings

logger = logging.getLogger(__name__)

# 每用户最大记忆记录数（内存实现用）
DEFAULT_MAX_PER_USER = 100
# 单次异步补嵌入最大记录数
DEFAULT_BACKFILL_BATCH = 10


@runtime_checkable
class SqlMemoryBackend(Protocol):
    """SQL 记忆存储抽象协议。

    定义 SQL 历史记忆的最小契约接口，所有实现必须满足此协议。
    支持通过 isinstance(store, SqlMemoryBackend) 进行运行时检查。
    """

    async def record(
        self,
        user_id: str,
        question: str,
        sql: str,
        table_names: list[str],
        database_name: str,
        schema_id: int,
        execution_result: dict,
        embedding: list[float] | None,
    ) -> None:
        """记录一次 SQL 执行。

        Args:
            user_id: 用户标识
            question: 原始自然语言问题
            sql: 执行的 SQL 语句
            table_names: 涉及的数据库表名列表
            database_name: 数据库名称
            schema_id: schema 标识
            execution_result: 执行结果摘要，包含 row_count, column_names, data_preview
            embedding: 问题文本的嵌入向量，失败时为 None
        """
        ...

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        database_name: str = "",
        scope: str = "user",
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """语义检索相似的历史 SQL。

        Args:
            user_id: 用户标识
            query_embedding: 查询向量
            database_name: 数据库名称（per-database / mixed 模式使用）
            scope: 作用域模式 - "user" / "database" / "mixed"
            limit: 最大返回条数
            min_similarity: 最低相似度阈值

        Returns:
            按相似度降序排列的记录列表。
        """
        ...

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """列出用户的所有 SQL 记忆记录。"""
        ...

    async def delete_expired(self, ttl_days: int) -> int:
        """删除超过 TTL 的过期记录，返回删除条数。"""
        ...

    async def mine_patterns(
        self,
        database_name: str,
        min_records: int = 20,
    ) -> dict[str, Any]:
        """从历史 SQL 中挖掘查询模式。

        Returns:
            {
                "total_records": int,
                "top_tables": [{"table": str, "count": int}, ...],
                "top_condition_patterns": [{"pattern": str, "count": int}, ...],
                "common_joins": [{"tables": [str, str], "count": int}, ...],
            }
        """
        ...

    async def initialize(self) -> None:
        """初始化存储（创建表、索引等）。"""
        ...

    async def close(self) -> None:
        """关闭存储连接。"""
        ...


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度（纯 Python 实现）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _generate_uuid7() -> str:
    """Generate a UUID7 string for record IDs."""
    return str(uuid.uuid4())


# ============================================================================
# InMemorySqlMemoryStore — 内存 SQL 记忆存储实现
# ============================================================================


class InMemorySqlMemoryStore(SqlMemoryBackend):
    """进程内存 SQL 记忆存储，实现 SqlMemoryBackend 协议。

    使用 dict 存储所有记录，复合键 (user_id, sql_text) 用于 session 内去重。
    数据在进程重启后丢失（生产环境建议使用 SqliteSqlMemoryStore）。
    threading.Lock 为防御性并发保护。
    """

    def __init__(self, max_per_user: int | None = None) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        if max_per_user is None:
            max_per_user = DEFAULT_MAX_PER_USER
        self._max_per_user = max_per_user

    # ── 辅助方法 ──────────────────────────────────────────────

    def _get_records_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """获取指定用户的所有记录列表，按 created_at 降序。"""
        results: list[dict[str, Any]] = []
        with self._lock:
            for rid, rec in self._records.items():
                if rec["user_id"] == user_id:
                    results.append({**rec, "id": rid})
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return results

    def _get_records_for_database(self, database_name: str) -> list[dict[str, Any]]:
        """获取指定数据库的所有记录（跨用户）。"""
        results: list[dict[str, Any]] = []
        with self._lock:
            for rid, rec in self._records.items():
                if rec["database_name"] == database_name:
                    results.append({**rec, "id": rid})
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return results

    def _dedup_key(self, user_id: str, sql: str, database_name: str) -> str:
        """生成去重键：user_id + 归一化 SQL + database_name。"""
        normalized = " ".join(sql.lower().split())
        return f"{user_id}:{database_name}:{normalized}"

    # ── SqlMemoryBackend 协议方法 ───────────────────────────────

    async def record(
        self,
        user_id: str,
        question: str,
        sql: str,
        table_names: list[str],
        database_name: str,
        schema_id: int,
        execution_result: dict,
        embedding: list[float] | None,
    ) -> None:
        """记录一次 SQL 执行（UPSERT 语义，去重 + LRU 淘汰）。"""
        if not user_id or not sql:
            return

        now = datetime.datetime.now().isoformat()
        settings = get_settings()
        sql_max_length = getattr(settings, "sql_memory_sql_max_length", 2000)

        record_id = _generate_uuid7()
        sql_truncated = sql[:500] if len(sql) > 500 else sql

        detup_key = self._dedup_key(user_id, sql, database_name)

        with self._lock:
            # 去重检查
            for existing_id, existing in self._records.items():
                existing_key = self._dedup_key(
                    existing["user_id"], existing["sql_text"], existing["database_name"]
                )
                if existing_key == detup_key:
                    return  # 跳过重复记录

            # LRU 淘汰检查
            user_count = sum(
                1 for rid, r in self._records.items() if r["user_id"] == user_id
            )
            if user_count >= self._max_per_user:
                user_records = [
                    (rid, r)
                    for rid, r in self._records.items()
                    if r["user_id"] == user_id
                ]
                if user_records:
                    user_records.sort(key=lambda item: item[1].get("created_at", ""))
                    oldest_id = user_records[0][0]
                    del self._records[oldest_id]

            self._records[record_id] = {
                "user_id": user_id,
                "question": question,
                "sql_text": sql[:sql_max_length] if len(sql) > sql_max_length else sql,
                "sql_truncated": sql_truncated,
                "table_names": json.dumps(table_names, ensure_ascii=False),
                "database_name": database_name,
                "schema_id": schema_id,
                "row_count": execution_result.get("row_count"),
                "column_names": json.dumps(
                    execution_result.get("column_names", []), ensure_ascii=False
                ),
                "data_preview": json.dumps(
                    execution_result.get("data_preview", []), ensure_ascii=False,
                    default=str,
                ),
                "execution_status": execution_result.get("execution_status", "success"),
                "embedding_json": json.dumps(embedding) if embedding else None,
                "scope": getattr(settings, "sql_memory_scope", "user"),
                "created_at": now,
            }

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        database_name: str = "",
        scope: str = "user",
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """语义检索相似的历史 SQL 记录。"""
        # 收集候选记录
        with self._lock:
            candidates: list[dict[str, Any]] = []
            for rid, rec in self._records.items():
                # 作用域过滤
                if scope == "user":
                    if rec["user_id"] != user_id:
                        continue
                elif scope == "database":
                    if rec["database_name"] != database_name:
                        continue
                elif scope == "mixed":
                    if rec["database_name"] == database_name:
                        pass  # database 级别的记录直接包含
                    elif rec["user_id"] == user_id:
                        pass  # 用户自己的记录也包含
                    else:
                        continue

                # 必须有 embedding 才能计算相似度
                if rec.get("embedding_json") is None:
                    continue

                try:
                    rec_embedding = json.loads(rec["embedding_json"])
                except (json.JSONDecodeError, TypeError):
                    continue

                sim = _cosine_similarity(query_embedding, rec_embedding)
                if sim < min_similarity:
                    continue

                candidates.append({
                    "id": rid,
                    "user_id": rec["user_id"],
                    "question": rec["question"],
                    "sql_text": rec["sql_text"],
                    "sql_truncated": rec.get("sql_truncated", ""),
                    "table_names": json.loads(rec["table_names"]),
                    "database_name": rec["database_name"],
                    "schema_id": rec["schema_id"],
                    "row_count": rec["row_count"],
                    "column_names": json.loads(rec.get("column_names", "[]")),
                    "data_preview": json.loads(rec.get("data_preview", "[]")),
                    "execution_status": rec.get("execution_status", "success"),
                    "scope": rec.get("scope", "user"),
                    "created_at": rec.get("created_at", ""),
                    "similarity": round(sim, 4),
                })

        # 按相似度降序排列
        candidates.sort(key=lambda r: r["similarity"], reverse=True)
        return candidates[:limit]

    async def list_by_user(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """列出用户的所有 SQL 记忆记录。"""
        records = self._get_records_for_user(user_id)
        return records[:limit]

    async def delete_expired(self, ttl_days: int) -> int:
        """删除超过 TTL 的过期记录。"""
        cutoff = (
            datetime.datetime.now() - datetime.timedelta(days=ttl_days)
        ).isoformat()
        deleted = 0
        with self._lock:
            expired_ids = [
                rid
                for rid, rec in self._records.items()
                if rec.get("created_at", "") < cutoff
            ]
            for rid in expired_ids:
                del self._records[rid]
                deleted += 1
        return deleted

    async def mine_patterns(
        self, database_name: str, min_records: int = 20
    ) -> dict[str, Any]:
        """从历史 SQL 中挖掘查询模式（内存实现为简化版）。"""
        import re

        records = self._get_records_for_database(database_name)
        total = len(records)

        if total < min_records:
            return {
                "total_records": total,
                "message": f"记录不足：当前 {total} 条，需要 {min_records} 条以上才能挖掘模式",
                "top_tables": [],
                "top_condition_patterns": [],
                "common_joins": [],
            }

        # 统计表名
        table_counts: dict[str, int] = {}
        condition_patterns: dict[str, int] = {}
        join_pairs: dict[str, int] = {}

        for rec in records:
            table_names = rec.get("table_names", "[]")
            if isinstance(table_names, str):
                try:
                    table_names = json.loads(table_names)
                except (json.JSONDecodeError, TypeError):
                    table_names = []
            for t in table_names:
                table_counts[t] = table_counts.get(t, 0) + 1

            # 提取 WHERE 条件模式
            sql_text = rec.get("sql_text", "")
            where_match = re.search(
                r"\bWHERE\b\s+(.+?)(?:\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
                sql_text, re.IGNORECASE | re.DOTALL,
            )
            if where_match:
                condition = where_match.group(1).strip()
                normalized = re.sub(r"'[^']*'", "?", condition)
                normalized = re.sub(r"\b\d+\b", "?", normalized)
                normalized = " ".join(normalized.split())
                normalized = normalized.rstrip(";")
                condition_patterns[normalized] = (
                    condition_patterns.get(normalized, 0) + 1
                )

            # 提取 JOIN 关系
            join_tables = re.findall(
                r"\bJOIN\b\s+`?(\w+)`?", sql_text, re.IGNORECASE
            )
            from_tables = re.findall(
                r"\bFROM\b\s+`?(\w+)`?", sql_text, re.IGNORECASE
            )
            for ft in from_tables:
                for jt in join_tables:
                    pair = tuple(sorted([ft, jt]))
                    key = f"{pair[0]},{pair[1]}"
                    join_pairs[key] = join_pairs.get(key, 0) + 1

        top_tables = sorted(
            [{"table": k, "count": v} for k, v in table_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        top_conditions = sorted(
            [{"pattern": k, "count": v} for k, v in condition_patterns.items()],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        common_joins = sorted(
            [
                {"tables": k.split(","), "count": v}
                for k, v in join_pairs.items()
            ],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        return {
            "total_records": total,
            "top_tables": top_tables,
            "top_condition_patterns": top_conditions,
            "common_joins": common_joins,
        }

    async def initialize(self) -> None:
        """初始化存储（内存存储无需操作）。"""
        pass

    async def close(self) -> None:
        """关闭存储连接（内存存储无需操作）。"""
        pass


# ============================================================================
# SqliteSqlMemoryStore — SQLite 持久化 SQL 记忆存储实现
# ============================================================================


class SqliteSqlMemoryStore(SqlMemoryBackend):
    """SQL 记忆存储（SQLite 持久化实现），管理 sql_memories 表的完整生命周期。

    与 SqliteStore / SqlitePreferenceStore 共享同一 SQLite 数据库文件，
    使用独立连接。支持 per-user 和 per-database 混合作用域。
    """

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: SQLite 数据库文件路径（与 sessions/preferences 共享同一文件）
        """
        self._db_path = db_path
        self._conn: Any = None

    async def initialize(self) -> None:
        """初始化存储：连接数据库、启用 WAL 模式、创建 sql_memories 表和索引。"""
        import aiosqlite

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.execute("PRAGMA journal_mode=WAL;")

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sql_memories (
                id TEXT PRIMARY KEY NOT NULL,
                user_id TEXT NOT NULL,
                question TEXT NOT NULL,
                sql_text TEXT NOT NULL,
                sql_truncated TEXT,
                table_names TEXT NOT NULL DEFAULT '[]',
                database_name TEXT NOT NULL,
                schema_id INTEGER NOT NULL,
                row_count INTEGER,
                column_names TEXT DEFAULT '[]',
                data_preview TEXT DEFAULT '[]',
                execution_status TEXT NOT NULL DEFAULT 'success',
                embedding_json TEXT,
                scope TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # 复合索引：user_id + database_name（scope 过滤）
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sql_mem_user_db "
            "ON sql_memories(user_id, database_name);"
        )
        # database_name 索引（跨用户查询）
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sql_mem_db "
            "ON sql_memories(database_name);"
        )
        # created_at 索引（TTL 过期清理）
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sql_mem_created "
            "ON sql_memories(created_at);"
        )
        # embedding 非空索引（仅扫描已嵌入记录）
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sql_mem_embedding "
            "ON sql_memories(embedding_json) WHERE embedding_json IS NOT NULL;"
        )

        await self._conn.commit()

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ── 辅助方法 ──────────────────────────────────────────────

    def _dedup_key(self, user_id: str, sql: str, database_name: str) -> str:
        """生成去重键：user_id + 归一化 SQL + database_name。"""
        normalized = " ".join(sql.lower().split())
        return f"{user_id}:{database_name}:{normalized}"

    async def _count_user_records(self, user_id: str) -> int:
        """获取用户当前记录数。"""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) as cnt FROM sql_memories WHERE user_id = ?;",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def _evict_lru(self, user_id: str, max_records: int) -> None:
        """淘汰用户最旧的记录（LRU）。"""
        current = await self._count_user_records(user_id)
        if current < max_records:
            return
        excess = current - max_records + 1
        await self._conn.execute(
            """
            DELETE FROM sql_memories
            WHERE rowid IN (
                SELECT rowid FROM sql_memories
                WHERE user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            );
            """,
            (user_id, excess),
        )

    # ── SqlMemoryBackend 协议方法 ───────────────────────────────

    async def record(
        self,
        user_id: str,
        question: str,
        sql: str,
        table_names: list[str],
        database_name: str,
        schema_id: int,
        execution_result: dict,
        embedding: list[float] | None,
    ) -> None:
        """记录一次 SQL 执行（UPSERT 语义，去重 + LRU 淘汰）。"""
        if not user_id or not sql:
            return

        settings = get_settings()
        sql_max_length = getattr(settings, "sql_memory_sql_max_length", 2000)

        now = datetime.datetime.now().isoformat()
        record_id = _generate_uuid7()
        sql_truncated = sql[:500] if len(sql) > 500 else sql
        stored_sql = sql[:sql_max_length] if len(sql) > sql_max_length else sql
        embedding_str = json.dumps(embedding) if embedding else None

        # 去重检查
        cursor = await self._conn.execute(
            "SELECT user_id FROM sql_memories "
            "WHERE user_id = ? AND database_name = ? AND sql_text = ?;",
            (user_id, database_name, sql),
        )
        existing = await cursor.fetchone()
        if existing is not None:
            return  # 跳过重复记录

        # LRU 淘汰
        default_max = DEFAULT_MAX_PER_USER
        await self._evict_lru(user_id, default_max)

        await self._conn.execute(
            """
            INSERT INTO sql_memories
                (id, user_id, question, sql_text, sql_truncated,
                 table_names, database_name, schema_id,
                 row_count, column_names, data_preview, execution_status,
                 embedding_json, scope, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record_id, user_id, question, stored_sql, sql_truncated,
                json.dumps(table_names, ensure_ascii=False),
                database_name, schema_id,
                execution_result.get("row_count"),
                json.dumps(execution_result.get("column_names", []), ensure_ascii=False),
                json.dumps(execution_result.get("data_preview", []), ensure_ascii=False, default=str),
                execution_result.get("execution_status", "success"),
                embedding_str,
                getattr(settings, "sql_memory_scope", "user"),
                now,
            ),
        )
        await self._conn.commit()

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        database_name: str = "",
        scope: str = "user",
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """语义检索相似的历史 SQL 记录。

        仅扫描 embedding_json IS NOT NULL 的记录。
        """
        # 构建作用域过滤子句
        if scope == "user":
            scope_clause = "user_id = ?"
            scope_params: list[Any] = [user_id]
        elif scope == "database":
            scope_clause = "database_name = ?"
            scope_params = [database_name]
        elif scope == "mixed":
            scope_clause = "(database_name = ? OR user_id = ?)"
            scope_params = [database_name, user_id]
        else:
            scope_clause = "user_id = ?"
            scope_params = [user_id]

        cursor = await self._conn.execute(
            f"""
            SELECT id, user_id, question, sql_text, sql_truncated,
                   table_names, database_name, schema_id,
                   row_count, column_names, data_preview,
                   execution_status, embedding_json, scope, created_at
            FROM sql_memories
            WHERE {scope_clause} AND embedding_json IS NOT NULL
            """,
            scope_params,
        )
        rows = await cursor.fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            rec = dict(row)
            try:
                rec_embedding = json.loads(rec["embedding_json"])
            except (json.JSONDecodeError, TypeError):
                continue

            sim = _cosine_similarity(query_embedding, rec_embedding)
            if sim < min_similarity:
                continue

            candidates.append({
                "id": rec["id"],
                "user_id": rec["user_id"],
                "question": rec["question"],
                "sql_text": rec["sql_text"],
                "sql_truncated": rec.get("sql_truncated", ""),
                "table_names": json.loads(rec["table_names"]),
                "database_name": rec["database_name"],
                "schema_id": rec["schema_id"],
                "row_count": rec["row_count"],
                "column_names": json.loads(rec.get("column_names", "[]")),
                "data_preview": json.loads(rec.get("data_preview", "[]")),
                "execution_status": rec.get("execution_status", "success"),
                "scope": rec.get("scope", "user"),
                "created_at": rec.get("created_at", ""),
                "similarity": round(sim, 4),
            })

        candidates.sort(key=lambda r: r["similarity"], reverse=True)
        return candidates[:limit]

    async def list_by_user(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """列出用户的所有 SQL 记忆记录（按时间降序）。"""
        cursor = await self._conn.execute(
            """
            SELECT id, user_id, question, sql_text, sql_truncated,
                   table_names, database_name, schema_id,
                   row_count, execution_status, scope, created_at
            FROM sql_memories
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            rec = dict(row)
            rec["table_names"] = json.loads(rec.get("table_names", "[]"))
            results.append(rec)
        return results

    async def delete_expired(self, ttl_days: int) -> int:
        """删除超过 TTL 的过期记录，返回删除条数。"""
        cursor = await self._conn.execute(
            """
            DELETE FROM sql_memories
            WHERE created_at < datetime('now', '-' || CAST(? AS TEXT) || ' days');
            """,
            (str(ttl_days),),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def mine_patterns(
        self, database_name: str, min_records: int = 20
    ) -> dict[str, Any]:
        """从历史 SQL 中挖掘查询模式。"""
        import re

        # 统计记录总数
        cursor = await self._conn.execute(
            "SELECT COUNT(*) as cnt FROM sql_memories WHERE database_name = ?;",
            (database_name,),
        )
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

        if total < min_records:
            return {
                "total_records": total,
                "message": f"记录不足：当前 {total} 条，需要 {min_records} 条以上才能挖掘模式",
                "top_tables": [],
                "top_condition_patterns": [],
                "common_joins": [],
            }

        # 获取所有记录
        cursor = await self._conn.execute(
            "SELECT table_names, sql_text FROM sql_memories "
            "WHERE database_name = ?;",
            (database_name,),
        )
        rows = await cursor.fetchall()

        table_counts: dict[str, int] = {}
        condition_patterns: dict[str, int] = {}
        join_pairs: dict[str, int] = {}

        for row in rows:
            try:
                names = json.loads(row["table_names"])
            except (json.JSONDecodeError, TypeError):
                names = []
            for t in names:
                table_counts[t] = table_counts.get(t, 0) + 1

            sql_text = row["sql_text"] or ""
            where_match = re.search(
                r"\bWHERE\b\s+(.+?)(?:\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
                sql_text, re.IGNORECASE | re.DOTALL,
            )
            if where_match:
                condition = where_match.group(1).strip()
                normalized = re.sub(r"'[^']*'", "?", condition)
                normalized = re.sub(r"\b\d+\b", "?", normalized)
                normalized = " ".join(normalized.split()).rstrip(";")
                condition_patterns[normalized] = (
                    condition_patterns.get(normalized, 0) + 1
                )

            join_tables = re.findall(
                r"\bJOIN\b\s+`?(\w+)`?", sql_text, re.IGNORECASE
            )
            from_tables = re.findall(
                r"\bFROM\b\s+`?(\w+)`?", sql_text, re.IGNORECASE
            )
            for ft in from_tables:
                for jt in join_tables:
                    pair = tuple(sorted([ft, jt]))
                    key = f"{pair[0]},{pair[1]}"
                    join_pairs[key] = join_pairs.get(key, 0) + 1

        top_tables = sorted(
            [{"table": k, "count": v} for k, v in table_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        top_conditions = sorted(
            [{"pattern": k, "count": v} for k, v in condition_patterns.items()],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        common_joins = sorted(
            [
                {"tables": k.split(","), "count": v}
                for k, v in join_pairs.items()
            ],
            key=lambda x: x["count"], reverse=True,
        )[:10]

        return {
            "total_records": total,
            "top_tables": top_tables,
            "top_condition_patterns": top_conditions,
            "common_joins": common_joins,
        }


# ============================================================================
# 工厂函数
# ============================================================================

_sql_memory_store: Optional[SqlMemoryBackend] = None


def get_sql_memory_store() -> SqlMemoryBackend:
    """获取 SQL 记忆存储实例（进程级单例）。

    根据 storage_backend 配置选择后端实现：
    - "memory" → InMemorySqlMemoryStore（进程内内存，重启丢失）
    - "sqlite"  → SqliteSqlMemoryStore（文件持久化）

    首次调用时自动从 Settings 读取配置创建实例。

    Returns:
        SqlMemoryBackend 实例（单例）
    """
    global _sql_memory_store
    if _sql_memory_store is not None:
        return _sql_memory_store

    settings = get_settings()
    backend = getattr(settings, "storage_backend", "memory")

    if backend == "memory":
        _sql_memory_store = InMemorySqlMemoryStore()
    else:
        _sql_memory_store = SqliteSqlMemoryStore(settings.storage_file_path)
    return _sql_memory_store


def reset_sql_memory_store() -> None:
    """重置全局 SQL 记忆存储实例（仅用于测试）。"""
    global _sql_memory_store
    _sql_memory_store = None


# ============================================================================
# Embedding 客户端
# ============================================================================

_embedding_cache: dict[str, list[float]] = {}


async def embed_text(text: str, cache: dict[str, list[float]] | None = None) -> list[float] | None:
    """将文本转换为嵌入向量（1536 维），失败时返回 None。

    复用现有的 AsyncOpenAI 客户端（与 Agent LLM 调用共享同一连接池）。
    支持 dict 级 memoization 缓存，避免同一会话内重复嵌入相同文本。

    Args:
        text: 待嵌入的文本
        cache: 可选的缓存字典，用于会话级 memoization

    Returns:
        1536 维浮点数列表，或 None（嵌入 API 不可用时）
    """
    if not text or not text.strip():
        return None

    cache = cache or _embedding_cache
    cache_key = text.strip()
    if cache_key in cache:
        return cache[cache_key]

    try:
        from app.agent.runner import _get_llm_client

        settings = get_settings()
        model = getattr(settings, "llm_embedding_model", "text-embedding-3-small")
        client = _get_llm_client()

        response = await client.embeddings.create(
            model=model,
            input=cache_key,
        )
        embedding = response.data[0].embedding
        cache[cache_key] = embedding
        return embedding

    except Exception as e:
        logger.warning(f"SQL Memory: 嵌入生成失败 ({type(e).__name__}): {e}")
        return None

