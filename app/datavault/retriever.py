"""
HDC Retriever — 封装 OpenViking find API 调用，格式化 HDC 检索结果用于上下文注入。

Two-stage retrieval:
  Stage 1: find matching tables via tags+vector (level=[0,1])
  Stage 2: find relevant columns per table (level=[2], max 6 per table)

Graceful degradation: OpenViking unavailable → log warning, return None.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.datavault.models import HDCContext, TableMatch
from app.knowledge.openviking import OpenVikingClient

log = logging.getLogger("vkdbagent.datavault")


class HDCRetriever:
    """封装 OpenViking find API 调用，格式化 HDC 检索结果用于上下文注入。

    两阶段检索：
    1. 通过 tags 精确过滤 + 向量语义检索匹配表（level=[0,1]）
    2. 对 top 5 表检索相关列（level=[2]，每表最多 6 列）

    静默降级：OpenViking 不可用时记录警告日志并返回 None，不阻塞对话流程。
    """

    def __init__(self, ov_client: OpenVikingClient):
        self._ov = ov_client

    # ── Public API ──

    async def retrieve(
        self,
        user_input: str,
        database_name: str,
    ) -> Optional[HDCContext]:
        """两阶段 HDC 检索，返回 HDCContext 或 None（降级）。

        Stage 1: find(query, target_uri=".../hdc/{db}/_tables",
                       tags=["hdc_level=table"], level=[0,1], limit=10)
        Stage 2: for top 5 tables, find(query, target_uri=".../hdc/{db}/_tables/{table}",
                                       level=[2], limit=6)

        Returns:
            HDCContext with database_summary and matched_tables, or None on degradation.
        """
        target_base = f"viking://resources/hdc/{database_name}"

        # ── Stage 1: find matching tables ──
        result = await self._ov.find(
            query=user_input,
            target_uri=f"{target_base}/_tables",
            tags=["hdc_level=table"],
            level=[0, 1],
            limit=10,
        )

        matches = self._extract_matches(result)
        if not matches:
            log.info(
                "HDC retrieval: no matching tables for database=%s query=%s",
                database_name,
                user_input[:80],
            )
            return None

        # ── Stage 2: for top 5 tables, read _INDEX.md for real metadata ──
        # find() returns derived files (.abstract.md/.overview.md) which
        # are VLM summaries — they don't carry our tags. Instead, read
        # the actual _INDEX.md files we wrote for real metadata.
        #
        # Sort matches by score (desc) so that most relevant tables appear first,
        # then dedup by table_name (a single table may have multiple returned files
        # like .abstract.md + .overview.md).
        candidates: list[tuple[str, float]] = []  # (table_name, best_score)
        for match in matches:
            table_name = self._extract_table_name(match)
            if not table_name:
                continue
            score = match.get("score", 0.0)
            # Keep the highest score for each table
            existing = next((c for c in candidates if c[0] == table_name), None)
            if existing is None:
                candidates.append((table_name, score))
            else:
                idx = candidates.index(existing)
                if score > existing[1]:
                    candidates[idx] = (table_name, score)

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        table_matches: list[TableMatch] = []
        for table_name, score in candidates[:5]:
            # Read _INDEX.md to get real metadata we wrote
            index_content = await self._read_index(target_base, table_name)
            main_entity, table_type, description = self._parse_index(index_content)

            relevant_columns = await self._retrieve_columns(
                user_input, target_base, table_name
            )

            table_matches.append(TableMatch(
                table_name=table_name,
                main_entity=main_entity,
                table_type=table_type,
                description=description,
                relevant_columns=relevant_columns,
            ))

        if not table_matches:
            return None

        # ── Retrieve database summary ──
        database_summary = await self._retrieve_database_summary(target_base)

        return HDCContext(
            database_summary=database_summary,
            matched_tables=table_matches,
        )

    def format_context(self, hdc: HDCContext) -> str:
        """将 HDCContext 格式化为 [数据底座] 上下文字符串。

        格式包含：
        - 数据库概览摘要
        - 匹配的业务表列表（表名、核心实体、类型、描述、相关列）

        Returns:
            格式化的上下文字符串，hdc 为 None 时返回空字符串。
        """
        if not hdc:
            return ""

        lines = ["[数据底座 — 数据库知识]"]

        # Database summary
        if hdc.database_summary:
            lines.append("")
            lines.append(f"**数据库概览**：{hdc.database_summary}")

        # Matched tables
        if hdc.matched_tables:
            lines.append("")
            lines.append("**匹配的业务表**：")
            for tm in hdc.matched_tables:
                entity_label = f"({tm.main_entity})" if tm.main_entity else ""
                type_label = f"[{tm.table_type}]" if tm.table_type else ""
                header_parts = [f"### {tm.table_name}"]
                if entity_label:
                    header_parts.append(entity_label)
                if type_label:
                    header_parts.append(type_label)
                lines.append("")
                lines.append(" ".join(header_parts))
                if tm.description:
                    lines.append(f"  {tm.description}")
                if tm.relevant_columns:
                    lines.append("  **相关列**：")
                    for col in tm.relevant_columns:
                        lines.append(f"    - {col}")

        return "\n".join(lines)

    # ── Private helpers ──

    async def _read_index(self, target_base: str, table_name: str) -> str:
        """Read the actual _INDEX.md file we wrote (not VLM summary).

        Uses OpenViking content/read API to get raw L2 content.
        """
        uri = f"{target_base}/_tables/{table_name}/_INDEX.md"
        try:
            raw = await self._ov._get_raw("/api/v1/content/read", uri)
            if isinstance(raw, str):
                return raw
            if isinstance(raw, dict):
                return raw.get("content", "") or raw.get("result", "") or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _parse_index(content: str) -> tuple[str, str, str]:
        """Parse our _INDEX.md format to extract main_entity, table_type, description.

        Our format:
          <main_entity>                    ← Line 1: plain text entity name
                                          ← Line 2: blank
          **<table_name>** 是 **<type>** 类型的表，主键为 `<pk>`。  ← Line 3
          ...
          ## 详细描述
          description text
        """
        main_entity = ""
        table_type = ""
        description = ""
        lines = content.split("\n")

        # Line 1: main_entity (plain text, not bold)
        if lines:
            first = lines[0].strip()
            if first and not first.startswith("#") and not first.startswith("**"):
                main_entity = first

        # Line 3: "**table_name** 是 **fact** 类型的表"
        if len(lines) >= 3:
            meta_line = lines[2].strip()
            if "fact" in meta_line:
                table_type = "fact"
            elif "dimension" in meta_line or "维度" in meta_line:
                table_type = "dimension"
            elif "bridge" in meta_line or "桥接" in meta_line:
                table_type = "bridge"

        # Description: after "## 详细描述"
        in_detail = False
        for line in lines:
            if "详细描述" in line or "Detailed Description" in line:
                in_detail = True
                continue
            if in_detail and line.strip() and not line.strip().startswith("*"):
                description = line.strip()
                break

        return main_entity, table_type, description

    async def _retrieve_columns(
        self,
        user_input: str,
        target_base: str,
        table_name: str,
    ) -> list[str]:
        """Stage 2: 检索某张表的相关列描述（level=[2]，最多 6 列）。

        使用 find(level=[2]) 定位相关列名，再读取原始 .md 文件获取简洁描述。
        检索失败时返回空列表，不中断整体流程。
        """
        result = await self._ov.find(
            query=user_input,
            target_uri=f"{target_base}/_tables/{table_name}",
            level=[2],
            limit=6,
        )

        if not result:
            return []

        matches = self._extract_matches(result)
        columns: list[str] = []
        for match in matches[:6]:
            col_name = self._extract_column_name(match)
            if not col_name or col_name == "_INDEX":
                continue
            # Read the original .md file for the short description we wrote
            col_content = await self._read_column_file(target_base, table_name, col_name)
            if col_content:
                columns.append(f"{col_name}: {col_content}")
        return columns

    async def _read_column_file(self, target_base: str, table_name: str, column_name: str) -> str:
        """Read a column .md file to get the original short description."""
        uri = f"{target_base}/_tables/{table_name}/{column_name}.md"
        try:
            raw = await self._ov._get_raw("/api/v1/content/read", uri)
            content = ""
            if isinstance(raw, str):
                content = raw
            elif isinstance(raw, dict):
                content = raw.get("content", "") or raw.get("result", "") or ""
            # Extract the first meaningful line after the heading
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("**"):
                    return stripped[:200]
            return content[:200] if content else ""
        except Exception:
            return ""

    async def _retrieve_database_summary(self, target_base: str) -> str:
        """读取数据库根目录的 _INDEX.md 获取摘要。"""
        uri = f"{target_base}/_INDEX.md"
        try:
            raw = await self._ov._get_raw("/api/v1/content/read", uri)
            content = ""
            if isinstance(raw, str):
                content = raw
            elif isinstance(raw, dict):
                content = raw.get("content", "") or raw.get("result", "") or ""

            parts: list[str] = []
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped or stripped.startswith("# "):
                    continue
                if "核心实体" in stripped:
                    parts.append(stripped.strip("* "))
                elif "表数量" in stripped:
                    parts.append(stripped.strip("* "))
                elif not stripped.startswith("**") and len(stripped) > 20:
                    parts.append(stripped)
                    break  # got the description paragraph

            return "；".join(parts) if parts else content[:300]
        except Exception:
            return ""

    # ── Static helpers ──

    @staticmethod
    def _extract_matches(result) -> list[dict]:
        """从 find API 返回结果中提取匹配项列表。

        兼容多种响应格式：
        - 直接返回的 list
        - dict 中的 "matches" / "items" / "data" / "results" 键
        """
        if not result:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("matches", "items", "data", "results", "resources"):
                val = result.get(key)
                if isinstance(val, list):
                    return val
                if isinstance(val, dict):
                    return [val]
        return []

    @staticmethod
    def _extract_table_name(match: dict) -> str:
        """从匹配项的 URI 中提取表名。

        URI 格式: viking://resources/hdc/{db}/_tables/{table_name}
        或:       viking://resources/hdc/{db}/_tables/{table_name}/.abstract.md
        """
        uri = match.get("uri", "")
        if uri:
            parts = uri.rstrip("/").split("/")
            # If the last segment is a derived file (.abstract.md, .overview.md),
            # the table name is the parent directory
            last = parts[-1] if parts else ""
            if last in (".abstract.md", ".overview.md", ".abstract", ".overview"):
                if len(parts) >= 2:
                    return parts[-2]
                return ""
            if last.endswith(".md"):
                last = last[:-3]
            return last
        name = match.get("name", "")
        if name:
            if name in (".abstract", ".overview", ".abstract.md", ".overview.md"):
                return ""
            return name.replace(".md", "")
        return ""

    @staticmethod
    def _extract_column_name(match: dict) -> str:
        """从匹配项的 URI 中提取列名。

        URI 格式: viking://resources/hdc/{db}/_tables/{table}/{column}.md
        跳过 .abstract.md 和 .overview.md
        """
        uri = match.get("uri", "")
        if uri:
            parts = uri.rstrip("/").split("/")
            name = parts[-1] if parts else ""
            # Skip derived files
            if name in (".abstract.md", ".overview.md", ".abstract", ".overview"):
                return ""
            if name.endswith(".md"):
                name = name[:-3]
            return name
        raw_name = match.get("name", "")
        if raw_name in (".abstract", ".overview", ".abstract.md", ".overview.md", ""):
            return ""
        return raw_name.replace(".md", "")

    @staticmethod
    def _parse_tags(tags) -> dict[str, str]:
        """解析 tags 为 key-value 字典。

        兼容两种格式：
        - list[str]: ["hdc_level=table", "main_entity=订单/order", "table_type=fact"]
        - dict[str, str]: {"hdc_level": "table", "main_entity": "订单/order"}
        """
        if isinstance(tags, dict):
            return {str(k): str(v) for k, v in tags.items()}
        if isinstance(tags, list):
            result: dict[str, str] = {}
            for tag in tags:
                if isinstance(tag, str):
                    if "=" in tag:
                        key, _, value = tag.partition("=")
                    elif ":" in tag:
                        key, _, value = tag.partition(":")
                    else:
                        continue
                    result[key.strip()] = value.strip()
            return result
        return {}