"""
Admin Store, Auth Dependency, resolve_hdc_namespace, SQL Memory management,
and StorageBackend stats unit tests.

Covers test tasks 11.1 through 11.5 for feature ``admin-hdc-memory-manager``.
"""

import asyncio
import datetime
import json

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.memory.admin_store import InMemoryAdminStore, SqliteAdminStore
from app.memory.manager import StorageManager, get_storage, reset_storage
from app.memory.sql_memory import InMemorySqlMemoryStore, SqliteSqlMemoryStore
from app.memory.store import InMemoryStore, SqliteStore
from app.api.routes import resolve_hdc_namespace
from app.main import app


# ============================================================================
# Task 11.1: Admin Store unit tests
# ============================================================================


@pytest_asyncio.fixture
async def admin_store():
    """Create SqliteAdminStore instance with :memory: database."""
    s = SqliteAdminStore(":memory:")
    await s.initialize()
    yield s
    await s.close()


# ── upsert ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_upsert_creates_new_mapping(admin_store):
    """Verify upsert creates a new mapping and returns full record."""
    result = await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    assert result["user_id"] == "alice"
    assert result["schema_id"] == 1
    assert result["database_name"] == "prod_db"
    assert result["hdc_namespace"] == "recall_extra"
    assert "updated_at" in result


@pytest.mark.asyncio
async def test_admin_upsert_overwrites_existing(admin_store):
    """Verify upsert overwrites an existing mapping (INSERT OR REPLACE)."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    result = await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_new",
    )
    assert result["hdc_namespace"] == "recall_new"

    # Verify get_mapping returns the updated value
    mapping = await admin_store.get_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
    )
    assert mapping is not None
    assert mapping["hdc_namespace"] == "recall_new"


# ── get_mapping ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_get_mapping_returns_correct_record(admin_store):
    """Verify get_mapping returns the correct mapping by composite key."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=2, database_name="test_db",
        hdc_namespace="recall_test",
    )

    mapping = await admin_store.get_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
    )
    assert mapping is not None
    assert mapping["hdc_namespace"] == "recall_extra"
    assert mapping["user_id"] == "alice"


@pytest.mark.asyncio
async def test_admin_get_mapping_nonexistent(admin_store):
    """Verify get_mapping returns None for a non-existent mapping."""
    mapping = await admin_store.get_mapping(
        user_id="nobody", schema_id=99, database_name="no_db",
    )
    assert mapping is None


@pytest.mark.asyncio
async def test_admin_get_mapping_partial_key_mismatch(admin_store):
    """Verify get_mapping returns None when only part of composite key matches."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    # Different user_id
    mapping = await admin_store.get_mapping(
        user_id="bob", schema_id=1, database_name="prod_db",
    )
    assert mapping is None


# ── get_mappings with filters ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_get_mappings_no_filters_returns_all(admin_store):
    """Verify get_mappings with no filters returns all mappings."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=2, database_name="test_db",
        hdc_namespace="recall_test",
    )
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=3, database_name="staging",
        hdc_namespace="recall_staging",
    )

    results = await admin_store.get_mappings()
    assert len(results) == 3


@pytest.mark.asyncio
async def test_admin_get_mappings_filter_by_user_id(admin_store):
    """Verify get_mappings filters by user_id correctly."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=2, database_name="test_db",
        hdc_namespace="recall_test",
    )
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=3, database_name="staging",
        hdc_namespace="recall_staging",
    )

    results = await admin_store.get_mappings(user_id="alice")
    assert len(results) == 2
    for r in results:
        assert r["user_id"] == "alice"


@pytest.mark.asyncio
async def test_admin_get_mappings_filter_by_schema_id(admin_store):
    """Verify get_mappings filters by schema_id correctly."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=1, database_name="test_db",
        hdc_namespace="recall_test",
    )
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=3, database_name="staging",
        hdc_namespace="recall_staging",
    )

    results = await admin_store.get_mappings(schema_id=1)
    assert len(results) == 2
    for r in results:
        assert r["schema_id"] == 1


