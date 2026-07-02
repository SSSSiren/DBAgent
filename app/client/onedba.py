"""
OneDBA HTTP 客户端 — 封装 OneDBA 平台的数据库操作 API

参考 DBAgent 的 app/client/onedba_client.py，核心接口：
- list_databases: 列出用户有权限访问的数据库
- execute_sql: 在指定数据库上执行 SQL

使用 httpx.AsyncClient 进行异步 HTTP 调用，认证方式为 accessToken header。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class OneDBAError(Exception):
    """OneDBA API 错误"""

    def __init__(self, message: str, code: int | str = -1):
        super().__init__(message)
        self.code = code


class OneDBAClient:
    """OneDBA 平台 HTTP 客户端"""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url: str = settings.onedba_base_url.rstrip("/")
        self._access_token: str = settings.onedba_access_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 客户端（懒初始化）"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "accessToken": self._access_token,
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    def _check_response(self, data: dict[str, Any]) -> None:
        """检查 API 响应是否成功"""
        code = data.get("code")
        if code is not None and code != 0 and code != "0":
            message = data.get("message") or data.get("msg") or "未知错误"
            raise OneDBAError(f"OneDBA API 错误 (code={code}): {message}", code=code)

    async def list_databases(
        self,
        keyword: str = "",
        env_type: str = "test",
        instance_type: str = "acs_rds",
        main_body: str = "shizhuang",
        page: int = 1,
        size: int = 30,
    ) -> list[dict[str, Any]]:
        """
        列出用户有权限访问的数据库。

        Args:
            keyword: 搜索关键词，用于过滤数据库名称
            env_type: 环境类型，默认 "test"
            instance_type: 实例类型，默认 "acs_rds"
            main_body: 主体，默认 "shizhuang"
            page: 页码
            size: 每页大小

        Returns:
            数据库列表，每个元素包含 schemaId, schemaName, instanceName 等
        """
        client = await self._get_client()
        params: dict[str, Any] = {
            "queryType": "select",
            "page": page,
            "size": size,
            "envType": env_type,
            "instanceType": instance_type,
            "mainBody": main_body,
        }
        if keyword:
            params["keyword"] = keyword

        response = await client.get(
            "/api/external/v1/agent/instance/schema/user/list",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        self._check_response(data)
        payload = data.get("data") or {}
        return payload.get("items") or []

    async def execute_sql(
        self, schema_id: int, sql: str, query_timeout: int = 30
    ) -> dict[str, Any]:
        """
        在指定数据库上执行 SQL 查询。

        Args:
            schema_id: 数据库 schema ID
            sql: SQL 语句
            query_timeout: 查询超时（秒）

        Returns:
            查询结果，包含 columnNames 和 columnDatas
        """
        client = await self._get_client()
        payload = {
            "schemaId": schema_id,
            "sqlText": sql,
            "queryTimeout": query_timeout,
        }

        response = await client.post(
            "/api/external/v1/agent/query",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        self._check_response(data)
        return data.get("data") or {}

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# 全局单例
_onedba_client: OneDBAClient | None = None


def get_onedba_client() -> OneDBAClient:
    """获取 OneDBA 客户端单例"""
    global _onedba_client
    if _onedba_client is None:
        _onedba_client = OneDBAClient()
    return _onedba_client