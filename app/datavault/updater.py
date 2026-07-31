"""
HDCUpdater — Schema change detection and incremental regeneration.

Detects schema changes via column signature hash comparison, triggers
selective re-generation of changed tables, and cascades to relationship
and database summary regeneration.

Requirements: 3.1 (column signature hash comparison), 3.2 (re-generate only
changed/new tables), 3.3 (delete removed tables from OpenViking),
3.4 (cascade to relationships and database summary), 3.5 (no changes → no LLM calls).
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from app.datavault.models import (
    ColumnRaw,
    ColumnSummary,
    TableDescription,
    TableDescriptionWithColumns,
)
from app.datavault.uploader import storage_key

if TYPE_CHECKING:
    from app.datavault.collector import SchemaCollector
    from app.datavault.generator import HDCGenerator
    from app.datavault.uploader import HDCUploader

log = logging.getLogger(__name__)


class HDCUpdater:
    """Detect schema changes and perform incremental HDC regeneration.

    Workflow:
      1. Collect current schema from OneDBA
      2. Compute column signature hashes (column name + type) for each table
      3. Read stored hashes from OpenViking table tags
      4. Compare: identify new, changed, and deleted tables
      5. If no changes: return {"changed": False} — zero LLM calls
      6. Re-generate new/changed tables (column summaries + table description)
      7. Delete removed tables from OpenViking
      8. Cascade: re-generate relationships and database summary for the full set

    Contract: Service
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """

    def __init__(
        self,
        collector: "SchemaCollector",
        generator: "HDCGenerator",
        uploader: "HDCUploader",
    ) -> None:
        self._collector = collector
        self._generator = generator
        self._uploader = uploader

    # ── Hash computation ──────────────────────────────────────────

    @staticmethod
    def _compute_columns_hash(columns: list[ColumnRaw]) -> str:
        """Compute a deterministic SHA-256 hash of column names and types.

        Columns are sorted by name for stable ordering so that reordered
        columns produce the same hash.

        Requirement 3.1: Column signature hash comparison (column name + type).
        """
        sorted_cols = sorted(columns, key=lambda c: c.name)
        signature = ",".join(f"{c.name}:{c.data_type}" for c in sorted_cols)
        return hashlib.sha256(signature.encode("utf-8")).hexdigest()

    # ── OpenViking state read/write ───────────────────────────────

    async def _get_stored_state(
        self, key: str
    ) -> tuple[dict[str, str], set[str]]:
        """Read stored column hashes and existing table names from OpenViking.

        Lists the _tables directory via the OpenViking fs/ls API, then reads
        each table directory's tags to extract the ``columns_hash:...`` value.

        Returns:
            Tuple of (stored_hashes, existing_table_names).
            - stored_hashes: dict mapping table_name -> stored columns_hash
            - existing_table_names: set of table names that have directories
              in OpenViking (with or without a hash tag)
        """
        from app.datavault.uploader import _table_dir_uri, _tables_dir_uri

        tables_dir = _tables_dir_uri(key)

        # List entries in the _tables directory
        try:
            entries = await self._uploader._ov._get_raw(
                "/api/v1/fs/ls", tables_dir
            )
        except Exception:
            log.debug(
                "HDCUpdater: cannot list _tables directory for '%s' "
                "(may not exist yet)",
                key,
            )
            return {}, set()

        if not isinstance(entries, list):
            entries = []

        stored_hashes: dict[str, str] = {}
        existing_names: set[str] = set()

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Only consider directories (table dirs)
            if not entry.get("isDir", False):
                continue

            # OpenViking fs/ls via _get_raw returns entries with 'uri' but not 'name'.
            table_name = (entry.get("name") or "").strip()
            if not table_name:
                uri = entry.get("uri", "")
                table_name = uri.rstrip("/").split("/")[-1] if uri else ""
            if not table_name:
                continue

            existing_names.add(table_name)

            # Read the _INDEX.md file's attributes to extract tags
            # (OpenViking persists tags only on files, not directories)
            table_dir = _table_dir_uri(key, table_name)
            index_uri = f"{table_dir}/_INDEX.md"
            try:
                detail = await self._uploader._ov._get_raw(
                    "/api/v1/fs/attrs", index_uri
                )
            except Exception:
                log.debug(
                    "HDCUpdater: cannot read attrs for %s", index_uri
                )
                continue

            if not isinstance(detail, dict):
                continue

            # fs/attrs returns {"uri": ..., "attrs": {"tags": [...]}}
            attrs = detail.get("attrs", {})
            tags = attrs.get("tags", []) if isinstance(attrs, dict) else []
            if not isinstance(tags, list):
                tags = []

            for tag in tags:
                if isinstance(tag, str) and tag.startswith("columns_hash="):
                    stored_hashes[table_name] = tag[len("columns_hash="):]
                    break

        return stored_hashes, existing_names

    async def _store_hash(
        self, key: str, table_name: str, hash_value: str
    ) -> None:
        """Store the column hash as a ``columns_hash:...`` tag on the table's _INDEX.md file.

        Uses ``mode="append"`` so that existing tags are preserved.
        Tags must be set on a file (not a directory) — OpenViking ignores
        set_tags calls on directory URIs.
        """
        from app.datavault.uploader import _table_dir_uri

        table_dir = _table_dir_uri(key, table_name)
        index_uri = f"{table_dir}/_INDEX.md"
        try:
            await self._uploader._ov.set_tags(
                index_uri,
                [f"columns_hash={hash_value}"],
                mode="append",
            )
        except Exception:
            log.warning(
                "HDCUpdater: failed to store hash for %s/%s",
                key,
                table_name,
                exc_info=True,
            )

    # ── Main entry point ──────────────────────────────────────────

    async def check_and_update(
        self,
        schema_id: int,
        database_name: str,
        tables: list[str] | None = None,
        namespace: str | None = None,
        dry_run: bool = False,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        """Check for schema changes and perform incremental updates.

        Workflow:
        1. Collect current schema from OneDBA
        2. Compute column signature hashes for each table
        3. Read stored hashes from OpenViking
        4. Compare: identify new, changed, and deleted tables
        5. If no changes: return ``{"changed": False}`` (zero LLM calls)
        6. Re-generate new/changed tables (column summaries + table description)
        7. Delete removed tables from OpenViking
        8. Cascade: re-generate relationships and database summary
        9. Return change summary

        Args:
            schema_id: OneDBA schema ID.
            database_name: Database name.
            tables: Optional target table names. None checks all tables;
                a list limits change detection to only those tables.
            namespace: Optional HDC namespace variant.
                When set, operates on the isolated directory.
            dry_run: When True, only detect and report changes without
                performing any regeneration or deletion. The returned
                summary still describes what *would* change.
            rebuild: When True, treat every existing table as "changed",
                forcing full regeneration of column summaries and table
                descriptions. Bypasses hash comparison.

        Returns:
            ``{"changed": False}`` when no schema changes are detected.
            ``{"changed": True, "new": N, "changed_tables": N, "deleted": N}``
            when changes are detected and processed.

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 1.11, 1.12
        """
        key = storage_key(schema_id, database_name, namespace=namespace)

        # ── 1. Collect current schema ──
        db_raw = await self._collector.collect_database(schema_id, tables=tables)
        current_tables: dict[str, Any] = {
            t.name: t for t in db_raw.tables
        }

        # ── Filter: only check specified tables when tables param is provided ──
        if tables is not None:
            table_set = set(tables)
            for t in tables:
                if t not in current_tables:
                    log.warning(
                        "HDCUpdater: table '%s' not found in schema_id=%d, skipped",
                        t, schema_id,
                    )
            current_tables = {
                name: tbl for name, tbl in current_tables.items()
                if name in table_set
            }

        # ── 2. Compute current hashes ──
        current_hashes: dict[str, str] = {}
        for name, table in current_tables.items():
            current_hashes[name] = self._compute_columns_hash(table.columns)

        # ── 3. Read stored state from OpenViking ──
        stored_hashes, existing_tables = await self._get_stored_state(key)

        # ── 4. Compare: identify new, changed, deleted ──
        new_tables: list[str] = []
        changed_tables: list[str] = []
        needs_hash_store: list[str] = []

        for name, current_hash in current_hashes.items():
            if name not in existing_tables:
                new_tables.append(name)
            elif name not in stored_hashes:
                needs_hash_store.append(name)
            elif current_hash != stored_hashes[name]:
                changed_tables.append(name)

        deleted_tables: list[str] = [
            name for name in stored_hashes if name not in current_hashes
        ]
        for name in existing_tables:
            if name not in current_hashes and name not in deleted_tables:
                deleted_tables.append(name)

        # ── 5. No changes: return early (zero LLM calls) ──
        for name in needs_hash_store:
            await self._store_hash(key, name, current_hashes[name])

        # rebuild 模式：强制把所有已知表标记为 changed，触发全量重算
        if rebuild:
            changed_tables = [name for name in current_tables if name in existing_tables]
            new_tables = [name for name in current_tables if name not in existing_tables]
            log.info(
                "HDCUpdater: rebuild mode for '%s' — forcing regeneration of %d table(s)",
                key, len(new_tables) + len(changed_tables),
            )

        # dry_run 模式：只报告变更，不执行任何重算/删除
        if dry_run:
            log.info(
                "HDCUpdater: dry-run for '%s' — new=%d, changed=%d, deleted=%d (no changes applied)",
                key, len(new_tables), len(changed_tables), len(deleted_tables),
            )
            return {
                "changed": bool(new_tables or changed_tables or deleted_tables),
                "dry_run": True,
                "new": len(new_tables),
                "changed_tables": len(changed_tables),
                "deleted": len(deleted_tables),
                "new_tables": new_tables,
                "changed_table_names": changed_tables,
                "deleted_tables": deleted_tables,
            }

        if not new_tables and not changed_tables and not deleted_tables:
            log.info("HDCUpdater: no schema changes detected for '%s'", key)
            return {"changed": False}

        log.info(
            "HDCUpdater: detected changes for '%s' — new=%d, changed=%d, deleted=%d",
            key, len(new_tables), len(changed_tables), len(deleted_tables),
        )

        # ── 6-8. Re-generate + cascade (same logic as before) ──
        regenerated_descriptions: dict[str, TableDescription] = {}
        all_column_summaries: dict[str, list[ColumnSummary]] = {}
        errors: list[str] = []

        for table_name in new_tables + changed_tables:
            table_raw = current_tables[table_name]
            try:
                col_map = await self._generator.generate_column_summaries([table_raw])
                summaries = col_map.get(table_name, [])
                desc = await self._generator._generate_one_table_description(table_raw, summaries)
                if desc is None:
                    errors.append(f"Table description generation failed for '{table_name}'")
                    continue
                regenerated_descriptions[table_name] = desc
                twc = TableDescriptionWithColumns(
                    table_name=desc.table_name, main_entity=desc.main_entity,
                    table_type=desc.table_type, primary_key=desc.primary_key,
                    key_attributes=desc.key_attributes, description=desc.description,
                    usage_scenario=desc.usage_scenario, row_count_estimate=desc.row_count_estimate,
                    columns=summaries,
                )
                await self._uploader.upload_table(key, twc)
                await self._store_hash(key, table_name, current_hashes[table_name])
                all_column_summaries[table_name] = summaries
                log.info("HDCUpdater: regenerated table '%s/%s'", key, table_name)
            except Exception as e:
                errors.append(f"Failed to regenerate table '{table_name}': {e}")

        for table_name in deleted_tables:
            try:
                await self._uploader.delete_table(key, table_name)
            except Exception as e:
                errors.append(f"Failed to delete table '{table_name}': {e}")

        all_descriptions: list[TableDescription] = list(regenerated_descriptions.values())
        for name, table_raw in current_tables.items():
            if name in deleted_tables or name in regenerated_descriptions:
                continue
            all_descriptions.append(TableDescription(
                table_name=name, main_entity=table_raw.comment or name,
                table_type="fact", primary_key="", key_attributes=[],
                description=table_raw.comment or "",
                row_count_estimate=table_raw.row_count_estimate,
            ))

        # Skip table relationships (O(N²) cost, not used in online retrieval)
        relationships: list[TableRelationship] = []

        db_summary = None
        try:
            db_summary = await self._generator.generate_database_summary(
                database_name, all_descriptions, relationships)
        except Exception as e:
            errors.append(f"Database summary regeneration failed: {e}")

        if db_summary is not None:
            try:
                await self._uploader.upload_cascade(key, db_summary, relationships)
            except Exception as e:
                errors.append(f"Cascade upload failed: {e}")

        if errors:
            log.warning("HDCUpdater: update completed with %d error(s) for '%s'", len(errors), key)

        return {
            "changed": True,
            "new": len(new_tables),
            "changed_tables": len(changed_tables),
            "deleted": len(deleted_tables),
        }

    async def rebuild_relationships(
        self, schema_id: int, database_name: str,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Force-rebuild relationships and database summary without touching tables.

        Use case: After fixing a bug that caused relationship detection failures
        (e.g. LLM connection exhaustion), rebuild relationships and database
        summary from existing table data in OpenViking.

        This method does NOT regenerate column summaries or table descriptions.
        It reads table tags (main_entity, table_type, pk) from OpenViking and
        column names/types from OneDBA, then runs relationship detection and
        database summary generation.

        Args:
            namespace: Optional HDC namespace variant.
                When set, operates on the isolated directory.

        Returns:
            {"relationships": N, "duration_seconds": float} on success.
        """
        import time as _time
        from app.datavault.uploader import _tables_dir_uri, _table_dir_uri

        key = storage_key(schema_id, database_name, namespace=namespace)
        start_time = _time.monotonic()

        # ── 1. Collect current schema from OneDBA ──
        db_raw = await self._collector.collect_database(schema_id, tables=tables)
        current_tables: dict[str, Any] = {
            t.name: t for t in db_raw.tables
        }

        # ── 2. Read table tags from OpenViking ──
        tables_dir = _tables_dir_uri(key)
        try:
            entries = await self._uploader._ov._get_raw(
                "/api/v1/fs/ls", tables_dir
            )
        except Exception:
            log.warning(
                "HDCUpdater: cannot list _tables directory for '%s'", key
            )
            return {"relationships": 0, "duration_seconds": 0}

        if not isinstance(entries, list):
            entries = []

        # Build TableDescription + ColumnSummary from OpenViking tags + OneDBA raw
        all_descriptions: list[TableDescription] = []
        all_column_summaries: dict[str, list[ColumnSummary]] = {}

        for entry in (entries or []):
            if not isinstance(entry, dict):
                continue
            if not entry.get("isDir", False):
                continue

            # OpenViking fs/ls via _get_raw returns entries with 'uri' but not 'name'.
            # Extract table name from the last segment of the URI path.
            table_name = (entry.get("name") or "").strip()
            if not table_name:
                uri = entry.get("uri", "")
                table_name = uri.rstrip("/").split("/")[-1] if uri else ""
            if not table_name:
                continue

            # Read tags from OpenViking table directory
            table_dir = _table_dir_uri(key, table_name)
            main_entity = table_name
            table_type = "fact"
            primary_key = ""

            try:
                detail = await self._uploader._ov._get_raw(
                    "/api/v1/fs/attrs", table_dir
                )
                if isinstance(detail, dict):
                    # fs/attrs returns {"uri": ..., "attrs": {"tags": [...]}}
                    attrs = detail.get("attrs", {})
                    tags_raw = attrs.get("tags", []) if isinstance(attrs, dict) else []
                    tags: list[str] = tags_raw if isinstance(tags_raw, list) else []
                    for tag in tags:
                        if not isinstance(tag, str):
                            continue
                        if tag.startswith("main_entity="):
                            main_entity = tag[len("main_entity="):]
                        elif tag.startswith("table_type="):
                            table_type = tag[len("table_type="):]
                        elif tag.startswith("pk="):
                            primary_key = tag[len("pk="):]
            except Exception:
                log.debug("HDCUpdater: cannot read tags for %s", table_dir)

            # Build TableDescription from tags
            desc = TableDescription(
                table_name=table_name,
                main_entity=main_entity,
                table_type=table_type,  # type: ignore[arg-type]
                primary_key=primary_key,
                key_attributes=[],
                description="",
                usage_scenario="",
            )
            all_descriptions.append(desc)

            # Build ColumnSummary from OneDBA raw schema
            table_raw = current_tables.get(table_name)
            if table_raw:
                summaries: list[ColumnSummary] = []
                for col in table_raw.columns:
                    summaries.append(ColumnSummary(
                        column_name=col.name,
                        description="",
                        data_type=col.data_type,
                        nullable=col.nullable,
                        is_primary_key=(col.key == "PRI"),
                    ))
                all_column_summaries[table_name] = summaries

        if not all_descriptions:
            log.warning("HDCUpdater: no tables found in OpenViking for '%s'", key)
            return {"relationships": 0, "duration_seconds": 0}

        log.info(
            "HDCUpdater: rebuilding relationships for %d tables in '%s'",
            len(all_descriptions), key,
        )

        # ── 2.5 Write _tables/_INDEX.md to trigger SemanticProcessor L0/L1 ──
        # find() searches _tables/ directory level (non-recursive), so we need
        # _tables/.abstract.md and .overview.md for tags-based vector search to work.
        # Without this, every table shows "回退" (local heuristic) instead of "OV".
        from app.datavault.uploader import _format_tables_index, _tables_dir_uri
        from app.datavault.models import TableDescriptionWithColumns
        tables_for_index: list[TableDescriptionWithColumns] = []
        for td in all_descriptions:
            tables_for_index.append(TableDescriptionWithColumns(
                table_name=td.table_name,
                main_entity=td.main_entity,
                table_type=td.table_type,
                primary_key=td.primary_key,
                key_attributes=td.key_attributes,
                description=td.description,
                usage_scenario=td.usage_scenario,
                row_count_estimate=td.row_count_estimate,
                columns=all_column_summaries.get(td.table_name, []),
            ))
        tables_dir = _tables_dir_uri(key)
        tables_index = _format_tables_index(tables_for_index)
        try:
            await self._uploader._ov.write(
                f"{tables_dir}/_INDEX.md", tables_index,
                mode="replace", wait=False,  # 377表文档 VLM 处理 >300s，不阻塞
            )
        except Exception:
            log.warning(
                "HDCUpdater: failed to write _tables/_INDEX.md for '%s'", key, exc_info=True
            )

        # ── 3. Regenerate relationships ──
        # Skip table relationships (O(N²) cost, not used in online retrieval)
        relationships: list[TableRelationship] = []
        errors: list[str] = []

        if progress_callback:
            progress_callback("rebuild_relationships", {
                "phase": 4, "phase_label": "检测表关系",
                "status": "skipped", "count": 0,
            })

        # ── 4. Regenerate database summary ──
        db_summary = None

        if progress_callback:
            progress_callback("rebuild_db_summary", {
                "phase": 5, "phase_label": "生成数据库摘要",
                "status": "running",
            })

        try:
            db_summary = await self._generator.generate_database_summary(
                database_name, all_descriptions, relationships,
            )
        except Exception as e:
            error_msg = f"Database summary regeneration failed during rebuild: {e}"
            log.error("HDCUpdater: %s", error_msg)
            errors.append(error_msg)

        if progress_callback:
            progress_callback("rebuild_db_summary", {
                "phase": 5, "phase_label": "生成数据库摘要",
                "status": "done",
                "domain_hint": db_summary.domain_hint if db_summary else "",
            })

        # ── 5. Upload cascade results ──
        if db_summary is not None:
            if progress_callback:
                progress_callback("rebuild_upload", {
                    "phase": 6, "phase_label": "上传摘要和关系",
                    "status": "running",
                    "relationships": len(relationships),
                })
            try:
                await self._uploader.upload_cascade(key, db_summary, relationships)
            except Exception as e:
                error_msg = f"Cascade upload failed during rebuild: {e}"
                log.error("HDCUpdater: %s", error_msg)
                errors.append(error_msg)
            if progress_callback:
                progress_callback("rebuild_upload", {
                    "phase": 6, "phase_label": "上传摘要和关系",
                    "status": "done",
                })

        duration = _time.monotonic() - start_time
        result = {
            "relationships": len(relationships),
            "duration_seconds": round(duration, 2),
        }
        if errors:
            result["errors"] = errors

        log.info(
            "HDCUpdater: rebuild_relationships complete — %d relationships in %.2fs",
            len(relationships), duration,
        )
        return result