@pytest.mark.asyncio
async def test_admin_get_mappings_filter_by_database_name(admin_store):
    """Verify get_mappings filters by database_name correctly."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=2, database_name="prod_db",
        hdc_namespace="recall_test",
    )
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=3, database_name="staging",
        hdc_namespace="recall_staging",
    )

    results = await admin_store.get_mappings(database_name="prod_db")
    assert len(results) == 2
    for r in results:
        assert r["database_name"] == "prod_db"


@pytest.mark.asyncio
async def test_admin_get_mappings_combined_filter(admin_store):
    """Verify get_mappings with combined filters (user_id + schema_id)."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=2, database_name="prod_db",
        hdc_namespace="recall_test",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_bob",
    )

    results = await admin_store.get_mappings(user_id="alice", schema_id=1)
    assert len(results) == 1
    assert results[0]["hdc_namespace"] == "recall_extra"


@pytest.mark.asyncio
async def test_admin_get_mappings_empty_result(admin_store):
    """Verify get_mappings returns empty list when no mappings match filter."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )

    results = await admin_store.get_mappings(user_id="nobody")
    assert results == []


# ── delete_mapping ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_delete_existing_mapping(admin_store):
    """Verify delete_mapping removes an existing mapping and returns True."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )

    result = await admin_store.delete_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
    )
    assert result is True

    # Verify it is truly gone
    mapping = await admin_store.get_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
    )
    assert mapping is None


@pytest.mark.asyncio
async def test_admin_delete_nonexistent_mapping(admin_store):
    """Verify delete_mapping returns False for non-existent mapping."""
    result = await admin_store.delete_mapping(
        user_id="nobody", schema_id=99, database_name="no_db",
    )
    assert result is False


