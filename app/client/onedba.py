"""
OneDBA HTTP 客户端 — 封装 OneDBA 平台的数据库操作 API

参考 DBAgent 的 app/client/onedba_client.py，核心接口：
- list_databases: 列出用户有权限访问的数据库
- execute_sql: 在指定数据库上执行 SQL

使用 httpx.AsyncClient 进行异步 HTTP 调用，认证方式为 accessToken header。
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import get_settings

# 需要自动重试的瞬态网络错误
_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectTimeout,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # 指数退避基数（秒）: 1s, 2s, 4s


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
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(
                    max_keepalive_connections=50,
                    max_connections=200,
                    keepalive_expiry=30.0,
                ),
                trust_env=False,  # OneDBA 是内网服务，不走系统代理
            )
        return self._client

    def _check_response(self, data: dict[str, Any]) -> None:
        """检查 API 响应是否成功"""
        code = data.get("code")
        if code is not None and code != 0 and code != "0":
            message = data.get("message") or data.get("msg") or "未知错误"
            raise OneDBAError(f"OneDBA API 错误 (code={code}): {message}", code=code)

    async def _retry_request(self, request_name: str, coro_factory):
        """
        对瞬态网络错误自动重试（指数退避）。

        Args:
            request_name: 请求名称（用于日志）
            coro_factory: 返回 awaitable 的工厂函数，每次重试重新调用

        Returns:
            coro_factory 的返回值

        Raises:
            最后一次重试的异常（如果所有重试都失败）
        """
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await coro_factory()
            except _RETRYABLE_EXCEPTIONS as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"[OneDBA] {request_name} 第{attempt+1}次重试（{delay:.0f}s 后）: {e}")
                    await asyncio.sleep(delay)
                else:
                    print(f"[OneDBA] {request_name} 已重试{_MAX_RETRIES}次仍失败: {e}")
        raise last_exc  # type: ignore[misc]

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

        async def _do_request():
            response = await client.get(
                "/api/external/v1/agent/instance/schema/user/list",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            self._check_response(data)
            payload = data.get("data") or {}
            return payload.get("items") or []

        return await self._retry_request("list_databases", _do_request)

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

        async def _do_request():
            response = await client.post(
                "/api/external/v1/agent/query",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            self._check_response(data)
            return data.get("data") or {}

        return await self._retry_request("execute_sql", _do_request)

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