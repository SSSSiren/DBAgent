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
        self, database_name: str
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

        tables_dir = _tables_dir_uri(database_name)

        # List entries in the _tables directory
        try:
            entries = await self._uploader._ov._get_raw(
                "/api/v1/fs/ls", tables_dir
            )
        except Exception:
            log.debug(
                "HDCUpdater: cannot list _tables directory for '%s' "
                "(may not exist yet)",
                database_name,
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

            table_name = entry.get("name", "")
            if not table_name:
                continue

            existing_names.add(table_name)

            # Read the table directory's attributes to extract tags
            table_dir = _table_dir_uri(database_name, table_name)
            try:
                detail = await self._uploader._ov._get_raw(
                    "/api/v1/fs/read", table_dir
                )
            except Exception:
                log.debug(
                    "HDCUpdater: cannot read attrs for %s", table_dir
                )
                continue

            if not isinstance(detail, dict):
                continue

            tags = detail.get("tags", [])
            if not isinstance(tags, list):
                tags = []

            for tag in tags:
                if isinstance(tag, str) and tag.startswith("columns_hash:"):
                    stored_hashes[table_name] = tag[len("columns_hash:"):]
                    break

        return stored_hashes, existing_names

    async def _store_hash(
        self, database_name: str, table_name: str, hash_value: str
    ) -> None:
        """Store the column hash as a ``columns_hash:...`` tag on the table directory.

        Uses ``mode="merge"`` so that existing tags (hdc_level, main_entity, etc.)
        are preserved.
        """
        from app.datavault.uploader import _table_dir_uri

        table_dir = _table_dir_uri(database_name, table_name)
        try:
            await self._uploader._ov.set_tags(
                table_dir,
                [f"columns_hash:{hash_value}"],
                mode="merge",
            )
        except Exception:
            log.warning(
                "HDCUpdater: failed to store hash for %s.%s",
                database_name,
                table_name,
                exc_info=True,
            )

    # ── Main entry point ──────────────────────────────────────────

    async def check_and_update(
        self, schema_id: int, database_name: str
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
            database_name: Database name used in OpenViking URIs.

        Returns:
            ``{"changed": False}`` when no schema changes are detected.
            ``{"changed": True, "new": N, "changed_tables": N, "deleted": N}``
            when changes are detected and processed.

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
        """
        # ── 1. Collect current schema ──
        db_raw = await self._collector.collect_database(schema_id)
        current_tables: dict[str, Any] = {
            t.name: t for t in db_raw.tables
        }

        # ── 2. Compute current hashes ──
        current_hashes: dict[str, str] = {}
        for name, table in current_tables.items():
            current_hashes[name] = self._compute_columns_hash(table.columns)

        # ── 3. Read stored state from OpenViking ──
        stored_hashes, existing_tables = await self._get_stored_state(
            database_name
        )

        # ── 4. Compare: identify new, changed, deleted ──
        new_tables: list[str] = []
        changed_tables: list[str] = []
        needs_hash_store: list[str] = []  # tables that exist but lack a hash tag

        for name, current_hash in current_hashes.items():
            if name not in existing_tables:
                # Table directory does not exist in OpenViking → truly new
                new_tables.append(name)
            elif name not in stored_hashes:
                # Table directory exists but no columns_hash tag yet
                # (e.g. after initial generation via HDCGenerator.generate())
                needs_hash_store.append(name)
            elif current_hash != stored_hashes[name]:
                changed_tables.append(name)

        deleted_tables: list[str] = [
            name for name in stored_hashes if name not in current_hashes
        ]
        # Also consider tables that exist in OpenViking but not in current schema
        # (even without a hash tag)
        for name in existing_tables:
            if name not in current_hashes and name not in deleted_tables:
                deleted_tables.append(name)

        # ── 5. No changes: return early (zero LLM calls) ──
        # Store hashes for any existing tables that lack them (no-op for change detection)
        for name in needs_hash_store:
            await self._store_hash(database_name, name, current_hashes[name])

        if not new_tables and not changed_tables and not deleted_tables:
            log.info(
                "HDCUpdater: no schema changes detected for '%s'",
                database_name,
            )
            return {"changed": False}

        log.info(
            "HDCUpdater: detected changes for '%s' — "
            "new=%d, changed=%d, deleted=%d",
            database_name,
            len(new_tables),
            len(changed_tables),
            len(deleted_tables),
        )

        # ── 6. Re-generate new/changed tables ──
        regenerated_descriptions: dict[str, TableDescription] = {}
        regenerated_with_cols: list[TableDescriptionWithColumns] = []
        all_column_summaries: dict[str, list[ColumnSummary]] = {}
        errors: list[str] = []

        for table_name in new_tables + changed_tables:
            table_raw = current_tables[table_name]
            try:
                # Generate column summaries for this table
                col_map = await self._generator.generate_column_summaries(
                    [table_raw]
                )
                summaries = col_map.get(table_name, [])

                # Generate table description
                desc = await self._generator._generate_one_table_description(
                    table_raw, summaries
                )
                if desc is None:
                    error_msg = (
                        f"Table description generation failed for '{table_name}'"
                    )
                    log.error("HDCUpdater: %s", error_msg)
                    errors.append(error_msg)
                    continue

                regenerated_descriptions[table_name] = desc

                # Build TableDescriptionWithColumns for upload
                twc = TableDescriptionWithColumns(
                    table_name=desc.table_name,
                    main_entity=desc.main_entity,
                    table_type=desc.table_type,
                    primary_key=desc.primary_key,
                    key_attributes=desc.key_attributes,
                    description=desc.description,
                    row_count_estimate=desc.row_count_estimate,
                    columns=summaries,
                )
                regenerated_with_cols.append(twc)
                all_column_summaries[table_name] = summaries

                # Upload to OpenViking
                await self._uploader.upload_table(database_name, twc)

                # Store the new hash
                await self._store_hash(
                    database_name, table_name, current_hashes[table_name]
                )

                log.info(
                    "HDCUpdater: regenerated table '%s.%s'",
                    database_name,
                    table_name,
                )
            except Exception as e:
                error_msg = f"Failed to regenerate table '{table_name}': {e}"
                log.error("HDCUpdater: %s", error_msg)
                errors.append(error_msg)

        # ── 7. Delete removed tables ──
        for table_name in deleted_tables:
            try:
                await self._uploader.delete_table(database_name, table_name)
                log.info(
                    "HDCUpdater: deleted table '%s.%s'",
                    database_name,
                    table_name,
                )
            except Exception as e:
                error_msg = f"Failed to delete table '{table_name}': {e}"
                log.error("HDCUpdater: %s", error_msg)
                errors.append(error_msg)

        # ── 8. Cascade: regenerate relationships and database summary ──
        # Build the full set of table descriptions (regenerated + unchanged)
        all_descriptions: list[TableDescription] = list(
            regenerated_descriptions.values()
        )

        for name, table_raw in current_tables.items():
            if name in deleted_tables:
                continue
            if name in regenerated_descriptions:
                continue
            # Unchanged table: create a minimal TableDescription from raw data
            desc = TableDescription(
                table_name=name,
                main_entity=table_raw.comment or name,
                table_type="fact",
                primary_key="",
                key_attributes=[],
                description=table_raw.comment or "",
                row_count_estimate=table_raw.row_count_estimate,
            )
            all_descriptions.append(desc)

        # Generate relationships using the full set
        relationships = []
        try:
            relationships = await self._generator.generate_relationships(
                database_name, all_descriptions, all_column_summaries,
            )
        except Exception as e:
            error_msg = f"Relationship regeneration failed: {e}"
            log.error("HDCUpdater: %s", error_msg)
            errors.append(error_msg)

        # Generate database summary
        db_summary = None
        try:
            db_summary = await self._generator.generate_database_summary(
                database_name, all_descriptions, relationships,
            )
        except Exception as e:
            error_msg = f"Database summary regeneration failed: {e}"
            log.error("HDCUpdater: %s", error_msg)
            errors.append(error_msg)

        # Upload cascade results (database summary + relationships only;
        # individual tables were already uploaded above)
        if db_summary is not None:
            from app.datavault.uploader import (
                _db_uri,
                _format_database_index,
                _format_relationship_md,
                _relations_dir_uri,
            )

            try:
                # Write database _INDEX.md
                db_index_content = _format_database_index(db_summary)
                db_index_uri = f"{_db_uri(database_name)}/_INDEX.md"
                await self._uploader._ov.write(
                    db_index_uri, db_index_content, mode="replace", wait=True
                )

                # Write relationship files
                for rel in relationships:
                    rel_content = _format_relationship_md(rel)
                    rel_uri = (
                        f"{_relations_dir_uri(database_name)}/"
                        f"{rel.source_table}__{rel.target_table}.md"
                    )
                    await self._uploader._ov.write(
                        rel_uri, rel_content, mode="replace", wait=False
                    )
            except Exception as e:
                error_msg = f"Cascade upload failed: {e}"
                log.error("HDCUpdater: %s", error_msg)
                errors.append(error_msg)

        if errors:
            log.warning(
                "HDCUpdater: update completed with %d error(s) for '%s'",
                len(errors),
                database_name,
            )

        return {
            "changed": True,
            "new": len(new_tables),
            "changed_tables": len(changed_tables),
            "deleted": len(deleted_tables),
        }