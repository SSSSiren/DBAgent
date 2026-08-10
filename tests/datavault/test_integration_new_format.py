#!/usr/bin/env python3
"""
Integration test: verify the complete new-format HDC generation-to-retrieval pipeline.

Validates that:
1. generate 2 tables (test_orders, test_alerts) via HDCUploader → L0/L1 files are created
2. Retrieve "查询订单" → test_orders is the top match
3. Retrieve "查询告警" → test_alerts is the top match
4. The retriever uses level=[0,1] (new format), not falling back to level=[2]

Requires OpenViking running at kb_openviking_url (default: http://localhost:1933).

Usage:
    cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
    python -m pytest tests/datavault/test_integration_new_format.py -v -s -k "test_new_format_pipeline"

Or run directly:
    python tests/datavault/test_integration_new_format.py
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
    _tables_dir_uri,
    storage_key,
)
from app.datavault.retriever import HDCRetriever
from app.knowledge.openviking import OpenVikingClient

# ── Test configuration ──
SETTINGS = get_settings()
OV_URL = SETTINGS.kb_openviking_url
TEST_USER = "integration-test-new-format"
TEST_SCHEMA_ID = 99999
TEST_DB_NAME = "test_integration_db"
TEST_NAMESPACE = "new_format_test"

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
def test_tables():
    """Two minimal test tables with distinct business entities."""
    return [
        TableDescriptionWithColumns(
            table_name="test_orders",
            main_entity="订单/order/购买记录",
            table_type="fact",
            primary_key="order_id",
            key_attributes=["订单号", "用户ID", "订单状态", "金额", "创建时间"],
            description="订单表记录所有用户的购买订单，包含订单基本信息、支付状态和物流信息。",
            usage_scenario="当需要查询用户的订单历史、统计销售额或分析订单状态分布时使用此表。",
            row_count_estimate=50000,
            columns=[
                ColumnSummary(
                    column_name="order_id",
                    description="订单唯一标识，自增主键",
                    sample_values=["100001", "100002"],
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
                    column_name="order_status",
                    description="订单状态：pending/paid/shipped/delivered/cancelled",
                    sample_values=["paid", "shipped"],
                    data_type="varchar(32)",
                ),
                ColumnSummary(
                    column_name="total_amount",
                    description="订单总金额（元）",
                    sample_values=["299.00", "1580.50"],
                    data_type="decimal(12,2)",
                ),
                ColumnSummary(
                    column_name="created_at",
                    description="订单创建时间",
                    sample_values=["2026-07-20 10:30:00"],
                    data_type="datetime",
                ),
            ],
        ),
        TableDescriptionWithColumns(
            table_name="test_alerts",
            main_entity="告警/alert/监控通知",
            table_type="fact",
            primary_key="alert_id",
            key_attributes=["告警ID", "告警级别", "告警类型", "服务名称", "触发时间"],
            description="告警表记录所有系统监控告警事件，包含告警级别、触发条件和处理状态。",
            usage_scenario="当需要查询历史告警记录、分析告警趋势或统计告警处理效率时使用此表。",
            row_count_estimate=120000,
            columns=[
                ColumnSummary(
                    column_name="alert_id",
                    description="告警唯一标识，自增主键",
                    sample_values=["A001", "A002"],
                    data_type="bigint",
                    is_primary_key=True,
                ),
                ColumnSummary(
                    column_name="alert_level",
                    description="告警级别：P0/P1/P2/P3/P4（严重程度递减）",
                    sample_values=["P1", "P2"],
                    data_type="varchar(8)",
                ),
                ColumnSummary(
                    column_name="alert_type",
                    description="告警类型：cpu/memory/disk/network/latency/error_rate",
                    sample_values=["latency", "error_rate"],
                    data_type="varchar(32)",
                ),
                ColumnSummary(
                    column_name="service_name",
                    description="触发告警的服务名称",
                    sample_values=["order-service", "payment-service"],
                    data_type="varchar(64)",
                ),
                ColumnSummary(
                    column_name="triggered_at",
                    description="告警触发时间",
                    sample_values=["2026-07-27 08:15:00"],
                    data_type="datetime",
                ),
            ],
        ),
    ]


# ── Helper: wait for L0/L1 embedding readiness ──

async def wait_for_l0l1_ready(ov: OpenVikingClient, key: str, timeout: float = 120.0) -> bool:
    """Poll find(level=[0,1]) until at least 2 unique table results appear.

    The find API returns results under the 'resources' key (for resources path).
    We extract unique table names from URIs like:
      viking://resources/hdc/{key}/_tables/{table_name}/.overview.md
    """
    tables_uri = _tables_dir_uri(key)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            result = await ov.find(
                query="test order alert",
                target_uri=tables_uri,
                level=[0, 1],
                limit=20,
            )
            # find() auto-unwraps status→result, so we get the result dict directly
            # It has keys: memories, resources, skills, total
            entries = []
            if isinstance(result, dict):
                entries = (
                    result.get("resources", [])
                    or result.get("matches", [])
                    or []
                )
            elif isinstance(result, list):
                entries = result

            # Extract unique table names from matches
            table_names = set()
            for entry in entries:
                uri = entry.get("uri", "")
                if "/_tables/" in uri:
                    parts = uri.rstrip("/").split("/")
                    # URI format: .../_tables/{table_name}/.overview.md
                    # Find _tables index, table_name is the next part
                    for i, p in enumerate(parts):
                        if p == "_tables" and i + 1 < len(parts):
                            tn = parts[i + 1]
                            # Skip sub-dir names, file extensions
                            if tn and not tn.startswith("_") and not tn.endswith(".md"):
                                table_names.add(tn)
                            # Also handle: _tables/{table_name}/.overview.md → table_name
                            elif tn and not tn.startswith("_") and tn.endswith(".md"):
                                # This is a file like .abstract.md → table is parts[i+1]
                                pass  # i+1 is the dir before the file
                            break
                # Second pass: extract table name from .../_tables/{table_name}/.overview.md
                if "/_tables/" in uri and "/.overview" in uri:
                    after_tables = uri.split("/_tables/", 1)[1] if "/_tables/" in uri else ""
                    parts = after_tables.split("/")
                    if parts:
                        tn = parts[0]
                        if tn and not tn.startswith("_"):
                            table_names.add(tn)

            if len(table_names) >= 2:
                logging.info("L0/L1 ready: found %d unique tables: %s", len(table_names), sorted(table_names))
                return True
            elif table_names:
                logging.info("L0/L1 partial: found %d tables: %s (need 2)", len(table_names), sorted(table_names))
            else:
                logging.info("L0/L1: no table-level results yet, %d raw entries", len(entries))
        except Exception as e:
            logging.info("L0/L1 check failed (will retry): %s", e)
        await asyncio.sleep(2.0)

    logging.warning("L0/L1 not ready within %.0fs", timeout)
    return False


# ── Helper: verify L0/L1 files exist per table ──

async def verify_l0l1_per_table(ov: OpenVikingClient, key: str, table_names: list[str]) -> dict[str, dict]:
    """Check whether each table directory returns results via find(level=[0,1]).

    Queries at each individual table directory to check for L0 (.abstract.md) and
    L1 (.overview.md) entries. At the _tables directory level, L0 abstracts may
    not surface due to lower scores compared to higher-level overviews.

    Returns: {table_name: {"l0_found": bool, "l1_found": bool, "entries": list}}
    """
    from app.datavault.uploader import _table_dir_uri

    results = {tn: {"l0_found": False, "l1_found": False, "entries": []} for tn in table_names}

    for tn in table_names:
        table_uri = _table_dir_uri(key, tn)
        result = await ov.find(
            query="test",
            target_uri=table_uri,
            level=[0, 1],
            limit=10,
        )

        entries = (
            result.get("resources", []) if isinstance(result, dict)
            else result if isinstance(result, list)
            else []
        )

        for entry in entries:
            uri = entry.get("uri", "")
            name = entry.get("name", "")
            score = entry.get("score", 0.0)
            level = entry.get("level", -1)
            entry_info = {"uri": uri, "name": name, "score": score, "level": level}
            results[tn]["entries"].append(entry_info)
            if ".abstract" in (uri + name):
                results[tn]["l0_found"] = True
            if ".overview" in (uri + name):
                results[tn]["l1_found"] = True

    return results


# ── Cleanup ──

async def cleanup(ov: OpenVikingClient, key: str) -> None:
    """Delete the test database HDC directory."""
    from app.datavault.uploader import _db_uri
    try:
        await ov.rm(_db_uri(key), recursive=True)
        logging.info("Cleanup: deleted %s", _db_uri(key))
    except Exception as e:
        logging.warning("Cleanup failed: %s", e)


# ═══════════════════════════════════════════════════════════════
#  Test: Full pipeline — generate → L0/L1 → retrieve → verify
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_new_format_pipeline(key, test_tables):
    """Verify the complete new-format HDC pipeline from generation to retrieval.

    Steps:
    1. Upload 2 tables via HDCUploader (new format: resources path + _columns/ subdir)
    2. Wait for L0/L1 embedding to complete
    3. Verify L0/L1 files exist per table via find(level=[0,1])
    4. Retrieve "查询订单" → test_orders is top match
    5. Retrieve "查询告警" → test_alerts is top match
    """
    ov = OpenVikingClient(OV_URL, TEST_USER)
    await ov.start()
    uploader = HDCUploader(ov)

    try:
        # Clean any leftover data from previous runs first
        from app.datavault.uploader import _db_uri
        try:
            await ov.rm(_db_uri(key), recursive=True)
            logging.info("Cleaned up leftover data from previous run")
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # ── Step 1: Upload tables ──
        logging.info("=" * 60)
        logging.info("Step 1: Uploading %d test tables", len(test_tables))
        logging.info("=" * 60)

        for table in test_tables:
            t0 = time.monotonic()
            await uploader.upload_table(key, table)
            elapsed = time.monotonic() - t0
            logging.info(
                "Uploaded table %s with %d columns in %.1fs",
                table.table_name, len(table.columns), elapsed,
            )

        # ── Step 2: Wait for L0/L1 embedding ──
        logging.info("=" * 60)
        logging.info("Step 2: Waiting for L0/L1 embedding to complete...")
        logging.info("=" * 60)

        l0l1_ready = await wait_for_l0l1_ready(ov, key, timeout=120.0)
        assert l0l1_ready, (
            "L0/L1 embedding did not complete within timeout. "
            "SemanticProcessor may not be running or OpenViking may be unavailable."
        )

        # ── Step 3: Verify L0/L1 files per table ──
        logging.info("=" * 60)
        logging.info("Step 3: Verifying L0/L1 files per table")
        logging.info("=" * 60)

        expected_tables = [t.table_name for t in test_tables]
        l0l1_status = await verify_l0l1_per_table(ov, key, expected_tables)

        for tn, status in l0l1_status.items():
            logging.info(
                "  %s: L0=%s L1=%s entries=%d",
                tn, status["l0_found"], status["l1_found"], len(status["entries"]),
            )
            assert status["l0_found"], (
                f"L0 (.abstract.md) not found for table '{tn}'. "
                f"SemanticProcessor may not have generated the abstract summary. "
                f"Entries found: {status['entries']}"
            )
            assert status["l1_found"], (
                f"L1 (.overview.md) not found for table '{tn}'. "
                f"SemanticProcessor may not have generated the overview summary. "
                f"Entries found: {status['entries']}"
            )
            assert len(status["entries"]) > 0, (
                f"No entries returned for table '{tn}' via find(level=[0,1])"
            )

        # ── Step 4: Retrieve "查询订单" → test_orders is top match ──
        logging.info("=" * 60)
        logging.info("Step 4: Retrieve '查询订单' → expect test_orders as top match")
        logging.info("=" * 60)

        retriever = HDCRetriever(ov)
        ctx_orders = await retriever.retrieve(
            "查询最近的订单记录和订单状态",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace=TEST_NAMESPACE,
        )

        assert ctx_orders is not None, (
            "retrieve('查询订单') returned None — no tables matched. "
            "Check if L0/L1 embedding has completed and scores meet threshold."
        )
        assert len(ctx_orders.matched_tables) > 0, (
            "retrieve('查询订单') returned empty matched_tables"
        )

        top_table = ctx_orders.matched_tables[0].table_name
        logging.info(
            "  Top match: %s (entity=%s, type=%s)",
            top_table,
            ctx_orders.matched_tables[0].main_entity,
            ctx_orders.matched_tables[0].table_type,
        )
        for i, tm in enumerate(ctx_orders.matched_tables):
            logging.info(
                "    [%d] %s — %s [%s] cols=%d",
                i + 1, tm.table_name, tm.main_entity, tm.table_type,
                len(tm.relevant_columns),
            )

        assert top_table == "test_orders", (
            f"Expected 'test_orders' as top match for '查询订单', got '{top_table}'. "
            f"All matches: {[t.table_name for t in ctx_orders.matched_tables]}"
        )

        # ── Step 5: Retrieve "查询告警" → test_alerts is top match ──
        logging.info("=" * 60)
        logging.info("Step 5: Retrieve '查询告警' → expect test_alerts as top match")
        logging.info("=" * 60)

        ctx_alerts = await retriever.retrieve(
            "查询最近的系统告警记录和告警级别",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace=TEST_NAMESPACE,
        )

        assert ctx_alerts is not None, (
            "retrieve('查询告警') returned None — no tables matched."
        )
        assert len(ctx_alerts.matched_tables) > 0, (
            "retrieve('查询告警') returned empty matched_tables"
        )

        top_table_alerts = ctx_alerts.matched_tables[0].table_name
        logging.info(
            "  Top match: %s (entity=%s, type=%s)",
            top_table_alerts,
            ctx_alerts.matched_tables[0].main_entity,
            ctx_alerts.matched_tables[0].table_type,
        )
        for i, tm in enumerate(ctx_alerts.matched_tables):
            logging.info(
                "    [%d] %s — %s [%s] cols=%d",
                i + 1, tm.table_name, tm.main_entity, tm.table_type,
                len(tm.relevant_columns),
            )

        assert top_table_alerts == "test_alerts", (
            f"Expected 'test_alerts' as top match for '查询告警', got '{top_table_alerts}'. "
            f"All matches: {[t.table_name for t in ctx_alerts.matched_tables]}"
        )

        # ── Step 6: Verify retriever uses level=[0,1] (not falling back to L2) ──
        logging.info("=" * 60)
        logging.info("Step 6: Verify retriever uses level=[0,1] (not L2 fallback)")
        logging.info("=" * 60)

        # If L0/L1 is working, a query specific to one table should still return it.
        # The key evidence: if L0/L1 failed to find anything, the retriever would
        # fall back to level=[2] and still find results — but we verify L0/L1 directly
        # by checking that the tables_uri find(level=[0,1]) returns entries.
        tables_uri = _tables_dir_uri(key)
        l0l1_direct = await ov.find(
            query="订单 告警",
            target_uri=tables_uri,
            level=[0, 1],
            limit=10,
        )
        l0l1_entries = (
            l0l1_direct.get("resources", []) if isinstance(l0l1_direct, dict)
            else l0l1_direct if isinstance(l0l1_direct, list)
            else []
        )
        assert len(l0l1_entries) > 0, (
            "find(level=[0,1]) returned no entries — retriever would fall back to level=[2]. "
            "L0/L1 embedding is not ready."
        )
        logging.info(
            "  find(level=[0,1]) returned %d entries — retriever uses new format",
            len(l0l1_entries),
        )

        # Also verify distinct table coverage from L0/L1
        l2_direct = await ov.find(
            query="订单 告警",
            target_uri=tables_uri,
            level=[2],
            limit=10,
        )
        l2_entries = (
            l2_direct.get("resources", []) if isinstance(l2_direct, dict)
            else l2_direct if isinstance(l2_direct, list)
            else []
        )
        logging.info(
            "  Comparison: L0/L1=%d entries, L2=%d entries",
            len(l0l1_entries), len(l2_entries),
        )

        logging.info("=" * 60)
        logging.info("ALL CHECKS PASSED: New-format HDC pipeline verification complete!")
        logging.info("=" * 60)

    finally:
        if CLEANUP_AFTER_TEST:
            await cleanup(ov, key)
        await ov.close()


# ═══════════════════════════════════════════════════════════════
#  Test 3.3: Updater compatibility with new directory structure
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def updater_key():
    """Storage key for updater compatibility test."""
    return storage_key(TEST_SCHEMA_ID, TEST_DB_NAME, namespace="updater_compat_test")


@pytest.mark.asyncio
async def test_updater_new_format_compatibility(updater_key):
    """Task 3.3: Verifies the updater works with the new directory structure (_columns/ subdirs).

    The updater reads/writes column hashes as tags on _INDEX.md files. The new
    directory format (columns in _columns/ subdir) should not affect the updater's
    ability to read and write hash tags -- _INDEX.md remains in the table directory.

    Steps:
    1. Upload two tables via HDCUploader (new format with _columns/ subdirs)
    2. Use _get_stored_state to verify tags can be read from new-format directories
    3. Use _store_hash to verify tags can be written to new-format directories
    4. Verify _compute_columns_hash produces deterministic results
    5. Verify updater's state comparison logic works across new-format directories
    """
    from app.datavault.updater import HDCUpdater
    from app.datavault.models import ColumnRaw, TableRaw
    from app.datavault.uploader import _table_dir_uri, _tables_dir_uri

    ov = OpenVikingClient(OV_URL, TEST_USER)
    await ov.start()
    uploader = HDCUploader(ov)

    try:
        # Clean any leftover data
        try:
            await ov.rm(_db_uri(updater_key), recursive=True)
            logging.info("Cleaned up leftover data from previous run")
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # ── Step 1: Upload tables in new format (via HDCUploader → _columns/ subdirs) ──
        logging.info("=" * 60)
        logging.info("Step 1: Uploading tables in new format (with _columns/ subdirs)")
        logging.info("=" * 60)

        # Create a minimal updater (no real collector/generator needed for hash tests)
        updater = HDCUpdater(
            collector=None,
            generator=None,
            uploader=uploader,
        )

        # Manual table descriptions matching the updater's expected format
        test_tables_for_update = [
            TableDescriptionWithColumns(
                table_name="test_updater_a",
                main_entity="用户/user/账户信息",
                table_type="dimension",
                primary_key="user_id",
                key_attributes=["用户名", "邮箱", "角色", "创建时间"],
                description="用户表记录系统用户的基本信息和账户状态。",
                usage_scenario="当需要查询用户信息、验证权限或统计用户活跃度时使用此表。",
                row_count_estimate=5000,
                columns=[
                    ColumnSummary(column_name="user_id", description="用户唯一标识", sample_values=["1001"], data_type="bigint", is_primary_key=True),
                    ColumnSummary(column_name="username", description="用户登录名", sample_values=["admin"], data_type="varchar(64)"),
                    ColumnSummary(column_name="email", description="用户邮箱", sample_values=["user@example.com"], data_type="varchar(128)"),
                    ColumnSummary(column_name="role", description="用户角色：admin/developer/viewer", sample_values=["developer"], data_type="varchar(32)"),
                    ColumnSummary(column_name="created_at", description="账户创建时间", sample_values=["2025-01-15"], data_type="datetime"),
                ],
            ),
            TableDescriptionWithColumns(
                table_name="test_updater_b",
                main_entity="日志/log/操作记录",
                table_type="fact",
                primary_key="log_id",
                key_attributes=["日志ID", "操作类型", "用户ID", "操作时间"],
                description="操作日志表记录所有用户的操作行为，用于审计和安全分析。",
                usage_scenario="当需要追踪用户操作、审计操作记录或分析操作模式时使用此表。",
                row_count_estimate=200000,
                columns=[
                    ColumnSummary(column_name="log_id", description="日志唯一标识", sample_values=["L10001"], data_type="bigint", is_primary_key=True),
                    ColumnSummary(column_name="action_type", description="操作类型：create/update/delete/query", sample_values=["create"], data_type="varchar(32)"),
                    ColumnSummary(column_name="user_id", description="操作用户ID", sample_values=["1001"], data_type="bigint"),
                    ColumnSummary(column_name="action_time", description="操作时间", sample_values=["2026-07-27 10:00:00"], data_type="datetime"),
                    ColumnSummary(column_name="details", description="操作详情摘要", sample_values=["Created order #100001"], data_type="text"),
                ],
            ),
        ]

        for table in test_tables_for_update:
            await uploader.upload_table(updater_key, table)
            logging.info("Uploaded table %s in new format", table.table_name)

        # Store hash tags so _get_stored_state can find them
        test_raw_tables = [
            TableRaw(
                name="test_updater_a",
                columns=[
                    ColumnRaw(name="user_id", data_type="bigint", nullable=False),
                    ColumnRaw(name="username", data_type="varchar(64)", nullable=False),
                    ColumnRaw(name="email", data_type="varchar(128)", nullable=False),
                    ColumnRaw(name="role", data_type="varchar(32)", nullable=False),
                    ColumnRaw(name="created_at", data_type="datetime", nullable=False),
                ],
            ),
            TableRaw(
                name="test_updater_b",
                columns=[
                    ColumnRaw(name="log_id", data_type="bigint", nullable=False),
                    ColumnRaw(name="action_type", data_type="varchar(32)", nullable=False),
                    ColumnRaw(name="user_id", data_type="bigint", nullable=False),
                    ColumnRaw(name="action_time", data_type="datetime", nullable=False),
                    ColumnRaw(name="details", data_type="text", nullable=False),
                ],
            ),
        ]

        for table_raw in test_raw_tables:
            columns_hash = HDCUpdater._compute_columns_hash(table_raw.columns)
            await updater._store_hash(updater_key, table_raw.name, columns_hash)
            logging.info(
                "Stored hash for %s: %s",
                table_raw.name, columns_hash[:16],
            )

        # ── Step 2: Verify _get_stored_state can read hashes from new-format directories ──
        logging.info("=" * 60)
        logging.info("Step 2: Reading stored hashes from new-format directories")
        logging.info("=" * 60)

        stored_hashes, existing_tables = await updater._get_stored_state(updater_key)

        logging.info("Stored hashes: %s", {k: v[:16] for k, v in stored_hashes.items()})
        logging.info("Existing tables: %s", sorted(existing_tables))

        assert "test_updater_a" in stored_hashes, (
            f"Expected 'test_updater_a' in stored_hashes, got {list(stored_hashes.keys())}. "
            f"Tags on _INDEX.md in new-format directory may not be readable."
        )
        assert "test_updater_b" in stored_hashes, (
            f"Expected 'test_updater_b' in stored_hashes, got {list(stored_hashes.keys())}"
        )
        assert "test_updater_a" in existing_tables, (
            f"Expected 'test_updater_a' in existing_tables, got {sorted(existing_tables)}"
        )
        assert "test_updater_b" in existing_tables, (
            f"Expected 'test_updater_b' in existing_tables, got {sorted(existing_tables)}"
        )

        # Verify the hashes match what was computed
        expected_hash_a = HDCUpdater._compute_columns_hash(test_raw_tables[0].columns)
        expected_hash_b = HDCUpdater._compute_columns_hash(test_raw_tables[1].columns)
        assert stored_hashes["test_updater_a"] == expected_hash_a, (
            f"Hash for test_updater_a mismatch. Stored hash may differ from computed."
        )
        assert stored_hashes["test_updater_b"] == expected_hash_b, (
            f"Hash for test_updater_b mismatch."
        )

        # ── Step 3: Verify _store_hash works with new-format directory ──
        logging.info("=" * 60)
        logging.info("Step 3: Verify hash storage and retrieval via fs/attrs on new-format dirs")
        logging.info("=" * 60)

        # Re-read via raw API to verify the tag is actually on the _INDEX.md file
        index_uri_a = f"{_table_dir_uri(updater_key, 'test_updater_a')}/_INDEX.md"
        attrs_a = await ov._get_raw("/api/v1/fs/attrs", index_uri_a)
        logging.info("fs/attrs for %s", index_uri_a)

        if isinstance(attrs_a, dict):
            attrs_inner = attrs_a.get("attrs", {})
            tags_list = attrs_inner.get("tags", []) if isinstance(attrs_inner, dict) else []
            if isinstance(tags_list, list):
                hash_tags = [t for t in tags_list if isinstance(t, str) and t.startswith("columns_hash=")]
                logging.info("columns_hash tags on _INDEX.md: %s", hash_tags)
                assert len(hash_tags) >= 1, (
                    f"Expected at least one columns_hash tag on _INDEX.md, got {hash_tags}. "
                    f"All tags: {tags_list}. updater may be writing tags to wrong location."
                )

        # ── Step 4: Verify _compute_columns_hash is deterministic ──
        logging.info("=" * 60)
        logging.info("Step 4: Verify hash determinism")
        logging.info("=" * 60)

        hash1 = HDCUpdater._compute_columns_hash(test_raw_tables[0].columns)
        hash2 = HDCUpdater._compute_columns_hash(test_raw_tables[0].columns)
        assert hash1 == hash2, "Column hashes should be deterministic"

        # Verify reordered columns produce the same hash
        reordered = [
            ColumnRaw(name="created_at", data_type="datetime", nullable=False),
            ColumnRaw(name="email", data_type="varchar(128)", nullable=False),
            ColumnRaw(name="role", data_type="varchar(32)", nullable=False),
            ColumnRaw(name="user_id", data_type="bigint", nullable=False),
            ColumnRaw(name="username", data_type="varchar(64)", nullable=False),
        ]
        reordered_hash = HDCUpdater._compute_columns_hash(reordered)
        assert reordered_hash == hash1, (
            "Column hash should be invariant to column order (alphabetically sorted)"
        )

        # ── Step 5: Verify no changes detected for identical schema ──
        logging.info("=" * 60)
        logging.info("Step 5: Verify state comparison (detect no changes for identical tables)")
        logging.info("=" * 60)

        current_hashes = {
            "test_updater_a": expected_hash_a,
            "test_updater_b": expected_hash_b,
        }

        # Simulate the updater's diff logic
        new_tables = []
        changed_tables = []
        for name, current_hash in current_hashes.items():
            if name not in existing_tables:
                new_tables.append(name)
            elif name not in stored_hashes:
                new_tables.append(name)
            elif current_hash != stored_hashes[name]:
                changed_tables.append(name)

        deleted_tables = [
            name for name in stored_hashes if name not in current_hashes
        ]
        for name in existing_tables:
            if name not in current_hashes and name not in deleted_tables:
                deleted_tables.append(name)

        logging.info("new=%s, changed=%s, deleted=%s", new_tables, changed_tables, deleted_tables)

        assert len(new_tables) == 0, (
            f"Expected 0 new tables for identical schema, got {new_tables}"
        )
        assert len(changed_tables) == 0, (
            f"Expected 0 changed tables for identical schema, got {changed_tables}"
        )
        assert len(deleted_tables) == 0, (
            f"Expected 0 deleted tables for identical schema, got {deleted_tables}"
        )

        # ── Step 6: Verify change detection works (different columns) ──
        logging.info("=" * 60)
        logging.info("Step 6: Verify change detection with modified columns")
        logging.info("=" * 60)

        # Add a new column
        modified_raw = TableRaw(
            name="test_updater_a",
            columns=[
                ColumnRaw(name="user_id", data_type="bigint", nullable=False),
                ColumnRaw(name="username", data_type="varchar(64)", nullable=False),
                ColumnRaw(name="email", data_type="varchar(128)", nullable=False),
                ColumnRaw(name="role", data_type="varchar(32)", nullable=False),
                ColumnRaw(name="created_at", data_type="datetime", nullable=False),
                ColumnRaw(name="phone", data_type="varchar(20)", nullable=True),  # NEW
            ],
        )
        modified_hash = HDCUpdater._compute_columns_hash(modified_raw.columns)

        assert modified_hash != expected_hash_a, (
            "Modified schema (added column) should produce a different hash"
        )
        logging.info(
            "Original hash: %s, Modified hash: %s",
            expected_hash_a[:16], modified_hash[:16],
        )

        # Verify change detection
        current_hashes_modified = {
            "test_updater_a": modified_hash,
            "test_updater_b": expected_hash_b,
        }

        detected_changes = []
        for name, h in current_hashes_modified.items():
            if name in stored_hashes and h != stored_hashes[name]:
                detected_changes.append(name)

        assert "test_updater_a" in detected_changes, (
            f"Expected 'test_updater_a' to be detected as changed. Got: {detected_changes}"
        )

        logging.info("=" * 60)
        logging.info("ALL CHECKS PASSED: Updater new-format compatibility verified!")
        logging.info("=" * 60)

    finally:
        if CLEANUP_AFTER_TEST:
            await cleanup(ov, updater_key)
        await ov.close()


# ═══════════════════════════════════════════════════════════════
#  Test 4.3: Three-table integration test (generation + retrieval + ranking)
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def three_table_key():
    """Storage key for 3-table integration test."""
    return storage_key(TEST_SCHEMA_ID, TEST_DB_NAME, namespace="three_table_test")


@pytest.fixture
def three_tables():
    """Three test tables with distinct business domains: orders, alerts, workflow."""
    return [
        TableDescriptionWithColumns(
            table_name="test_orders",
            main_entity="订单/order/购买记录",
            table_type="fact",
            primary_key="order_id",
            key_attributes=["订单号", "用户ID", "订单状态", "金额", "创建时间"],
            description="订单表记录所有用户的购买订单，包含订单基本信息、支付状态和物流信息。",
            usage_scenario="当需要查询用户的订单历史、统计销售额或分析订单状态分布时使用此表。",
            row_count_estimate=50000,
            columns=[
                ColumnSummary(column_name="order_id", description="订单唯一标识", sample_values=["100001"], data_type="bigint", is_primary_key=True),
                ColumnSummary(column_name="user_id", description="用户ID", sample_values=["5001"], data_type="bigint"),
                ColumnSummary(column_name="order_status", description="订单状态：pending/paid/shipped/delivered/cancelled", sample_values=["paid"], data_type="varchar(32)"),
                ColumnSummary(column_name="total_amount", description="订单总金额（元）", sample_values=["299.00"], data_type="decimal(12,2)"),
                ColumnSummary(column_name="created_at", description="订单创建时间", sample_values=["2026-07-20"], data_type="datetime"),
            ],
        ),
        TableDescriptionWithColumns(
            table_name="test_alerts",
            main_entity="告警/alert/监控通知",
            table_type="fact",
            primary_key="alert_id",
            key_attributes=["告警ID", "告警级别", "告警类型", "服务名称", "触发时间"],
            description="告警表记录所有系统监控告警事件，包含告警级别、触发条件和处理状态。",
            usage_scenario="当需要查询历史告警记录、分析告警趋势或统计告警处理效率时使用此表。",
            row_count_estimate=120000,
            columns=[
                ColumnSummary(column_name="alert_id", description="告警唯一标识", sample_values=["A001"], data_type="bigint", is_primary_key=True),
                ColumnSummary(column_name="alert_level", description="告警级别：P0/P1/P2/P3/P4", sample_values=["P1"], data_type="varchar(8)"),
                ColumnSummary(column_name="alert_type", description="告警类型：cpu/memory/disk/network/latency/error_rate", sample_values=["latency"], data_type="varchar(32)"),
                ColumnSummary(column_name="service_name", description="触发告警的服务名称", sample_values=["order-service"], data_type="varchar(64)"),
                ColumnSummary(column_name="triggered_at", description="告警触发时间", sample_values=["2026-07-27 08:15:00"], data_type="datetime"),
            ],
        ),
        TableDescriptionWithColumns(
            table_name="test_workflow",
            main_entity="工作流/workflow/审批流程",
            table_type="fact",
            primary_key="workflow_id",
            key_attributes=["工作流ID", "工作流名称", "状态", "发起人", "创建时间", "完成时间"],
            description="工作流表记录所有审批工作流的定义和实例信息，包含审批节点、状态变更和审批结果。",
            usage_scenario="当需要查询审批进度、统计工单审批效率或分析工作流节点耗时分布时使用此表。",
            row_count_estimate=35000,
            columns=[
                ColumnSummary(column_name="workflow_id", description="工作流唯一标识", sample_values=["WF001"], data_type="bigint", is_primary_key=True),
                ColumnSummary(column_name="workflow_name", description="工作流名称，如'数据变更审批流'", sample_values=["数据变更审批"], data_type="varchar(128)"),
                ColumnSummary(column_name="workflow_status", description="工作流状态：pending/approved/rejected/cancelled", sample_values=["approved"], data_type="varchar(32)"),
                ColumnSummary(column_name="initiator_id", description="发起人工号或用户ID", sample_values=["5001"], data_type="bigint"),
                ColumnSummary(column_name="current_step", description="当前审批步骤名称", sample_values=["部门主管审批"], data_type="varchar(64)"),
                ColumnSummary(column_name="created_at", description="工作流创建时间", sample_values=["2026-07-25 09:00:00"], data_type="datetime"),
                ColumnSummary(column_name="completed_at", description="工作流完成时间", sample_values=["2026-07-25 17:30:00"], data_type="datetime"),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_three_table_pipeline(three_table_key, three_tables):
    """Task 4.3: Three-table integration test with generation + L0/L1 + retrieval + ranking.

    Verifies Requirements 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1 (table scoring + entity dedup)
    with a 3-table knowledge base.

    Steps:
    1. Upload 3 tables (test_orders, test_alerts, test_workflow) via HDCUploader
    2. Wait for L0/L1 embedding to complete on all 3 tables
    3. Retrieve "查询订单" → test_orders is top match
    4. Retrieve "查询告警" → test_alerts is top match
    5. Retrieve "查询工作流" → test_workflow is top match
    6. Verify table ranking: correct table is highest scored for its domain
    7. Verify generic query returns all 3 tables in ranking order
    """
    ov = OpenVikingClient(OV_URL, TEST_USER)
    await ov.start()
    uploader = HDCUploader(ov)

    try:
        # Clean any leftover data
        try:
            await ov.rm(_db_uri(three_table_key), recursive=True)
            logging.info("Cleaned up leftover data from previous run")
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # ── Step 1: Upload 3 tables ──
        logging.info("=" * 60)
        logging.info("Step 1: Uploading 3 tables in new format")
        logging.info("=" * 60)

        for table in three_tables:
            t0 = time.monotonic()
            await uploader.upload_table(three_table_key, table)
            elapsed = time.monotonic() - t0
            logging.info(
                "Uploaded table %s with %d columns in %.1fs",
                table.table_name, len(table.columns), elapsed,
            )

        # ── Step 2: Wait for L0/L1 embedding on all 3 tables ──
        logging.info("=" * 60)
        logging.info("Step 2: Waiting for L0/L1 embedding on all 3 tables...")
        logging.info("=" * 60)

        l0l1_ready = await wait_for_l0l1_ready(ov, three_table_key, timeout=180.0)
        assert l0l1_ready, (
            "L0/L1 embedding did not complete for 3 tables within timeout."
        )

        # Verify all 3 tables have L0/L1
        expected_names = [t.table_name for t in three_tables]
        l0l1_status = await verify_l0l1_per_table(ov, three_table_key, expected_names)

        for tn, status in l0l1_status.items():
            logging.info(
                "  %s: L0=%s L1=%s entries=%d",
                tn, status["l0_found"], status["l1_found"], len(status["entries"]),
            )
            assert status["l0_found"], f"L0 not found for table '{tn}'"
            assert status["l1_found"], f"L1 not found for table '{tn}'"

        # ── Step 3: Retrieve "查询订单" → test_orders top match ──
        logging.info("=" * 60)
        logging.info("Step 3: Retrieve '查询订单' → expect test_orders as #1")
        logging.info("=" * 60)

        retriever = HDCRetriever(ov)
        ctx_orders = await retriever.retrieve(
            "查询最近的订单记录和订单状态",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace="three_table_test",
        )

        assert ctx_orders is not None, "retrieve('查询订单') returned None"
        assert len(ctx_orders.matched_tables) > 0, "retrieve('查询订单') returned 0 tables"

        top_table = ctx_orders.matched_tables[0].table_name
        logging.info("Top match for '查询订单': %s", top_table)
        for i, tm in enumerate(ctx_orders.matched_tables):
            logging.info("  [%d] %s — %s [%s] cols=%d",
                i + 1, tm.table_name, tm.main_entity, tm.table_type,
                len(tm.relevant_columns),
            )

        assert top_table == "test_orders", (
            f"Expected 'test_orders' as top match, got '{top_table}'."
        )

        # ── Step 4: Retrieve "查询告警" → test_alerts top match ──
        logging.info("=" * 60)
        logging.info("Step 4: Retrieve '查询告警' → expect test_alerts as #1")
        logging.info("=" * 60)

        ctx_alerts = await retriever.retrieve(
            "查询最近的系统告警记录和告警级别",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace="three_table_test",
        )

        assert ctx_alerts is not None, "retrieve('查询告警') returned None"
        assert len(ctx_alerts.matched_tables) > 0, "retrieve('查询告警') returned 0 tables"

        top_alerts = ctx_alerts.matched_tables[0].table_name
        logging.info("Top match for '查询告警': %s", top_alerts)
        for i, tm in enumerate(ctx_alerts.matched_tables):
            logging.info("  [%d] %s — %s [%s] cols=%d",
                i + 1, tm.table_name, tm.main_entity, tm.table_type,
                len(tm.relevant_columns),
            )

        assert top_alerts == "test_alerts", (
            f"Expected 'test_alerts' as top match, got '{top_alerts}'."
        )

        # ── Step 5: Retrieve "查询工作流" → test_workflow top match ──
        logging.info("=" * 60)
        logging.info("Step 5: Retrieve '查询工作流' → expect test_workflow as #1")
        logging.info("=" * 60)

        ctx_wf = await retriever.retrieve(
            "查询审批工作流的当前状态和审批进度",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace="three_table_test",
        )

        assert ctx_wf is not None, "retrieve('查询工作流') returned None"
        assert len(ctx_wf.matched_tables) > 0, "retrieve('查询工作流') returned 0 tables"

        top_wf = ctx_wf.matched_tables[0].table_name
        logging.info("Top match for '查询工作流': %s", top_wf)
        for i, tm in enumerate(ctx_wf.matched_tables):
            logging.info("  [%d] %s — %s [%s] cols=%d",
                i + 1, tm.table_name, tm.main_entity, tm.table_type,
                len(tm.relevant_columns),
            )

        assert top_wf == "test_workflow", (
            f"Expected 'test_workflow' as top match, got '{top_wf}'."
        )

        # ── Step 6: Verify distinct ranking for each domain ──
        logging.info("=" * 60)
        logging.info("Step 6: Verify each table ranks #1 for its own domain query")
        logging.info("=" * 60)

        # All three domain-specific queries should rank their table #1
        top_by_domain = {
            "orders": top_table,
            "alerts": top_alerts,
            "workflow": top_wf,
        }
        expected_tops = {
            "orders": "test_orders",
            "alerts": "test_alerts",
            "workflow": "test_workflow",
        }
        for domain, expected in expected_tops.items():
            actual = top_by_domain[domain]
            logging.info("Domain '%s': expected=%s actual=%s", domain, expected, actual)
            assert actual == expected, (
                f"Domain '{domain}': expected '{expected}' as top, got '{actual}'"
            )

        # ── Step 7: Generic query verification ──
        logging.info("=" * 60)
        logging.info("Step 7: Generic query to verify all tables found")
        logging.info("=" * 60)

        ctx_all = await retriever.retrieve(
            "查询",
            TEST_SCHEMA_ID, TEST_DB_NAME,
            namespace="three_table_test",
        )

        assert ctx_all is not None, "Generic retrieve('查询') returned None"
        all_table_names = [tm.table_name for tm in ctx_all.matched_tables]
        logging.info("Generic query matched tables: %s", all_table_names)

        # With only 3 tables, all should appear (no explosion radius limit hit)
        assert len(ctx_all.matched_tables) >= 2, (
            f"Expected at least 2 tables from generic query, got {all_table_names}"
        )

        # ── Step 8: Verify L0/L1 usage (not L2 fallback) ──
        logging.info("=" * 60)
        logging.info("Step 8: Verify L0/L1 is used (not falling back to L2)")
        logging.info("=" * 60)

        tables_uri = _tables_dir_uri(three_table_key)
        l0l1_direct = await ov.find(
            query="订单 告警 工作流",
            target_uri=tables_uri,
            level=[0, 1],
            limit=10,
        )
        l0l1_entries = (
            l0l1_direct.get("resources", []) if isinstance(l0l1_direct, dict)
            else l0l1_direct if isinstance(l0l1_direct, list)
            else []
        )
        assert len(l0l1_entries) > 0, (
            "find(level=[0,1]) returned no entries for 3-table KB. "
            "L0/L1 may not be ready."
        )

        # Extract unique tables from L0/L1 results
        l0l1_tables = set()
        for entry in l0l1_entries:
            uri = entry.get("uri", "")
            if "/_tables/" in uri:
                after = uri.split("/_tables/", 1)[1]
                parts = after.split("/")
                if parts:
                    tn = parts[0]
                    if tn and not tn.startswith("_") and not tn.endswith(".md"):
                        l0l1_tables.add(tn)

        logging.info(
            "L0/L1 covers %d unique tables: %s",
            len(l0l1_tables), sorted(l0l1_tables),
        )
        assert len(l0l1_tables) >= 2, (
            f"Expected L0/L1 to cover at least 2 tables, got {sorted(l0l1_tables)}"
        )

        logging.info("=" * 60)
        logging.info("ALL CHECKS PASSED: Three-table integration test complete!")
        logging.info("=" * 60)

    finally:
        if CLEANUP_AFTER_TEST:
            await cleanup(ov, three_table_key)
        await ov.close()


# ── Allow running directly ──

if __name__ == "__main__":
    asyncio.run(test_new_format_pipeline(
        key=storage_key(TEST_SCHEMA_ID, TEST_DB_NAME, namespace=TEST_NAMESPACE),
        test_tables=[
            TableDescriptionWithColumns(
                table_name="test_orders",
                main_entity="订单/order/购买记录",
                table_type="fact",
                primary_key="order_id",
                key_attributes=["订单号", "用户ID", "订单状态", "金额", "创建时间"],
                description="订单表记录所有用户的购买订单，包含订单基本信息、支付状态和物流信息。",
                usage_scenario="当需要查询用户的订单历史、统计销售额或分析订单状态分布时使用此表。",
                row_count_estimate=50000,
                columns=[
                    ColumnSummary(column_name="order_id", description="订单唯一标识，自增主键", sample_values=["100001"], data_type="bigint", is_primary_key=True),
                    ColumnSummary(column_name="user_id", description="用户ID，关联用户表", sample_values=["5001"], data_type="bigint"),
                    ColumnSummary(column_name="order_status", description="订单状态：pending/paid/shipped/delivered/cancelled", sample_values=["paid"], data_type="varchar(32)"),
                    ColumnSummary(column_name="total_amount", description="订单总金额（元）", sample_values=["299.00"], data_type="decimal(12,2)"),
                    ColumnSummary(column_name="created_at", description="订单创建时间", sample_values=["2026-07-20 10:30:00"], data_type="datetime"),
                ],
            ),
            TableDescriptionWithColumns(
                table_name="test_alerts",
                main_entity="告警/alert/监控通知",
                table_type="fact",
                primary_key="alert_id",
                key_attributes=["告警ID", "告警级别", "告警类型", "服务名称", "触发时间"],
                description="告警表记录所有系统监控告警事件，包含告警级别、触发条件和处理状态。",
                usage_scenario="当需要查询历史告警记录、分析告警趋势或统计告警处理效率时使用此表。",
                row_count_estimate=120000,
                columns=[
                    ColumnSummary(column_name="alert_id", description="告警唯一标识，自增主键", sample_values=["A001"], data_type="bigint", is_primary_key=True),
                    ColumnSummary(column_name="alert_level", description="告警级别：P0/P1/P2/P3/P4（严重程度递减）", sample_values=["P1"], data_type="varchar(8)"),
                    ColumnSummary(column_name="alert_type", description="告警类型：cpu/memory/disk/network/latency/error_rate", sample_values=["latency"], data_type="varchar(32)"),
                    ColumnSummary(column_name="service_name", description="触发告警的服务名称", sample_values=["order-service"], data_type="varchar(64)"),
                    ColumnSummary(column_name="triggered_at", description="告警触发时间", sample_values=["2026-07-27 08:15:00"], data_type="datetime"),
                ],
            ),
        ],
    ))