@pytest.mark.asyncio
async def test_admin_delete_only_target_mapping(admin_store):
    """Verify delete_mapping only removes the target and leaves others intact."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=2, database_name="prod_db",
        hdc_namespace="recall_test",
    )

    await admin_store.delete_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
    )

    # Deleted mapping should be gone
    assert await admin_store.get_mapping("alice", 1, "prod_db") is None

    # Other mapping should still exist
    remaining = await admin_store.get_mapping("alice", 2, "prod_db")
    assert remaining is not None
    assert remaining["hdc_namespace"] == "recall_test"


# ── Composite key isolation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_composite_key_isolation(admin_store):
    """Verify same schema_id+db_name for different users are isolated."""
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="shared_db",
        hdc_namespace="alice_ns",
    )
    await admin_store.upsert_mapping(
        user_id="bob", schema_id=1, database_name="shared_db",
        hdc_namespace="bob_ns",
    )

    alice_mapping = await admin_store.get_mapping("alice", 1, "shared_db")
    bob_mapping = await admin_store.get_mapping("bob", 1, "shared_db")

    assert alice_mapping["hdc_namespace"] == "alice_ns"
    assert bob_mapping["hdc_namespace"] == "bob_ns"


# ── initialize idempotency ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_initialize_is_idempotent(admin_store):
    """Verify initialize() is idempotent (calling twice does not error)."""
    # First call already done by fixture
    await admin_store.initialize()  # second call

    # Verify table still works
    await admin_store.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="recall_extra",
    )
    mapping = await admin_store.get_mapping("alice", 1, "prod_db")
    assert mapping is not None
    assert mapping["hdc_namespace"] == "recall_extra"


# ============================================================================
# Task 11.2: Auth Dependency unit tests
# ============================================================================


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


class TestAuthCorrectToken:
    """Authenticated requests with correct token should succeed."""

    def test_auth_correct_token_hdc_mappings(self, client, monkeypatch):
        """Verify correct Bearer token passes auth (does not return 401 or 503-auth).
        A 500 is acceptable here because the admin store is not initialized in the
        test context -- the auth dependency itself passes, and the crash is from
        the endpoint handler attempting to use an uninitialized store connection."""
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "admin_api_token", "secret-token")

        # Use raise_server_exceptions=False so that 500 is returned as a
        # response instead of raising an exception in the test.
        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.get(
                "/api/admin/hdc-mappings",
                headers={"Authorization": "Bearer secret-token"},
            )
        # Auth must pass: no 401 (token mismatch/missing) and no 503 (unconfigured).
        # A 500 is expected because the store is not initialized in TestClient context.
        assert response.status_code not in (401, 503)


class TestAuthWrongToken:
    """Wrong token should return 401."""

    def test_auth_wrong_token(self, client, monkeypatch):
        """Verify wrong Bearer token returns 401 with proper detail."""
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "admin_api_token", "secret-token")

        response = client.get(
            "/api/admin/hdc-mappings",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid admin token"


class TestAuthNoHeader:
    """Missing Authorization header should return 401."""

    def test_auth_no_header(self, client, monkeypatch):
        """Verify missing Authorization header returns 401."""
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "admin_api_token", "secret-token")

        response = client.get("/api/admin/hdc-mappings")
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing admin token"


class TestAuthTokenNotConfigured:
    """Empty admin_api_token should return 503."""

    def test_auth_token_not_configured(self, client, monkeypatch):
        """Verify empty admin_api_token returns 503 with proper detail."""
        from app.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "admin_api_token", "")

        response = client.get(
            "/api/admin/hdc-mappings",
            headers={"Authorization": "Bearer any-token"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Admin API not configured"


# ============================================================================
# Task 11.3: resolve_hdc_namespace unit tests
# ============================================================================


@pytest_asyncio.fixture
async def admin_store_for_resolve():
    """Create an InMemoryAdminStore for resolve_hdc_namespace tests."""
    s = InMemoryAdminStore()
    await s.initialize()
    yield s
    await s.close()


def _make_storage_manager(admin_store):
    """Create a StorageManager with a real InMemoryStore session store
    and the given admin_store."""
    session_store = InMemoryStore()
    return StorageManager(session_store=session_store, admin_store=admin_store)


@pytest.mark.asyncio
async def test_resolve_explicit_namespace_wins(admin_store_for_resolve, monkeypatch):
    """3.1: Explicit namespace is returned regardless of mapping state."""
    sm = _make_storage_manager(admin_store_for_resolve)

    # Add a mapping, but explicit should still win
    await admin_store_for_resolve.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="mapped_ns",
    )

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=1, database_name="prod_db",
        explicit_namespace="explicit_ns",
    )
    assert result == "explicit_ns"


@pytest.mark.asyncio
async def test_resolve_mapping_hit(admin_store_for_resolve, monkeypatch):
    """3.2: Without explicit, falls back to admin mapping lookup."""
    sm = _make_storage_manager(admin_store_for_resolve)

    await admin_store_for_resolve.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="mapped_ns",
    )

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=1, database_name="prod_db",
        explicit_namespace=None,
    )
    assert result == "mapped_ns"


@pytest.mark.asyncio
async def test_resolve_mapping_miss(admin_store_for_resolve, monkeypatch):
    """3.3: No explicit and no mapping returns None."""
    sm = _make_storage_manager(admin_store_for_resolve)

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=1, database_name="prod_db",
        explicit_namespace=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_missing_schema_id(admin_store_for_resolve, monkeypatch):
    """3.4: Missing schema_id (None) returns None even with explicit=None."""
    sm = _make_storage_manager(admin_store_for_resolve)

    await admin_store_for_resolve.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="mapped_ns",
    )

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    # schema_id=None should skip mapping lookup
    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=None, database_name="prod_db",
        explicit_namespace=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_missing_database_name(admin_store_for_resolve, monkeypatch):
    """3.4: Missing database_name (None) returns None."""
    sm = _make_storage_manager(admin_store_for_resolve)

    await admin_store_for_resolve.upsert_mapping(
        user_id="alice", schema_id=1, database_name="prod_db",
        hdc_namespace="mapped_ns",
    )

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=1, database_name=None,
        explicit_namespace=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_explicit_with_missing_schema_id(admin_store_for_resolve, monkeypatch):
    """3.1: Explicit namespace wins even when schema_id is None."""
    sm = _make_storage_manager(admin_store_for_resolve)

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=None, database_name=None,
        explicit_namespace="explicit_ns",
    )
    assert result == "explicit_ns"


@pytest.mark.asyncio
async def test_resolve_admin_store_none(monkeypatch):
    """3.3: Returns None when admin_store is None."""
    session_store = InMemoryStore()
    sm = StorageManager(session_store=session_store, admin_store=None)

    monkeypatch.setattr("app.api.routes.get_storage", lambda: sm)

    result = await resolve_hdc_namespace(
        user_id="alice", schema_id=1, database_name="prod_db",
        explicit_namespace=None,
    )
    assert result is None


# ============================================================================
# Task 11.4: SQL Memory management method unit tests
# ============================================================================

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(params=["InMemorySqlMemoryStore", "SqliteSqlMemoryStore"])
async def sql_mem_store(request):
    """Parametrized fixture yielding both SQL memory backends."""
    if request.param == "InMemorySqlMemoryStore":
        s = InMemorySqlMemoryStore()
        await s.initialize()
        yield s
        await s.close()
    else:
        s = SqliteSqlMemoryStore(":memory:")
        await s.initialize()
        yield s
        await s.close()


async def _seed_sql_mem_records(store, records: list[dict]):
    """Helper: insert multiple records into a SQL memory store."""
    for rec in records:
        await store.record(
            user_id=rec["user_id"],
            question=rec["question"],
            sql=rec["sql"],
            table_names=rec.get("table_names", []),
            database_name=rec.get("database_name", "default_db"),
            schema_id=rec.get("schema_id", 1),
            execution_result={
                "row_count": rec.get("row_count", 0),
                "column_names": rec.get("column_names", []),
                "data_preview": rec.get("data_preview", []),
                "execution_status": rec.get("execution_status", "success"),
            },
            embedding=rec.get("embedding"),
        )
    # Give a tiny sleep so timestamps differ for ordering tests
    await asyncio.sleep(0.01)


# ── list_records pagination ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_mem_list_records_pagination(sql_mem_store):
    """6.1: list_records respects limit and offset for pagination."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2"},
        {"user_id": "alice", "question": "q3", "sql": "SELECT 3"},
        {"user_id": "alice", "question": "q4", "sql": "SELECT 4"},
        {"user_id": "alice", "question": "q5", "sql": "SELECT 5"},
    ])

    # First page: limit=2, offset=0
    page1 = await sql_mem_store.list_records(user_id="alice", limit=2, offset=0)
    assert len(page1) == 2

    # Second page: limit=2, offset=2
    page2 = await sql_mem_store.list_records(user_id="alice", limit=2, offset=2)
    assert len(page2) == 2

    # Third page: limit=2, offset=4
    page3 = await sql_mem_store.list_records(user_id="alice", limit=2, offset=4)
    assert len(page3) == 1

    # No overlap
    page1_ids = {r["id"] for r in page1}
    page2_ids = {r["id"] for r in page2}
    page3_ids = {r["id"] for r in page3}
    assert page1_ids.isdisjoint(page2_ids)
    assert page1_ids.isdisjoint(page3_ids)
    assert page2_ids.isdisjoint(page3_ids)


