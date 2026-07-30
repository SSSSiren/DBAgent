"""
Admin Store — HDC namespace 映射存储抽象

设计：
- AdminStoreBackend 协议定义标准 HDC 映射 CRUD 接口，所有后端实现该协议
- 复合主键: (user_id, schema_id, database_name)
- upsert_mapping 为 INSERT OR REPLACE 语义
- get_mappings 支持可选过滤（空字符串/0 表示不筛选）
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


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
