"""
HDC Retriever — 封装 OpenViking find API 调用，格式化 HDC 检索结果用于上下文注入。

Two-stage retrieval:
  Stage 1: find matching tables via L2 column-level file search (level=[2], limit=200, score_threshold=0.25)
  Stage 2: find relevant columns per table (level=[2], max 6 per table, from _columns/ subdirectory)

Table scoring: sum of top-3 column match scores, with entity-level explosion radius control (max 2 per entity).
Fallback: when L2 returns nothing, retry with level=[0,1] for knowledge bases with L0/L1 summaries.

Graceful degradation: OpenViking unavailable → log warning, return None.

Storage key format: {schemaId}/{database_name}
  e.g. viking://resources/hdc/65938636/dw_onedba/_tables
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.datavault.models import HDCContext, TableMatch
from app.datavault.uploader import (
    _columns_dir_uri,
    _db_index_uri,
    _table_dir_uri,
    _table_index_uri,
    _tables_dir_uri,
    storage_key,
)
from app.knowledge.openviking import OpenVikingClient

log = logging.getLogger("vkdbagent.datavault")


class HDCRetriever:
    """封装 OpenViking find API 调用，格式化 HDC 检索结果用于上下文注入。

    两阶段检索：
    1. 通过 L0/L1 层级语义摘要匹配表（level=[0,1]，limit=200，score_threshold=0.25）
    2. 对 top 5 表检索相关列（level=[2]，每表最多 6 列，从 _columns/ 子目录）

    表评分使用 top-3 匹配分数累积求和，并进行业务实体爆炸半径控制（每实体最多 2 表）。
    旧格式知识库自动回退到 level=[2] 检索。

    静默降级：OpenViking 不可用时记录警告日志并返回 None，不阻塞对话流程。
    """

    def __init__(self, ov_client: OpenVikingClient):
        self._ov = ov_client

    # ── Public API ──

    async def retrieve(
        self,
        user_input: str,
        schema_id: int,
        database_name: str,
        table_filter: list[str] | None = None,
        namespace: str | None = None,
    ) -> Optional[HDCContext]:
        """两阶段 HDC 检索，返回 HDCContext 或 None（降级）。

        In the memory path, only file-level (level=2) embeddings exist;
        directory-level (level=0,1) summaries are never generated (VLM is skipped).
        Stage 1 searches level=2 files across all tables, then aggregates by
        parent table directory. Stage 2 is a no-op since column-level data
        is already returned from Stage 1.

        Args:
            table_filter: 可选的白名单表名列表。传入时，只有匹配的表会进入 Top 5
                          排序，未匹配的表被跳过。用于限定知识库范围。
            namespace: 可选的HDC命名空间，用于检索特定变体的知识库
                       （如 incomplete/complete/overcomplete）。

        Returns:
            HDCContext with database_summary and matched_tables, or None on degradation.
        """
        key = storage_key(schema_id, database_name, namespace=namespace)
        tables_uri = _tables_dir_uri(key)

        # ── Stage 1: find matching tables via L2 column-level file search ──
        # level=[2] searches individual column .md files. Each column is a separate
        # vector match, providing fine-grained semantic evidence. High limit and
        # score_threshold ensure correct tables enter the candidate set even in
        # large (400+ table) knowledge bases.
        result = await self._ov.find(
            query=user_input,
            target_uri=tables_uri,
            level=[2],
            limit=200,
            score_threshold=0.25,
        )

        matches = self._extract_matches(result)

        # Filesystem fallback: when embedding hasn't completed yet
        if not matches:
            log.info(
                "HDC retrieval: find returned nothing for key=%s. "
                "Falling back to filesystem listing (embedding may not be ready).",
                key,
            )
            matches = await self._fs_table_fallback(tables_uri, user_input)

        # ── L0/L1 fallback: when L2 returns nothing, try directory-level summaries ──
        # This covers the case where a knowledge base has L0/L1 generated but
        # column-level embeddings are not yet indexed.
        if not matches:
            log.info(
                "HDC retrieval: L2 find returned nothing for key=%s. "
                "Retrying with level=[0,1] (directory-level summaries).",
                key,
            )
            result_l0l1 = await self._ov.find(
                query=user_input,
                target_uri=tables_uri,
                level=[0, 1],
                limit=200,
                score_threshold=0.25,
            )
            matches = self._extract_matches(result_l0l1)

        if not matches:
            log.info(
                "HDC retrieval: no matching tables for key=%s query=%s",
                key,
                user_input[:80],
            )
            return None

        # ── Stage 2: score aggregation by table (sum of top-3 match scores) ──
        # L2 find() returns per-column file matches. We collect ALL scores per
        # table_name, then use sum(top-3) as the composite score. This accumulates
        # multi-column evidence — a table with multiple relevant columns ranks
        # higher than one with a single coincidental high-scoring column.
        table_scores: dict[str, list[float]] = {}
        for match in matches:
            table_name = self._extract_table_name(match)
            if not table_name:
                continue
            # Skip non-table directories (like _tables, _relationships)
            if table_name.startswith("_"):
                continue
            score = match.get("score", 0.0)
            table_scores.setdefault(table_name, []).append(score)

        candidates = [
            (tn, sum(sorted(scores, reverse=True)[:3]))
            for tn, scores in table_scores.items()
        ]

        # Sort by composite score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        # ── Table filter: 限定白名单后取 Top 5 ──
        if table_filter is not None:
            whitelist_lower = {t.lower() for t in table_filter}
            candidates = [(n, s) for n, s in candidates if n.lower() in whitelist_lower]

        # ── Entity dedup: enforce explosion radius per business entity ──
        # To avoid confusing the LLM with multiple similar tables from the same
        # business entity, limit each entity to at most MAX_PER_ENTITY tables.
        # The main_entity is extracted from the first line of _INDEX.md;
        # when unreadable, fall back to the table name itself as entity identifier.
        MAX_PER_ENTITY = 2
        entity_counts: dict[str, int] = {}
        diversified: list[tuple[str, float]] = []
        for table_name, score in candidates:
            entity = await self._get_main_entity(key, table_name)
            count = entity_counts.get(entity, 0)
            if count < MAX_PER_ENTITY:
                entity_counts[entity] = count + 1
                diversified.append((table_name, score))
            if len(diversified) >= 5:
                break

        table_matches: list[TableMatch] = []
        for table_name, score in diversified:
            # Read _INDEX.md to get real metadata we wrote
            index_content = await self._read_index(key, table_name)
            main_entity, table_type, description, usage_scenario = self._parse_index(index_content)

            relevant_columns = await self._retrieve_columns(
                user_input, key, table_name
            )

            table_matches.append(TableMatch(
                table_name=table_name,
                main_entity=main_entity,
                table_type=table_type,
                description=description,
                usage_scenario=usage_scenario,
                relevant_columns=relevant_columns,
            ))

        if not table_matches:
            return None

        # ── Retrieve database summary ──
        database_summary = await self._retrieve_database_summary(key)

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
                if tm.usage_scenario:
                    lines.append(f"  **使用场景**: {tm.usage_scenario}")
                if tm.relevant_columns:
                    lines.append("  **相关列**：")
                    for col in tm.relevant_columns:
                        lines.append(f"    - {col}")

        return "\n".join(lines)

    # ── Private helpers ──

    async def _get_main_entity(self, key: str, table_name: str) -> str:
        """Extract the business entity identifier from _INDEX.md first line.

        Reads the first line of _INDEX.md via existing _read_index(). If the
        line is non-empty and does not start with "#", returns it as the
        entity label. Otherwise falls back to table_name as the entity id.

        This is used by entity dedup (explosion radius control) to group
        similar tables from the same business domain.
        """
        content = await self._read_index(key, table_name)
        if content:
            first_line = content.split("\n")[0].strip()
            if first_line and not first_line.startswith("#"):
                return first_line
        return table_name

    async def _read_index(self, key: str, table_name: str) -> str:
        """Read the actual _INDEX.md file we wrote (not VLM summary).

        Uses OpenViking content/read API to get raw L2 content.
        """
        uri = _table_index_uri(key, table_name)
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
    def _parse_index(content: str) -> tuple[str, str, str, str]:
        """Parse our _INDEX.md format to extract main_entity, table_type, description, usage_scenario.

        Our format:
          <main_entity>                    ← Line 1: plain text entity name
                                          ← Line 2: blank
          **<table_name>** 是 **<type>** 类型的表，主键为 `<pk>`。  ← Line 3
          ...
          ## 详细描述
          description text
          ## 使用场景
          usage scenario text
        """
        main_entity = ""
        table_type = ""
        description = ""
        usage_scenario = ""
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
            if "使用场景" in line:
                in_detail = False
            if in_detail and line.strip() and not line.strip().startswith("*"):
                description = line.strip()
                in_detail = False
            if "详细描述" in line or "Detailed Description" in line:
                in_detail = True

        # Usage scenario: after "## 使用场景"
        in_scenario = False
        for line in lines:
            if in_scenario and line.strip() and not line.strip().startswith("*") and not line.strip().startswith("#"):
                usage_scenario = line.strip()
                break
            if "使用场景" in line:
                in_scenario = True

        return main_entity, table_type, description, usage_scenario

    async def _retrieve_columns(
        self,
        user_input: str,
        key: str,
        table_name: str,
    ) -> list[str]:
        """Stage 2: 检索某张表的相关列描述（level=[2]，最多 6 列）。

        使用 find(level=[2]) 定位相关列名，再读取原始 .md 文件获取简洁描述。
        检索失败时返回空列表，不中断整体流程。

        优先从 _columns/ 子目录检索（新格式），若子目录不存在则回退到表目录。
        """
        # Try new format: columns are in _columns/ subdirectory
        result = await self._ov.find(
            query=user_input,
            target_uri=_columns_dir_uri(key, table_name),
            level=[2],
            limit=6,
        )

        matches = self._extract_matches(result)
        if not matches:
            # Fallback to old format: columns are in the table directory itself.
            # We check extracted matches rather than result, because find() returns
            # a non-empty dict even for non-existent directories (e.g. with empty lists).
            result = await self._ov.find(
                query=user_input,
                target_uri=_table_dir_uri(key, table_name),
                level=[2],
                limit=6,
            )
            matches = self._extract_matches(result)

        if not matches:
            return []
        columns: list[str] = []
        for match in matches[:6]:
            col_name = self._extract_column_name(match)
            if not col_name or col_name == "_INDEX":
                continue
            # Read the original .md file for the short description we wrote
            col_content = await self._read_column_file(key, table_name, col_name)
            if col_content:
                columns.append(f"{col_name}: {col_content}")
        return columns

    async def _read_column_file(self, key: str, table_name: str, column_name: str) -> str:
        """Read a column .md file to get the original short description.

        Tries the new format (_columns/ subdirectory) first, then falls back to
        the old format (table directory) for backward compatibility.
        """
        # Try new format: columns are in _columns/ subdirectory
        new_uri = f"{_columns_dir_uri(key, table_name)}/{column_name}.md"
        content = await self._try_read_file(new_uri)
        if content:
            return content

        # Fallback to old format: columns are in the table directory itself
        old_uri = f"{_table_dir_uri(key, table_name)}/{column_name}.md"
        content = await self._try_read_file(old_uri)
        if content:
            return content

        return ""

    async def _try_read_file(self, uri: str) -> str:
        """Read a file and extract the first meaningful line after the heading.

        Returns empty string on any error.
        """
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

    async def _retrieve_database_summary(self, key: str) -> str:
        """读取数据库根目录的 _INDEX.md 获取摘要。"""
        uri = _db_index_uri(key)
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
                # Remove markdown bold markers
                cleaned = stripped.replace("**", "")
                if "核心实体" in cleaned:
                    parts.append(cleaned.strip("* "))
                elif "表数量" in cleaned:
                    parts.append(cleaned.strip("* "))
                elif not stripped.startswith("**") and len(stripped) > 20:
                    parts.append(stripped)
                    break  # got the description paragraph

            return "；".join(parts) if parts else content[:300]
        except Exception:
            return ""

    # ── Static helpers ──

    async def _fs_table_fallback(
        self, tables_uri: str, user_input: str
    ) -> list[dict]:
        """文件系统 fallback：直接列出 _tables 目录，按关键词匹配 _INDEX.md。

        当 OpenViking embedding 尚未完成时（如 wait=False 上传后），
        find() 返回空结果。此方法用 fs/ls 列出目录，逐表读取 _INDEX.md
        用关键词匹配 main_entity 或内容。

        Returns:
            list of synthetic match dicts with table_name and score=0.0.
        """
        # Extract key from tables_uri: "viking://user/.../memories/hdc/{key}/_tables" → "{key}"
        # _tables_dir_uri produces ".../hdc/{key}/_tables", so strip the "/_tables" suffix
        key = tables_uri.removesuffix("/_tables").rsplit("/hdc/", 1)[-1] if "/hdc/" in tables_uri else tables_uri
        try:
            raw = await self._ov._get_raw("/api/v1/fs/ls", tables_uri)
        except Exception:
            log.warning("HDC retrieval: fs/ls fallback failed for %s", tables_uri)
            return []

        entries = (
            raw if isinstance(raw, list)
            else raw.get("result", []) if isinstance(raw, dict)
            else []
        )
        if not entries:
            return []

        # Collect table directory names (skip files and _-prefixed dirs)
        table_dirs: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not entry.get("isDir", False):
                continue
            uri = entry.get("uri", "")
            name = uri.rstrip("/").rsplit("/", 1)[-1] if uri else ""
            if not name or name.startswith("_"):
                continue
            table_dirs.append(name)

        if not table_dirs:
            return []

        # Match: read each _INDEX.md, check if user input keywords appear
        keywords = user_input.lower().split()
        matches: list[dict] = []
        for table_name in table_dirs:
            content = await self._read_index(key, table_name)
            if not content:
                continue
            main_entity = ""
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("**"):
                    main_entity = stripped.lower()
                    break
            content_lower = content.lower()
            if any(kw in main_entity or kw in content_lower for kw in keywords):
                matches.append({"table_name": table_name, "score": 0.0})

        log.info(
            "HDC retrieval: fs fallback found %d tables for query=%s",
            len(matches), user_input[:80],
        )
        return matches

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
            for key in ("matches", "items", "data", "results", "resources", "memories", "skills"):
                val = result.get(key)
                if isinstance(val, list) and val:
                    return val
                if isinstance(val, dict) and val:
                    return [val]
        return []

    @staticmethod
    def _extract_table_name(match: dict) -> str:
        """从匹配项的 URI 中提取表名。

        URI 格式 (level=0,1 — resources 路径):
          viking://resources/hdc/{db}/_tables/{table_name}
          或 viking://resources/hdc/{db}/_tables/{table_name}/.abstract.md
        URI 格式 (level=2 — memory 路径):
          viking://user/.../memories/hdc/{key}/_tables/{table_name}/{column}.md
        URI 格式（新 — _columns/ 子目录）:
          viking://resources/hdc/{db}/_tables/{table_name}/_columns/{col}.md
          → 表名为 _columns 的父目录（parts[-3]）
        """
        uri = match.get("uri", "")
        if uri:
            parts = uri.rstrip("/").split("/")
            last = parts[-1] if parts else ""
            # _columns/ subdirectory: table is parent of _columns (parts[-3])
            if len(parts) >= 3 and parts[-2] == "_columns":
                return parts[-3]
            # Derived files (.abstract.md, .overview.md) → table is parent dir
            if last in (".abstract.md", ".overview.md", ".abstract", ".overview"):
                return parts[-2] if len(parts) >= 2 else ""
            # Column .md files (level=2) → table is parent dir
            if last.endswith(".md") and last != "_INDEX.md":
                return parts[-2] if len(parts) >= 2 else ""
            # Directory name or _INDEX.md → this is the table name
            return last.replace(".md", "")
        name = match.get("name", "")
        if name:
            if name in (".abstract", ".overview", ".abstract.md", ".overview.md"):
                return ""
            return name.replace(".md", "")
        return ""

    @staticmethod
    def _extract_column_name(match: dict) -> str:
        """从匹配项的 URI 中提取列名。

        URI 格式（新）: viking://resources/hdc/{db}/_tables/{table}/_columns/{column}.md
        URI 格式（旧）: viking://resources/hdc/{db}/_tables/{table}/{column}.md
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