@pytest.mark.asyncio
async def test_sql_mem_list_records_empty(sql_mem_store):
    """6.1: list_records returns empty list when no records match."""
    results = await sql_mem_store.list_records(user_id="nobody")
    assert results == []


@pytest.mark.asyncio
async def test_sql_mem_list_records_field_structure(sql_mem_store):
    """6.1: list_records returns records with expected fields."""
    await _seed_sql_mem_records(sql_mem_store, [
        {
            "user_id": "alice", "question": "find users",
            "sql": "SELECT * FROM users",
            "table_names": ["users"],
            "database_name": "mydb", "schema_id": 42,
            "execution_status": "success",
        },
    ])

    results = await sql_mem_store.list_records(user_id="alice")
    assert len(results) == 1
    r = results[0]
    assert "id" in r
    assert r["user_id"] == "alice"
    assert r["question"] == "find users"
    assert r["sql_text"] == "SELECT * FROM users"
    assert r["table_names"] == ["users"]
    assert r["database_name"] == "mydb"
    assert r["schema_id"] == 42
    assert r["execution_status"] == "success"
    assert "created_at" in r
    assert "has_embedding" in r


# ── count_records combo filtering ───────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_mem_count_records_no_filter(sql_mem_store):
    """6.2: count_records with no filters returns total count."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1"},
        {"user_id": "bob", "question": "q2", "sql": "SELECT 2"},
        {"user_id": "charlie", "question": "q3", "sql": "SELECT 3"},
    ])

    count = await sql_mem_store.count_records()
    assert count == 3


@pytest.mark.asyncio
async def test_sql_mem_count_records_filter_by_user(sql_mem_store):
    """6.2: count_records filters by user_id."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2"},
        {"user_id": "bob", "question": "q3", "sql": "SELECT 3"},
    ])

    assert await sql_mem_store.count_records(user_id="alice") == 2
    assert await sql_mem_store.count_records(user_id="bob") == 1


