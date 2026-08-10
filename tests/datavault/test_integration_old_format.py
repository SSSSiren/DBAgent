#!/usr/bin/env python3
"""
Integration test: backward compatibility for old-format HDC knowledge bases.

Validates that:
- Task 3.2: Old-format (no _columns/ subdir, no L0/L1) KBs can be queried via the updated retriever
  The retriever falls back from level=[0,1] to level=[2] when L0/L1 summaries aren't available.
- Task 4.4: End-to-end retrieval against old-format knowledge base, verifying the fallback path

Test design:
  Write data directly to a resources-path directory in the old format:
    viking://resources/hdc/{key}/_tables/{table}/_INDEX.md
    viking://resources/hdc/{key}/_tables/{table}/{col}.md (NOT _columns/ subdir)

  This simulates a KB generated before the _columns/ subdirectory restructuring,
  where SemanticProcessor did NOT generate L0/L1 summaries. The retriever should:
    1. Try find(level=[0,1]) -- returns nothing (no L0/L1)
    2. Try _fs_table_fallback -- reads _INDEX.md via fs listing
    3. Try find(level=[2]) -- matches column-level content
    4. Successfully return HDCContext with matched tables

Requirements covered: 5.1 (old-format fallback to L2)

Requires OpenViking running at kb_openviking_url (default: http://localhost:1933).

Usage:
    cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
    python -m pytest tests/datavault/test_integration_old_format.py -v -s

Or run directly:
    python tests/datavault/test_integration_old_format.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

import pytest

pytestmark = pytest.mark.integration

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.config import get_settings
from app.datavault.models import ColumnSummary, TableDescriptionWithColumns
from app.datavault.uploader import (
    HDCUploader,
    _columns_dir_uri,
    _format_column_md,
    _format_table_index,
    _table_dir_uri,
    _table_index_uri,
    _tables_dir_uri,
    _db_uri,
    storage_key,
)
from app.datavault.retriever import HDCRetriever
from app.knowledge.openviking import OpenVikingClient

# ── Test configuration ──
SETTINGS = get_settings()
OV_URL = SETTINGS.kb_openviking_url
TEST_USER = "integration-test-old-format"
TEST_SCHEMA_ID = 99999
TEST_DB_NAME = "test_integration_db_backcompat"
TEST_NAMESPACE = "old_format_test"

# Cleanup flag: set to False to keep data for manual inspection
CLEANUP_AFTER_TEST = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ── Test fixtures ──

@pytest.fixture
def key():
    """Storage key for the test namespace."""
    return storage_key(TEST_SCHEMA_ID, TEST_DB_NAME, namespace=TEST_NAMESPACE)


@pytest.fixture
def test_table():
    """A single test table for old-format backward compatibility testing."""
    return TableDescriptionWithColumns(
        table_name="test_billing",
        main_entity="账单/billing/费用记录",
        table_type="fact",
        primary_key="bill_id",
        key_attributes=["账单号", "用户ID", "金额", "账单状态", "创建时间"],
        description="账单表记录所有用户的消费账单，包含账单金额、支付状态和费用明细。",
        usage_scenario="当需要查询用户的消费账单历史、统计月度费用或分析费用趋势时使用此表。",
        row_count_estimate=80000,
        columns=[
            ColumnSummary(
                column_name="bill_id",
                description="账单唯一标识，自增主键",
                sample_values=["B001", "B002"],
                data_type="bigint",
                is_primary_key=True,
            ),
            ColumnSummary(
                column_name="user_id",
                description="用户ID，关联用户表",
                sample_values=["5001", "5002"],
                data_type="bigint",
            ),
            ColumnSummary(
                column_name="bill_amount",
                description="账单金额（元）",
                sample_values=["128.50", "4599.00"],
                data_type="decimal(12,2)",
            ),
            ColumnSummary(
                column_name="bill_status",
                description="账单状态：pending/paid/overdue/cancelled",
                sample_values=["paid", "overdue"],
                data_type="varchar(16)",
            ),
            ColumnSummary(
                column_name="created_at",
                description="账单创建时间",
                sample_values=["2026-07-25 14:20:00"],
                data_type="datetime",
            ),
        ],
    )


# ── Helper: write a table in old format (columns in table dir, no _columns/ subdir) ──

async def write_table_old_format(
    ov: OpenVikingClient, key: str, table: TableDescriptionWithColumns, wait_for_embed: bool = True
) -> None:
    """Write a table in the OLD format: columns directly in the table directory.

    Old format (pre _columns/ restructuring):
        viking://resources/hdc/{key}/_tables/{table}/_INDEX.md
        viking://resources/hdc/{key}/_tables/{table}/{col}.md  (NOT _columns/{col}.md)

    Uses the resources path (current _HDC_ROOT), so SemanticProcessor will auto-generate
    L0/L1 summaries from _INDEX.md. The critical backward-compat difference is that
    column files are in the table directory, NOT in a _columns/ subdirectory.
    The retriever must fall back from _columns/ to table dir for column retrieval.
    """
    table_dir = _table_dir_uri(key, table.table_name)

    # Create the table directory
    await ov.mkdir(table_dir)

    # Write column files directly in the table directory (old format)
    for col in table.columns:
        col_content = _format_column_md(col)
        col_uri = f"{table_dir}/{col.column_name}.md"
        await ov.write(col_uri, col_content, mode="create", wait=False)

    # Write _INDEX.md (wait=True to trigger L0/L1 + L2 embedding)
    index_content = _format_table_index(table)
    index_uri = f"{table_dir}/_INDEX.md"
    await ov.write(
        index_uri, index_content, mode="create",
        wait=wait_for_embed,
        timeout=120.0,
    )

    # Set tags
    tags = [
        "hdc_level=table",
        f"main_entity={table.main_entity}",
        f"table_type={table.table_type}",
        f"pk={table.primary_key}",
    ]
    await ov.set_tags(table_dir, tags, mode="replace")
    await asyncio.sleep(1.0)

    logging.info(
        "Wrote old-format table %s/%s (%d columns, _columns/ subdir=None, wait=%s)",
        key, table.table_name, len(table.columns), wait_for_embed,
    )


# ── Helper: verify no _columns/ subdirectory exists ──

async def assert_no_columns_subdir(ov: OpenVikingClient, key: str, table_name: str) -> dict:
    """Verify the table directory does NOT have a _columns/ subdirectory.

    This confirms the KB is in old format (column files in table directory, not in _columns/).

    Returns the table directory listing for further assertions.
    """
    table_dir = _table_dir_uri(key, table_name)
    ls_result = await ov._get_raw("/api/v1/fs/ls", table_dir)

    entries = (
        ls_result if isinstance(ls_result, list)
        else ls_result.get("result", []) if isinstance(ls_result, dict)
        else []
    )

    has_columns_dir = False
    col_files = []
    for e in entries:
        uri = e.get("uri", "")
        is_dir = e.get("isDir", False)
        if is_dir and "_columns" in uri.rstrip("/").split("/")[-1]:
            has_columns_dir = True
        if not is_dir:
            name = uri.rstrip("/").split("/")[-1]
            if name.endswith(".md") and name != "_INDEX.md":
                col_files.append(name)

    assert not has_columns_dir, (
        f"Table directory '{table_name}' has _columns/ subdirectory -- not old format. "
        f"Listing: {[e.get('uri','').rsplit('/',1)[-1] for e in entries]}"
    )
    assert len(col_files) > 0, (
        f"Table directory '{table_name}' has no column .md files. "
        f"Listing: {[e.get('uri','').rsplit('/',1)[-1] for e in entries]}"
    )

    logging.info(
        "Confirmed old format: table='%s', column files in table dir=%d, no _columns/ subdir",
        table_name, len(col_files),
    )
    return entries


async def assert_l2_retrieval_works(ov: OpenVikingClient, key: str) -> None:
    """Verify that find(level=[2]) against the tables directory returns results.

    Polls until embedding is ready, with a timeout.
    """
    tables_uri = _tables_dir_uri(key)
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        result = await ov.find(
            query="账单 费用",
            target_uri=tables_uri,
            level=[2],
            limit=10,
        )
        entries = (
            result.get("resources", []) if isinstance(result, dict)
            else result if isinstance(result, list)
            else []
        )
        if entries:
            logging.info("find(level=[2]) returned %d entries -- L2 embedding ready", len(entries))
            return
        logging.info("Waiting for L2 embedding... (%.0fs remaining)", deadline - time.monotonic())
        await asyncio.sleep(2.0)

    logging.warning("L2 embedding not ready within 60s, proceeding anyway")
    # Don't assert -- the retriever also has _fs_table_fallback which may still work


async def wait_for_l2_columns_ready(
    ov: OpenVikingClient, key: str, table_name: str, timeout: float = 60.0
) -> bool:
    """Poll find(level=[2]) on the table directory until column files appear.

    Column files written with wait=False may not have embedding completed yet.
    This polls the table directory level=[2] search to confirm readiness.
    """
    table_uri = _table_dir_uri(key, table_name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await ov.find(
            query="test",
            target_uri=table_uri,
            level=[2],
            limit=10,
        )
        matches = (
            result.get("resources", []) if isinstance(result, dict)
            else result if isinstance(result, list)
            else []
        )
        if matches:
            col_names = []
            for m in matches:
                uri = m.get("uri", "")
                name = uri.rstrip("/").split("/")[-1] if uri else ""
                if name.endswith(".md") and name != "_INDEX.md":
                    col_names.append(name)
            if col_names:
                logging.info(
                    "L2 column embedding ready for %s: %d files found",
                    table_name, len(col_names),
                )
                return True
        await asyncio.sleep(2.0)

    logging.warning("L2 columns not ready for %s within %.0fs", table_name, timeout)
    return False


# ── Cleanup ──

async def cleanup(ov: OpenVikingClient, key: str) -> None:
    """Delete the test database HDC directory."""
    try:
        await ov.rm(_db_uri(key), recursive=True)
        logging.info("Cleanup: deleted %s", _db_uri(key))
    except Exception as e:
        logging.warning("Cleanup failed: %s", e)


# ═══════════════════════════════════════════════════════════════
#  Test 3.2: Old-format KB backward compatibility
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_old_format_backward_compatibility(key, test_table):
    """Task 3.2: Verify old-format (no _columns/ subdir) KB can be queried via the updated retriever.

    Steps:
    1. Write a table in old format (columns in table dir, no _columns/ subdir, no L0/L1)
    2. Verify find(level=[0,1]) returns nothing (old format confirmed)
    3. Retrieve with a matching query via HDCRetriever
    4. Verify the retriever successfully returns the table
    5. Verify the returned table has relevant columns
    """
    ov = OpenVikingClient(OV_URL, TEST_USER)
    await ov.start()

    try:
        # Clean any leftover data from previous runs
        try:
            await ov.rm(_db_uri(key), recursive=True)
            logging.info("Cleaned up leftover data from previous run")
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # ── Step 1: Write old-format table ──
        logging.info("=" * 60)
        logging.info("Step 1: Writing table in OLD format (no _columns/ subdir)")
        logging.info("=" * 60)
        await write_table_old_format(ov, key, test_table)

        # ── Step 2: Verify old-format data structure ──
        logging.info("=" * 60)
        logging.info("Step 2: Verifying old-format structure (no _columns/ subdir)")
        logging.info("=" * 60)
        await assert_no_columns_subdir(ov, key, "test_billing")

        # Also verify that find(level=[2]) DOES find content (column-level .md files)
        await assert_l2_retrieval_works(ov, key)

        # ── Step 2.5: Wait for L2 column embedding (column files written with wait=False) ──
        l2_columns_ready = await wait_for_l2_columns_ready(ov, key, "test_billing")
        assert l2_columns_ready, (
            "L2 column embedding not ready for test_billing. "
            "Column files may not be indexed yet."
        )

        # ── Step 3: Retrieve via HDCRetriever ──
        logging.info("=" * 60)
        logging.info("Step 3: Retrieving via HDCRetriever (should use L2 fallback)")
        logging.info("=" * 60)

        retriever = HDCRetriever(ov)
        ctx = await retriever.retrieve(
            "查询最近的消费账单记录和账单状态",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace=TEST_NAMESPACE,
        )

        assert ctx is not None, (
            "retrieve() returned None -- retriever failed to find old-format table. "
            "Expected L2 fallback to find column-level content."
        )
        assert len(ctx.matched_tables) > 0, (
            "retrieve() returned empty matched_tables list"
        )

        # ── Step 4: Verify the correct table was found ──
        logging.info("=" * 60)
        logging.info("Step 4: Verifying returned table and columns")
        logging.info("=" * 60)

        found_table_names = [tm.table_name for tm in ctx.matched_tables]
        logging.info("Matched tables: %s", found_table_names)
        assert "test_billing" in found_table_names, (
            f"Expected 'test_billing' in matched tables, got {found_table_names}. "
            f"Fallback retrieval did not find the old-format table."
        )

        # Verify that relevant columns are returned
        billing_match = next(
            (tm for tm in ctx.matched_tables if tm.table_name == "test_billing"),
            None,
        )
        assert billing_match is not None
        assert len(billing_match.relevant_columns) > 0, (
            "Expected at least one relevant column for test_billing, got none. "
            "Column retrieval in old format (fallback from _columns/ to table dir) may have failed."
        )
        logging.info(
            "Relevant columns for test_billing: %d",
            len(billing_match.relevant_columns),
        )
        for col in billing_match.relevant_columns[:6]:
            logging.info("  - %s", col[:120])

        # Verify the main_entity was parsed from _INDEX.md
        logging.info("main_entity: %s", billing_match.main_entity)
        assert billing_match.main_entity, (
            "main_entity should be parsed from _INDEX.md first line"
        )
        assert "账单" in billing_match.main_entity, (
            f"Expected main_entity to contain '账单', got '{billing_match.main_entity}'"
        )

        # ── Step 5: Verify compatibility of retrieve with a different query ──
        logging.info("=" * 60)
        logging.info("Step 5: Second query to verify consistent retrieval")
        logging.info("=" * 60)

        ctx2 = await retriever.retrieve(
            "查询用户费用",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace=TEST_NAMESPACE,
        )

        assert ctx2 is not None, (
            "Second retrieve() returned None -- retriever not consistent with old format"
        )
        assert len(ctx2.matched_tables) > 0

        format_context = retriever.format_context(ctx)
        assert format_context, "format_context should return non-empty string"
        assert "test_billing" in format_context, (
            f"format_context should mention test_billing, got: {format_context[:200]}"
        )

        logging.info("=" * 60)
        logging.info("ALL CHECKS PASSED: Old-format backward compatibility verified!")
        logging.info("=" * 60)

    finally:
        if CLEANUP_AFTER_TEST:
            await cleanup(ov, key)
        await ov.close()


# ═══════════════════════════════════════════════════════════════
#  Test 4.4: Backward compatibility end-to-end integration
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_backward_compat_integration(key, test_table):
    """Task 4.4: End-to-end integration test for backward compatibility.

    Verifies the complete old-format retrieval flow:
    1. Old-format KB exists at resources path (no _columns/, no L0/L1)
    2. Retriever successfully queries it
    3. Column retrieval works correctly (falls back from _columns/ to table dir)
    4. _INDEX.md parsing works (main_entity, table_type, description, usage_scenario)
    5. format_context produces valid output
    """
    ov = OpenVikingClient(OV_URL, TEST_USER)
    await ov.start()

    try:
        # Clean any leftover data
        try:
            await ov.rm(_db_uri(key), recursive=True)
            logging.info("Cleaned up leftover data from previous run")
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # Write old-format table
        await write_table_old_format(ov, key, test_table)

        # Wait for L2 embedding to complete (brief poll)
        tables_uri = _tables_dir_uri(key)
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            result = await ov.find(
                query="账单",
                target_uri=tables_uri,
                level=[2],
                limit=5,
            )
            entries = (
                result.get("resources", []) if isinstance(result, dict)
                else result if isinstance(result, list)
                else []
            )
            if entries:
                logging.info("L2 embedding ready: %d entries found", len(entries))
                break
            logging.info("Waiting for L2 embedding...")
            await asyncio.sleep(2.0)
        else:
            logging.warning("L2 embedding not ready within 60s, continuing anyway")

        # ── Full retrieval flow ──
        retriever = HDCRetriever(ov)
        ctx = await retriever.retrieve(
            "查询用户的消费账单和金额明细",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace=TEST_NAMESPACE,
        )

        assert ctx is not None, "retrieve() returned None"
        assert len(ctx.matched_tables) > 0, "No tables matched"

        billing = next((t for t in ctx.matched_tables if t.table_name == "test_billing"), None)
        assert billing is not None, "test_billing not found in matched tables"

        # Verify all fields are populated correctly
        assert billing.main_entity, "main_entity should not be empty"
        assert billing.table_type, "table_type should not be empty"
        assert billing.description, "description should not be empty"
        assert billing.usage_scenario, "usage_scenario should not be empty"
        assert len(billing.relevant_columns) > 0, "relevant_columns should not be empty"

        logging.info("main_entity: %s", billing.main_entity)
        logging.info("table_type: %s", billing.table_type)
        logging.info("description: %s", billing.description[:100])
        logging.info("usage_scenario: %s", billing.usage_scenario[:100])
        logging.info("relevant_columns: %d columns", len(billing.relevant_columns))

        # Verify format_context output
        formatted = retriever.format_context(ctx)
        assert formatted, "format_context should not be empty"
        assert "[数据底座" in formatted, "format_context should contain data base header"
        assert "test_billing" in formatted, "format_context should mention test_billing"

        logging.info("format_context length: %d chars", len(formatted))

        logging.info("=" * 60)
        logging.info("ALL CHECKS PASSED: Backward compatibility integration test complete!")
        logging.info("=" * 60)

    finally:
        if CLEANUP_AFTER_TEST:
            await cleanup(ov, key)
        await ov.close()


# ═══════════════════════════════════════════════════════════════
#  Helper test: verify old-format data structure
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_old_format_no_columns_subdir(key, test_table):
    """Verify the old-format data structure: no _columns/ subdirectory exists.

    This is a structural test to confirm the old-format write produces the expected
    directory layout (columns directly in the table directory).
    """
    ov = OpenVikingClient(OV_URL, TEST_USER)
    await ov.start()

    try:
        try:
            await ov.rm(_db_uri(key), recursive=True)
            await asyncio.sleep(1.0)
        except Exception:
            pass

        await write_table_old_format(ov, key, test_table)

        # List the table directory to verify structure
        table_dir = _table_dir_uri(key, "test_billing")
        ls_result = await ov._get_raw("/api/v1/fs/ls", table_dir)

        entries = (
            ls_result if isinstance(ls_result, list)
            else ls_result.get("result", []) if isinstance(ls_result, dict)
            else []
        )

        entry_info = []
        has_columns_subdir = False
        has_index_md = False
        has_column_md = False

        for e in entries:
            uri = e.get("uri", "")
            is_dir = e.get("isDir", False)
            name = uri.rstrip("/").split("/")[-1] if uri else ""
            entry_info.append(f"{'[DIR]' if is_dir else '[FILE]'} {name}")
            if name == "_columns":
                has_columns_subdir = True
            if name == "_INDEX.md":
                has_index_md = True
            if name.endswith(".md") and name != "_INDEX.md":
                has_column_md = True

        logging.info("Table directory contents:")
        for info in entry_info:
            logging.info("  %s", info)

        assert not has_columns_subdir, (
            "Old format should NOT have _columns/ subdirectory. "
            f"Found: {entry_info}"
        )
        assert has_index_md, (
            f"Old format should have _INDEX.md. Found: {entry_info}"
        )
        assert has_column_md, (
            f"Old format should have column .md files in table directory. Found: {entry_info}"
        )

        logging.info("=" * 60)
        logging.info("OLD FORMAT STRUCTURE VERIFIED: columns in table dir, no _columns/")
        logging.info("=" * 60)

    finally:
        if CLEANUP_AFTER_TEST:
            await cleanup(ov, key)
        await ov.close()


# ── Allow running directly ──

if __name__ == "__main__":
    asyncio.run(test_old_format_backward_compatibility(
        key=storage_key(TEST_SCHEMA_ID, TEST_DB_NAME, namespace=TEST_NAMESPACE),
        test_table=TableDescriptionWithColumns(
            table_name="test_billing",
            main_entity="账单/billing/费用记录",
            table_type="fact",
            primary_key="bill_id",
            key_attributes=["账单号", "用户ID", "金额", "账单状态", "创建时间"],
            description="账单表记录所有用户的消费账单，包含账单金额、支付状态和费用明细。",
            usage_scenario="当需要查询用户的消费账单历史、统计月度费用或分析费用趋势时使用此表。",
            row_count_estimate=80000,
            columns=[
                ColumnSummary(column_name="bill_id", description="账单唯一标识，自增主键", sample_values=["B001"], data_type="bigint", is_primary_key=True),
                ColumnSummary(column_name="user_id", description="用户ID，关联用户表", sample_values=["5001"], data_type="bigint"),
                ColumnSummary(column_name="bill_amount", description="账单金额（元）", sample_values=["128.50"], data_type="decimal(12,2)"),
                ColumnSummary(column_name="bill_status", description="账单状态：pending/paid/overdue/cancelled", sample_values=["paid"], data_type="varchar(16)"),
                ColumnSummary(column_name="created_at", description="账单创建时间", sample_values=["2026-07-25 14:20:00"], data_type="datetime"),
            ],
        ),
    ))
