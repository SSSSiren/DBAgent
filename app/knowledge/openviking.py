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

        先查 viking://user/{user_id}/memories/，若无结果则回退到
        viking://user/{user_id}/peers/（兼容不同 OpenViking 版本）。

        Returns:
            记忆列表，每项包含 category、abstract、content
        """
        memory_categories = [
            "experiences", "events", "entities",
            "preferences", "tools", "skills", "trajectories",
        ]
        all_memories: list[dict[str, str]] = []

        # 先尝试 memories 路径，再回退到 peers
        for base_path in ("memories", "peers"):
            print(f"[KB] retrieve: trying base_path={base_path}")
            for category in memory_categories:
                try:
                    uri = f"viking://user/{self._user_id}/{base_path}/{category}"
                    entries = await self._get("/api/v1/fs/ls", {"uri": uri})
                    entries = entries if isinstance(entries, list) else entries.get("result", [])
                    if entries:
                        print(f"[KB] retrieve: {base_path}/{category} -> {len(entries)} entries")
                except Exception as e:
                    print(f"[KB] retrieve: {base_path}/{category} failed: {e}")
                    entries = []

                for entry in entries:
                    if entry.get("isDir", False):
                        continue
                    file_uri = entry.get("uri", "")
                    try:
                        detail = await self._get("/api/v1/fs/read", {"uri": file_uri})
                        abstract = detail.get("abstract", "") if isinstance(detail, dict) else ""
                        if abstract:
                            all_memories.append({
                                "category": category,
                                "abstract": abstract,
                                "name": entry.get("name", ""),
                            })
                            print(f"[KB] retrieve: +memory [{category}] {abstract[:80]}")
                    except Exception as e:
                        print(f"[KB] retrieve: fs/read {file_uri} failed: {e}")
                        continue

            # 回退：尝试平铺目录（文件直接在 base_path 下，无子分类）
            if not all_memories:
                try:
                    uri = f"viking://user/{self._user_id}/{base_path}"
                    entries = await self._get("/api/v1/fs/ls", {"uri": uri})
                    entries = entries if isinstance(entries, list) else entries.get("result", [])
                    print(f"[KB] retrieve: flat {base_path} -> {len(entries)} entries")
                    for entry in entries:
                        if entry.get("isDir", False):
                            print(f"[KB] retrieve:   skip dir: {entry.get('uri','?')}")
                            continue
                        file_uri = entry.get("uri", "")
                        try:
                            detail = await self._get("/api/v1/fs/read", {"uri": file_uri})
                            abstract = detail.get("abstract", "") if isinstance(detail, dict) else ""
                            if abstract:
                                all_memories.append({
                                    "category": base_path,
                                    "abstract": abstract,
                                    "name": entry.get("name", ""),
                                })
                                print(f"[KB] retrieve: +memory [{base_path}] {abstract[:80]}")
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[KB] retrieve: flat {base_path} failed: {e}")

            if all_memories:
                log.info("OpenViking retrieve: user=%s path=%s memories=%d",
                         self._user_id, base_path, len(all_memories))
                break  # 找到记忆就不再回退
            else:
                log.debug("OpenViking retrieve: user=%s path=%s empty", self._user_id, base_path)

        return all_memories