@pytest.mark.asyncio
async def test_sql_mem_count_records_filter_by_database(sql_mem_store):
    """6.2: count_records filters by database_name."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "database_name": "db_a"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "database_name": "db_a"},
        {"user_id": "alice", "question": "q3", "sql": "SELECT 3",
         "database_name": "db_b"},
    ])

    assert await sql_mem_store.count_records(database_name="db_a") == 2
    assert await sql_mem_store.count_records(database_name="db_b") == 1


@pytest.mark.asyncio
async def test_sql_mem_count_records_filter_by_status(sql_mem_store):
    """6.2: count_records filters by execution_status."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "execution_status": "success"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "execution_status": "error"},
        {"user_id": "alice", "question": "q3", "sql": "SELECT 3",
         "execution_status": "success"},
    ])

    assert await sql_mem_store.count_records(status="success") == 2
    assert await sql_mem_store.count_records(status="error") == 1


@pytest.mark.asyncio
async def test_sql_mem_count_records_combo_filter(sql_mem_store):
    """6.2: count_records with combined status+database+user filters."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "database_name": "db_a", "execution_status": "success"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "database_name": "db_a", "execution_status": "error"},
        {"user_id": "alice", "question": "q3", "sql": "SELECT 3",
         "database_name": "db_b", "execution_status": "success"},
        {"user_id": "bob", "question": "q4", "sql": "SELECT 4",
         "database_name": "db_a", "execution_status": "success"},
    ])

    count = await sql_mem_store.count_records(
        user_id="alice", database_name="db_a", status="success",
    )
    assert count == 1


@pytest.mark.asyncio
async def test_sql_mem_count_records_empty(sql_mem_store):
    """6.2: count_records returns 0 on empty store."""
    assert await sql_mem_store.count_records() == 0


# ── delete_records safety invariant ─────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_mem_delete_records_all_empty_no_older_returns_zero(sql_mem_store):
    """6.3: delete_records with all filters empty and no older_than_days returns 0."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1"},
        {"user_id": "bob", "question": "q2", "sql": "SELECT 2"},
    ])

    deleted = await sql_mem_store.delete_records(
        user_id="", database_name="", status="", older_than_days=None,
    )
    assert deleted == 0

    # Verify all records still exist
    count = await sql_mem_store.count_records()
    assert count == 2


@pytest.mark.asyncio
async def test_sql_mem_delete_records_by_user(sql_mem_store):
    """6.3: delete_records with user_id filter deletes only that user's records."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2"},
        {"user_id": "bob", "question": "q3", "sql": "SELECT 3"},
    ])

    deleted = await sql_mem_store.delete_records(user_id="alice")
    assert deleted == 2

    count = await sql_mem_store.count_records()
    assert count == 1


@pytest.mark.asyncio
async def test_sql_mem_delete_records_by_database(sql_mem_store):
    """6.3: delete_records with database_name filter deletes only matching records."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "database_name": "db_a"},
        {"user_id": "bob", "question": "q2", "sql": "SELECT 2",
         "database_name": "db_a"},
        {"user_id": "bob", "question": "q3", "sql": "SELECT 3",
         "database_name": "db_b"},
    ])

    deleted = await sql_mem_store.delete_records(database_name="db_a")
    assert deleted == 2

    count = await sql_mem_store.count_records()
    assert count == 1


