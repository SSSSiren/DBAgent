"""
OpenViking 会话记忆客户端 — 轻量 HTTP 封装

暴露对话记忆和 HDC 知识库所需的 API：
会话管理：
- create_session()  → POST /api/v1/sessions
- add_message()     → POST /api/v1/sessions/{id}/messages
- commit()          → POST /api/v1/sessions/{id}/commit

搜索与检索：
- find()            → POST /api/v1/search/find
- search()          → POST /api/v1/search/search

内容写入：
- write()           → POST /api/v1/content/write

文件系统操作：
- set_tags()        → POST /api/v1/fs/attrs/set_tags
- mkdir()           → POST /api/v1/fs/mkdir
- rm()              → DELETE /api/v1/fs

设计：
- 按请求创建（构造函数接收 user_id），保证多用户隔离
- 每次用完调用 close() 释放 HTTP 连接
- 不支持全局单例模式
- 所有方法自动解包 {"status":"ok","result":...}，错误时记录日志不抛出异常
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("vkdbagent.knowledge")


class OpenVikingClient:
    """OpenViking HTTP 客户端（按 user_id 隔离）"""

    def __init__(self, base_url: str, user_id: str = "default"):
        self._url = base_url.rstrip("/")
        self._user_id = user_id
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """初始化 HTTP 客户端（延迟创建，支持复用）"""
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            base_url=self._url,
            headers={
                "Content-Type": "application/json",
                "X-OpenViking-Account": "default",
                "X-OpenViking-User": self._user_id,
            },
            timeout=30,
        )

    async def close(self) -> None:
        """释放 HTTP 连接"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post(self, path: str, json_data: dict = None, timeout: float | None = None) -> dict:
        """POST 请求，自动解包 result 字段。可传入 timeout 覆盖客户端默认超时。"""
        if self._client is None:
            await self.start()
        resp = await self._client.post(path, json=json_data or {}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "ok" and "result" in data:
            return data["result"]
        return data

    async def _get(self, path: str, params: dict = None) -> dict:
        """GET 请求，自动解包 result 字段"""
        if self._client is None:
            await self.start()
        resp = await self._client.get(path, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "ok" and "result" in data:
            return data["result"]
        return data

    async def _get_raw(self, path: str, uri: str) -> dict:
        """GET 请求，uri 直接拼接在 URL 中（避免 httpx params 二次编码）。

        fs/ls 和 fs/read 返回的 URI 已经编码（如 %E6%9F%A5），
        直接用字符串拼接而非 httpx params，避免 % → %25 的二次编码。
        """
        if self._client is None:
            await self.start()
        resp = await self._client.get(f"{path}?uri={uri}")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "ok" and "result" in data:
            return data["result"]
        return data

    async def _delete(self, path: str, params: dict = None) -> dict:
        """DELETE 请求，自动解包 result 字段"""
        if self._client is None:
            await self.start()
        resp = await self._client.request("DELETE", path, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "ok" and "result" in data:
            return data["result"]
        return data

    # ── 会话管理 ──

    async def create_session(self) -> str:
        """创建 OpenViking 会话，返回 session_id"""
        result = await self._post("/api/v1/sessions")
        session_id = result.get("session_id", "")
        log.info("OpenViking session created: %s (user=%s)", session_id, self._user_id)
        return session_id

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """记录一条对话消息"""
        await self._post(
            f"/api/v1/sessions/{session_id}/messages",
            {"role": role, "content": content},
        )

    async def commit(
        self,
        session_id: str,
        keep_recent_count: int = 10,
    ) -> Optional[str]:
        """提交会话，触发长期记忆提取。返回 task_id 或 None"""
        result = await self._post(
            f"/api/v1/sessions/{session_id}/commit",
            {"keep_recent_count": keep_recent_count},
        )
        task_id = result.get("task_id")
        log.info(
            "OpenViking commit: session=%s task_id=%s (user=%s)",
            session_id, task_id, self._user_id,
        )
        return task_id

    # ── 记忆检索 ──

    async def retrieve_memories(self) -> list[dict[str, str]]:
        """
        检索用户的所有长期记忆。

        fs/ls 返回的条目 abstract 可能为空，按优先级回退：
        1. entry["abstract"]（如果非空）
        2. 文件名（去掉 .md 后缀）

        Returns:
            记忆列表，每项包含 category、abstract、name
        """
        import os

        memory_categories = [
            "experiences", "events", "entities",
            "preferences", "tools", "skills", "trajectories",
        ]
        all_memories: list[dict[str, str]] = []

        for base_path in ("memories", "peers"):
            for category in memory_categories:
                try:
                    uri = f"viking://user/{self._user_id}/{base_path}/{category}"
                    entries = await self._get_raw("/api/v1/fs/ls", uri)
                    entries = entries if isinstance(entries, list) else entries.get("result", [])
                except Exception:
                    entries = []

                for entry in entries:
                    if entry.get("isDir", False):
                        continue
                    uri = entry.get("uri", "")
                    name = entry.get("name", "")
                    # name 通常为空，从 uri 提取文件名
                    file_name = name or (uri.rstrip("/").split("/")[-1] if uri else "")
                    abstract = (entry.get("abstract") or "").strip()

                    # 回退1: 尝试 fs/read
                    if not abstract:
                        abstract = await self._read_file_abstract(uri)

                    # 回退2: 用文件名（去掉 .md 后缀和时间戳后缀）
                    if not abstract and file_name:
                        abstract = file_name.replace(".md", "").rsplit("_", 1)[0]

                    if abstract:
                        all_memories.append({
                            "category": category,
                            "abstract": abstract,
                            "name": file_name,
                        })

            if all_memories:
                break

        return all_memories

    # ── 搜索与检索（HDC）──

    async def find(
        self,
        query: str,
        target_uri: str = "",
        limit: int = 10,
        score_threshold: Optional[float] = None,
        level: Optional[list[int]] = None,
        filter: Optional[dict] = None,
        context_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """向量 + tags 精确检索，返回匹配项列表。

        POST /api/v1/search/find
        结果自动解包 {"status":"ok","result":...}。
        错误时记录警告并返回空 dict，不抛出异常。

        level: 过滤内容层级，[0,1] 只返回 L0+L1（摘要+概览），[2] 返回 L2（完整内容）。
        """
        try:
            payload: dict[str, Any] = {
                "query": query,
                "target_uri": target_uri,
                "limit": limit,
            }
            if score_threshold is not None:
                payload["score_threshold"] = score_threshold
            if level is not None:
                payload["level"] = level
            if filter is not None:
                payload["filter"] = filter
            if context_type is not None:
                payload["context_type"] = context_type
            if tags is not None:
                payload["tags"] = tags

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    return await self._post("/api/v1/search/find", payload)
                except (httpx.ReadError, httpx.RemoteProtocolError) as e:
                    if attempt < max_retries - 1:
                        wait = 0.5 * (attempt + 1)
                        log.warning(
                            "OpenViking find retry %d/%d after %.1fs: %s",
                            attempt + 1, max_retries, wait, e,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise
        except Exception:
            log.warning("OpenViking find failed", exc_info=True)
            return {}

    async def search(
        self,
        query: str,
        target_uri: str = "",
        session_id: Optional[str] = None,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter: Optional[dict] = None,
        context_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """意图感知检索（需要 session_id 上下文）。

        POST /api/v1/search/search
        结果自动解包 {"status":"ok","result":...}。
        错误时记录警告并返回空 dict，不抛出异常。
        """
        try:
            payload: dict[str, Any] = {
                "query": query,
                "target_uri": target_uri,
                "limit": limit,
            }
            if session_id is not None:
                payload["session_id"] = session_id
            if score_threshold is not None:
                payload["score_threshold"] = score_threshold
            if filter is not None:
                payload["filter"] = filter
            if context_type is not None:
                payload["context_type"] = context_type
            if tags is not None:
                payload["tags"] = tags
            return await self._post("/api/v1/search/search", payload)
        except Exception:
            log.warning("OpenViking search failed", exc_info=True)
            return {}

    # ── 内容写入（HDC）──

    async def write(
        self,
        uri: str,
        content: str,
        mode: str = "replace",
        wait: bool = False,
        timeout: Optional[float] = None,
    ) -> dict:
        """写入文件内容到 OpenViking。

        POST /api/v1/content/write
        wait=True 时阻塞直到 SemanticProcessor 处理完成（L0/L1 摘要生成）。
        结果自动解包 {"status":"ok","result":...}。
        错误时记录警告并返回空 dict，不抛出异常。

        如果 mode="replace" 失败（文件不存在），自动回退到 mode="create"。
        ReadError/RemoteProtocolError 自动重试 3 次（与 find() 一致）。
        """
        async def _do_write(payload: dict) -> dict:
            return await self._post("/api/v1/content/write", payload, timeout=httpx_timeout)

        try:
            payload: dict[str, Any] = {
                "uri": uri,
                "content": content,
                "mode": mode,
                "wait": wait,
            }
            if timeout is not None:
                payload["timeout"] = timeout
            if timeout is not None:
                httpx_timeout = timeout
            elif wait:
                httpx_timeout = 120.0
            else:
                httpx_timeout = None

            for attempt in range(3):
                try:
                    return await _do_write(payload)
                except (httpx.ReadError, httpx.RemoteProtocolError) as e:
                    if attempt == 2:
                        raise
                    backoff = 0.5 * (2 ** attempt)
                    log.debug(
                        "OpenViking write retry %d/3 after %.1fs: %s",
                        attempt + 1, backoff, e,
                    )
                    await asyncio.sleep(backoff)
        except Exception:
            # mode="replace" 要求文件已存在；如果失败，回退到 create
            if mode == "replace":
                try:
                    payload["mode"] = "create"
                    # wait=True is preserved from the original payload for SemanticProcessor
                    return await self._post("/api/v1/content/write", payload, timeout=httpx_timeout)
                except Exception:
                    log.warning(
                        "OpenViking write (create fallback) failed: uri=%s mode=%s wait=%s",
                        uri, mode, payload.get("wait"), exc_info=True,
                    )
                    return {}
            log.warning("OpenViking write failed: uri=%s", uri, exc_info=True)
            return {}

    # ── 文件系统操作（HDC）──

    async def set_tags(
        self,
        uri: str,
        tags: list[str],
        mode: str = "replace",
        recursive: bool = False,
    ) -> dict:
        """设置文件/目录的 tags。

        POST /api/v1/fs/attrs/set_tags
        结果自动解包 {"status":"ok","result":...}。
        错误时记录警告并返回空 dict，不抛出异常。
        """
        try:
            payload: dict[str, Any] = {
                "uri": uri,
                "tags": tags,
                "mode": mode,
                "recursive": recursive,
            }
            result = await self._post("/api/v1/fs/attrs/set_tags", payload)
            if not result:
                log.warning(
                    "OpenViking set_tags returned empty result: uri=%s tags=%s mode=%s",
                    uri, tags, mode,
                )
            return result
        except Exception:
            log.warning(
                "OpenViking set_tags failed: uri=%s tags=%s mode=%s",
                uri, tags, mode, exc_info=True,
            )
            return {}

    async def mkdir(
        self,
        uri: str,
        description: Optional[str] = None,
    ) -> dict:
        """创建目录。

        POST /api/v1/fs/mkdir
        结果自动解包 {"status":"ok","result":...}。
        错误时记录警告并返回空 dict，不抛出异常。
        """
        try:
            payload: dict[str, Any] = {"uri": uri}
            if description is not None:
                payload["description"] = description
            return await self._post("/api/v1/fs/mkdir", payload)
        except Exception:
            log.warning("OpenViking mkdir failed: uri=%s", uri, exc_info=True)
            return {}

    async def rm(
        self,
        uri: str,
        recursive: bool = False,
        wait: bool = False,
        timeout: Optional[float] = None,
    ) -> dict:
        """删除文件或目录。

        DELETE /api/v1/fs
        结果自动解包 {"status":"ok","result":...}。
        错误时记录警告并返回空 dict，不抛出异常。
        """
        try:
            params: dict[str, Any] = {
                "uri": uri,
                "recursive": recursive,
                "wait": wait,
            }
            if timeout is not None:
                params["timeout"] = timeout
            return await self._delete("/api/v1/fs", params)
        except Exception:
            log.warning("OpenViking rm failed: uri=%s", uri, exc_info=True)
            return {}

    async def _read_file_abstract(self, uri: str) -> str:
        """读取单个文件的 abstract，失败返回空字符串"""
        try:
            detail = await self._get_raw("/api/v1/fs/read", uri)
            return (detail.get("abstract") or "").strip() if isinstance(detail, dict) else ""
        except Exception:
            return ""