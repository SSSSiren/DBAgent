"""
Admin Store — HDC namespace 映射存储抽象

设计：
- AdminStoreBackend 协议定义标准 HDC 映射 CRUD 接口，所有后端实现该协议
- 复合主键: (user_id, schema_id, database_name)
- upsert_mapping 为 INSERT OR REPLACE 语义
- get_mappings 支持可选过滤（空字符串/0 表示不筛选）
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, Protocol, runtime_checkable

from app.config import get_settings


# ============================================================================
# AdminStoreBackend 协议
# ============================================================================

@runtime_checkable
class AdminStoreBackend(Protocol):
    """HDC namespace 映射存储抽象协议 — 所有管理存储后端必须实现此接口"""

    async def upsert_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
        hdc_namespace: str,
    ) -> dict:
        """
        创建或更新 HDC namespace 映射（INSERT OR REPLACE 语义）。

        Args:
            user_id: 用户标识
            schema_id: schema 标识
            database_name: 数据库名称
            hdc_namespace: HDC namespace 名称

        Returns:
            包含完整映射信息的字典（含 updated_at）
        """
        ...

    async def get_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
    ) -> Optional[dict]:
        """
        按复合主键 (user_id, schema_id, database_name) 查询映射。

        Args:
            user_id: 用户标识
            schema_id: schema 标识
            database_name: 数据库名称

        Returns:
            映射字典，不存在时返回 None
        """
        ...

    async def get_mappings(
        self,
        user_id: str = "",
        schema_id: int = 0,
        database_name: str = "",
    ) -> list[dict]:
        """
        查询映射列表，支持可选过滤。

        空字符串或 0 表示不按该字段过滤。

        Args:
            user_id: 用户标识过滤（空字符串表示不过滤）
            schema_id: schema 标识过滤（0 表示不过滤）
            database_name: 数据库名称过滤（空字符串表示不过滤）

        Returns:
            映射字典列表
        """
        ...

    async def delete_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
    ) -> bool:
        """
        按复合主键删除映射。

        Args:
            user_id: 用户标识
            schema_id: schema 标识
            database_name: 数据库名称

        Returns:
            True 表示成功删除，False 表示映射不存在
        """
        ...

    async def initialize(self) -> None:
        """初始化存储（创建表等），启动时调用一次"""
        ...

    async def close(self) -> None:
        """关闭存储连接，关闭时调用一次"""
        ...


# ============================================================================
# SqliteAdminStore — SQLite 持久化存储实现
# ============================================================================

class SqliteAdminStore:
    """
    SQLite 持久化 HDC namespace 映射存储，实现 AdminStoreBackend 协议。

    将映射数据持久化到 SQLite 数据库文件（与现有会话存储共享同一文件）。
    使用 WAL 模式支持并发读写，复合主键 (user_id, schema_id, database_name)。

    数据库文件路径通过 Settings.storage_file_path 配置，默认为 data/sessions.db。
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is not None:
            self._db_path = db_path
        else:
            self._db_path = get_settings().storage_file_path
        self._conn: Any = None

    # ── AdminStoreBackend 协议方法 ─────────────────────────────

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

        # 创建 user_hdc_mappings 表（复合主键）
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_hdc_mappings (
                user_id TEXT NOT NULL,
                schema_id INTEGER NOT NULL,
                database_name TEXT NOT NULL,
                hdc_namespace TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, schema_id, database_name)
            );
        """)

        await self._conn.commit()

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def upsert_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
        hdc_namespace: str,
    ) -> dict:
        """
        创建或更新 HDC namespace 映射（INSERT OR REPLACE 语义）。

        Returns:
            包含完整映射信息的字典（含 updated_at）
        """
        now = datetime.datetime.now().isoformat()

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO user_hdc_mappings (user_id, schema_id, database_name, hdc_namespace, updated_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (user_id, schema_id, database_name, hdc_namespace, now),
        )
        await self._conn.commit()

        return {
            "user_id": user_id,
            "schema_id": schema_id,
            "database_name": database_name,
            "hdc_namespace": hdc_namespace,
            "updated_at": now,
        }

    async def get_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
    ) -> Optional[dict]:
        """
        按复合主键 (user_id, schema_id, database_name) 查询映射。

        Returns:
            映射字典，不存在时返回 None
        """
        cursor = await self._conn.execute(
            """
            SELECT user_id, schema_id, database_name, hdc_namespace, updated_at
            FROM user_hdc_mappings
            WHERE user_id = ? AND schema_id = ? AND database_name = ?;
            """,
            (user_id, schema_id, database_name),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def get_mappings(
        self,
        user_id: str = "",
        schema_id: int = 0,
        database_name: str = "",
    ) -> list[dict]:
        """
        查询映射列表，支持可选过滤。

        空字符串或 0 表示不按该字段过滤。

        Returns:
            映射字典列表
        """
        conditions: list[str] = []
        params: list[Any] = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if schema_id:
            conditions.append("schema_id = ?")
            params.append(schema_id)
        if database_name:
            conditions.append("database_name = ?")
            params.append(database_name)

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        else:
            where_clause = ""

        cursor = await self._conn.execute(
            f"""
            SELECT user_id, schema_id, database_name, hdc_namespace, updated_at
            FROM user_hdc_mappings
            {where_clause}
            ORDER BY updated_at DESC;
            """,
            tuple(params),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
    ) -> bool:
        """
        按复合主键删除映射。

        Returns:
            True 表示成功删除，False 表示映射不存在
        """
        cursor = await self._conn.execute(
            """
            DELETE FROM user_hdc_mappings
            WHERE user_id = ? AND schema_id = ? AND database_name = ?;
            """,
            (user_id, schema_id, database_name),
        )
        await self._conn.commit()
        return cursor.rowcount > 0


# ============================================================================
# InMemoryAdminStore — 内存存储实现（仅测试用）
# ============================================================================

class InMemoryAdminStore:
    """
    进程内存 HDC namespace 映射存储，实现 AdminStoreBackend 协议。

    使用 (user_id, schema_id, database_name) 元组做复合键的 Python dict。
    映射在进程重启后丢失 — 仅供单元测试使用，不用于生产环境。
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, int, str], dict] = {}

    # ── AdminStoreBackend 协议方法 ─────────────────────────────

    async def upsert_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
        hdc_namespace: str,
    ) -> dict:
        """
        创建或更新 HDC namespace 映射（INSERT OR REPLACE 语义）。

        Returns:
            包含完整映射信息的字典（含 updated_at）
        """
        now = datetime.datetime.now().isoformat()
        key = (user_id, schema_id, database_name)
        mapping = {
            "user_id": user_id,
            "schema_id": schema_id,
            "database_name": database_name,
            "hdc_namespace": hdc_namespace,
            "updated_at": now,
        }
        self._store[key] = mapping
        return mapping

    async def get_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
    ) -> Optional[dict]:
        """
        按复合主键 (user_id, schema_id, database_name) 查询映射。

        Returns:
            映射字典，不存在时返回 None
        """
        key = (user_id, schema_id, database_name)
        return self._store.get(key)

    async def get_mappings(
        self,
        user_id: str = "",
        schema_id: int = 0,
        database_name: str = "",
    ) -> list[dict]:
        """
        查询映射列表，支持可选过滤。

        空字符串或 0 表示不按该字段过滤。

        Returns:
            映射字典列表
        """
        results = []
        for (uid, sid, db_name), mapping in self._store.items():
            if user_id and uid != user_id:
                continue
            if schema_id and sid != schema_id:
                continue
            if database_name and db_name != database_name:
                continue
            results.append(mapping)

        # 按 updated_at 降序
        results.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return results

    async def delete_mapping(
        self,
        user_id: str,
        schema_id: int,
        database_name: str,
    ) -> bool:
        """
        按复合主键删除映射。

        Returns:
            True 表示成功删除，False 表示映射不存在
        """
        key = (user_id, schema_id, database_name)
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def initialize(self) -> None:
        """初始化存储（内存存储无需操作）"""
        pass

    async def close(self) -> None:
        """关闭存储连接（内存存储无需操作）"""
        pass