@pytest.mark.asyncio
async def test_sql_mem_delete_records_by_status(sql_mem_store):
    """6.3: delete_records with status filter."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "execution_status": "success"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "execution_status": "error"},
    ])

    deleted = await sql_mem_store.delete_records(status="error")
    assert deleted == 1

    count = await sql_mem_store.count_records()
    assert count == 1


# ── SQLite-specific: table_names JSON parsing ───────────────────────────


@pytest_asyncio.fixture
async def sqlite_sql_mem():
    """Dedicated SqliteSqlMemoryStore fixture for SQLite-specific tests."""
    s = SqliteSqlMemoryStore(":memory:")
    await s.initialize()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_sqlite_table_names_normal_parse(sqlite_sql_mem):
    """6.4: get_stats_summary correctly parses JSON table_names."""
    await _seed_sql_mem_records(sqlite_sql_mem, [
        {
            "user_id": "alice", "question": "count users",
            "sql": "SELECT COUNT(*) FROM users",
            "table_names": ["users"],
            "database_name": "mydb",
        },
        {
            "user_id": "alice", "question": "join orders",
            "sql": "SELECT * FROM users JOIN orders ON users.id=orders.user_id",
            "table_names": ["users", "orders"],
            "database_name": "mydb",
        },
    ])

    summary = await sqlite_sql_mem.get_stats_summary(database_name="mydb")
    assert "table_distribution" in summary
    td = summary["table_distribution"]
    assert td.get("users") == 2
    assert td.get("orders") == 1


@pytest.mark.asyncio
async def test_sqlite_table_names_failed_parse_skips_table_distribution(sqlite_sql_mem):
    """6.4: get_stats_summary skips table distribution on JSON parse failure
    but still counts the record in other stats."""
    # Insert a record directly with corrupted table_names JSON
    await sqlite_sql_mem.record(
        user_id="alice",
        question="broken json",
        sql="SELECT 1",
        table_names=["users"],
        database_name="mydb",
        schema_id=1,
        execution_result={"execution_status": "success"},
        embedding=None,
    )

    # Manually corrupt the table_names JSON in the DB
    import aiosqlite
    # We need a separate connection to modify the data directly
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("ATTACH DATABASE ':memory:' AS mem2")
    # Actually, SQLite :memory: databases are per-connection.
    # We'll use the store's own connection to corrupt the data.
    await sqlite_sql_mem._conn.execute(
        "UPDATE sql_memories SET table_names = 'not-valid-json' WHERE user_id = 'alice'"
    )
    await sqlite_sql_mem._conn.commit()

    # Add a second record with valid table_names
    await _seed_sql_mem_records(sqlite_sql_mem, [
        {
            "user_id": "bob", "question": "valid record",
            "sql": "SELECT * FROM orders",
            "table_names": ["orders"],
            "database_name": "mydb2",
        },
    ])

    summary = await sqlite_sql_mem.get_stats_summary()
    assert summary["total_records"] == 2  # both records counted
    # table_distribution only has "orders"
    td = summary["table_distribution"]
    assert td.get("orders") == 1
    # "users" should NOT appear because the corrupted record was skipped
    assert "users" not in td


# ── SQLite-specific: WHERE correctness for combo filtering ──────────────


@pytest.mark.asyncio
async def test_sqlite_count_records_combo_where(sqlite_sql_mem):
    """6.5: count_records produces correct SQL WHERE for status/database/user combo."""
    await _seed_sql_mem_records(sqlite_sql_mem, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "database_name": "db_a", "execution_status": "success"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "database_name": "db_a", "execution_status": "error"},
        {"user_id": "bob", "question": "q3", "sql": "SELECT 3",
         "database_name": "db_a", "execution_status": "success"},
        {"user_id": "alice", "question": "q4", "sql": "SELECT 4",
         "database_name": "db_b", "execution_status": "success"},
    ])

    # All three filters
    c1 = await sqlite_sql_mem.count_records(
        user_id="alice", database_name="db_a", status="success",
    )
    assert c1 == 1

    # Two filters: user + database
    c2 = await sqlite_sql_mem.count_records(
        user_id="alice", database_name="db_a",
    )
    assert c2 == 2

    # Two filters: database + status
    c3 = await sqlite_sql_mem.count_records(
        database_name="db_a", status="success",
    )
    assert c3 == 2

    # Two filters: user + status
    c4 = await sqlite_sql_mem.count_records(
        user_id="alice", status="success",
    )
    assert c4 == 2


@pytest.mark.asyncio
async def test_sqlite_list_records_combo_where(sqlite_sql_mem):
    """6.5: list_records produces correct SQL WHERE for combo filtering."""
    await _seed_sql_mem_records(sqlite_sql_mem, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "database_name": "db_a", "execution_status": "success"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "database_name": "db_a", "execution_status": "error"},
        {"user_id": "bob", "question": "q3", "sql": "SELECT 3",
         "database_name": "db_a", "execution_status": "success"},
    ])

    results = await sqlite_sql_mem.list_records(
        user_id="bob", database_name="db_a", status="success",
    )
    assert len(results) == 1
    assert results[0]["user_id"] == "bob"
    assert results[0]["database_name"] == "db_a"
    assert results[0]["execution_status"] == "success"


# ── get_status_summary ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_mem_get_status_summary_structure(sql_mem_store):
    """6.6: get_status_summary returns expected result structure."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "execution_status": "success"},
        {"user_id": "alice", "question": "q2", "sql": "SELECT 2",
         "execution_status": "error"},
        {"user_id": "bob", "question": "q3", "sql": "SELECT 3",
         "execution_status": "success"},
    ])

    summary = await sql_mem_store.get_status_summary()

    assert "total_records" in summary
    assert summary["total_records"] == 3
    assert "embedding_coverage" in summary
    assert "status_breakdown" in summary
    assert "oldest_record" in summary
    assert "newest_record" in summary

    # status_breakdown should have "success" and "error"
    status_bd = summary["status_breakdown"]
    assert status_bd.get("success") == 2
    assert status_bd.get("error") == 1


