"""
OpenViking 会话记忆客户端 — 轻量 HTTP 封装

只暴露对话记忆所需的 3 个 API：
- create_session()  → POST /api/v1/sessions
- add_message()     → POST /api/v1/sessions/{id}/messages
- commit()          → POST /api/v1/sessions/{id}/commit

设计：
- 按请求创建（构造函数接收 user_id），保证多用户隔离
- 每次用完调用 close() 释放 HTTP 连接
- 不支持全局单例模式
"""

from __future__ import annotations

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

    async def _post(self, path: str, json_data: dict = None) -> dict:
        """POST 请求，自动解包 result 字段"""
        if self._client is None:
            await self.start()
        resp = await self._client.post(path, json=json_data or {})
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

        遍历 viking://user/{user_id}/memories/ 下的子目录，
        读取每个记忆文件的 abstract 字段。

        Returns:
            记忆列表，每项包含 category、abstract、content
        """
        memory_categories = [
            "experiences", "events", "entities",
            "preferences", "tools", "skills", "trajectories",
        ]
        all_memories: list[dict[str, str]] = []

        for category in memory_categories:
            try:
                uri = f"viking://user/{self._user_id}/memories/{category}"
                entries = await self._post("/api/v1/fs/ls", {"uri": uri})
                entries = entries if isinstance(entries, list) else entries.get("result", [])
            except Exception:
                continue

            for entry in entries:
                if entry.get("isDir", False):
                    continue
                uri = entry.get("uri", "")
                try:
                    detail = await self._post("/api/v1/fs/read", {"uri": uri})
                    abstract = detail.get("abstract", "") if isinstance(detail, dict) else ""
                    if abstract:
                        all_memories.append({
                            "category": category,
                            "abstract": abstract,
                            "name": entry.get("name", ""),
                        })
                except Exception:
                    continue

        log.info(
            "OpenViking retrieve: user=%s memories=%d",
            self._user_id, len(all_memories),
        )
        return all_memories