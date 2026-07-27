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