@pytest.mark.asyncio
async def test_sql_mem_get_status_summary_empty(sql_mem_store):
    """6.6: get_status_summary returns appropriate structure for empty store."""
    summary = await sql_mem_store.get_status_summary()

    assert summary["total_records"] == 0
    assert summary["embedding_coverage"] == 0.0
    assert summary["status_breakdown"] == {}
    assert summary["oldest_record"] is None
    assert summary["newest_record"] is None


@pytest.mark.asyncio
async def test_sql_mem_get_status_summary_with_filters(sql_mem_store):
    """6.6: get_status_summary with user_id filter."""
    await _seed_sql_mem_records(sql_mem_store, [
        {"user_id": "alice", "question": "q1", "sql": "SELECT 1",
         "execution_status": "success"},
        {"user_id": "bob", "question": "q2", "sql": "SELECT 2",
         "execution_status": "success"},
    ])

    summary = await sql_mem_store.get_status_summary(user_id="alice")
    assert summary["total_records"] == 1


# ── get_stats_summary ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_mem_get_stats_summary_structure(sql_mem_store):
    """6.6: get_stats_summary returns expected result structure."""
    await _seed_sql_mem_records(sql_mem_store, [
        {
            "user_id": "alice", "question": "count users",
            "sql": "SELECT COUNT(*) FROM users",
            "table_names": ["users"],
            "database_name": "mydb",
        },
        {
            "user_id": "bob", "question": "list orders",
            "sql": "SELECT * FROM orders",
            "table_names": ["orders"],
            "database_name": "mydb",
        },
        {
            "user_id": "alice", "question": "join query",
            "sql": "SELECT * FROM users JOIN orders ON users.id=orders.user_id",
            "table_names": ["users", "orders"],
            "database_name": "otherdb",
        },
    ])

    summary = await sql_mem_store.get_stats_summary()

    assert "total_records" in summary
    assert summary["total_records"] == 3
    assert "table_distribution" in summary
    assert "database_distribution" in summary
    assert "daily_histogram" in summary

    # table_distribution
    td = summary["table_distribution"]
    assert td.get("users") == 2
    assert td.get("orders") == 2

    # database_distribution
    dd = summary["database_distribution"]
    assert dd.get("mydb") == 2
    assert dd.get("otherdb") == 1

    # mined_patterns should be None when no specific database_name is provided
    assert summary["mined_patterns"] is None


@pytest.mark.asyncio
async def test_sql_mem_get_stats_summary_empty(sql_mem_store):
    """6.6: get_stats_summary returns appropriate structure for empty store."""
    summary = await sql_mem_store.get_stats_summary()

    assert summary["total_records"] == 0
    assert summary["table_distribution"] == {}
    assert summary["database_distribution"] == {}
    assert summary["daily_histogram"] == {}
    assert summary["mined_patterns"] is None


# ============================================================================
# Task 11.5: StorageBackend stats unit tests
# ============================================================================


@pytest_asyncio.fixture(params=["InMemoryStore", "SqliteStore"])
async def any_session_store(request):
    """Parametrized fixture yielding both session store backends."""
    if request.param == "InMemoryStore":
        s = InMemoryStore()
        await s.initialize()
        yield s
        await s.close()
    else:
        s = SqliteStore(":memory:")
        await s.initialize()
        yield s
        await s.close()


@pytest.mark.asyncio
async def test_session_store_count_sessions_empty(any_session_store):
    """8.1: count_sessions returns 0 on empty store."""
    assert await any_session_store.count_sessions() == 0


@pytest.mark.asyncio
async def test_session_store_count_sessions_basic(any_session_store):
    """8.1: count_sessions returns total sessions across all users."""
    await any_session_store.create_session("alice", "sess-1", {"summary": "a1"})
    await any_session_store.create_session("alice", "sess-2", {"summary": "a2"})
    await any_session_store.create_session("bob", "sess-1", {"summary": "b1"})

    assert await any_session_store.count_sessions() == 3


@pytest.mark.asyncio
async def test_session_store_count_sessions_after_delete(any_session_store):
    """8.1: count_sessions decreases after session deletion."""
    await any_session_store.create_session("alice", "sess-1", {"summary": "a1"})
    await any_session_store.create_session("alice", "sess-2", {"summary": "a2"})

    assert await any_session_store.count_sessions() == 2

    await any_session_store.delete_session("alice", "sess-1")
    assert await any_session_store.count_sessions() == 1


@pytest.mark.asyncio
async def test_session_store_count_distinct_users_empty(any_session_store):
    """8.2: count_distinct_users returns 0 on empty store."""
    assert await any_session_store.count_distinct_users() == 0


@pytest.mark.asyncio
async def test_session_store_count_distinct_users_basic(any_session_store):
    """8.2: count_distinct_users returns distinct user count."""
    await any_session_store.create_session("alice", "sess-1", {"summary": "a1"})
    await any_session_store.create_session("alice", "sess-2", {"summary": "a2"})
    await any_session_store.create_session("bob", "sess-1", {"summary": "b1"})
    await any_session_store.create_session("charlie", "sess-1", {"summary": "c1"})

    assert await any_session_store.count_distinct_users() == 3


@pytest.mark.asyncio
async def test_session_store_count_distinct_users_after_delete_all(any_session_store):
    """8.2: count_distinct_users decreases after deleting all of a user's sessions."""
    await any_session_store.create_session("alice", "sess-1", {"summary": "a1"})
    await any_session_store.create_session("bob", "sess-1", {"summary": "b1"})

    assert await any_session_store.count_distinct_users() == 2

    await any_session_store.delete_session("alice", "sess-1")
    assert await any_session_store.count_distinct_users() == 1


@pytest.mark.asyncio
async def test_session_store_counts_consistency(any_session_store):
    """8.3: count_sessions and count_distinct_users remain consistent."""
    # Empty
    assert await any_session_store.count_sessions() == 0
    assert await any_session_store.count_distinct_users() == 0

    # One user, one session
    await any_session_store.create_session("alice", "sess-1", {"summary": "a1"})
    assert await any_session_store.count_sessions() == 1
    assert await any_session_store.count_distinct_users() == 1

    # Same user, additional session
    await any_session_store.create_session("alice", "sess-2", {"summary": "a2"})
    assert await any_session_store.count_sessions() == 2
    assert await any_session_store.count_distinct_users() == 1

    # New user
    await any_session_store.create_session("bob", "sess-1", {"summary": "b1"})
    assert await any_session_store.count_sessions() == 3
    assert await any_session_store.count_distinct_users() == 2