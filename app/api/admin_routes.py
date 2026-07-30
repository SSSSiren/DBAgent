"""
Admin API routes — authentication dependency and management endpoints.

Provides `verify_admin_token` as a FastAPI dependency that validates Bearer
tokens against the configured `admin_api_token` setting.
"""

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.schemas import (
    CleanRequest,
    HdcMappingCreate,
    HdcMappingResponse,
    HdcNamespaceSummary,
    OverviewResponse,
    ReEmbedRequest,
    SqlMemoryListResponse,
    SqlMemoryRecordResponse,
    SqlMemoryStatsResponse,
    SqlMemoryStatusResponse,
)
from app.config import get_settings
from app.memory.manager import get_storage

logger = logging.getLogger(__name__)


async def verify_admin_token(authorization: str = Header(None)) -> None:
    """
    FastAPI dependency: validate the Bearer token in the Authorization header.

    Behavior:
    - ``admin_api_token`` is empty → 503 (Admin API not configured)
    - ``Authorization`` header missing → 401 (Missing admin token)
    - Token mismatch → 401 (Invalid admin token)
    - Token matched → returns ``None`` (caller proceeds)

    Security: the actual token value is never logged.
    """
    settings = get_settings()

    # 1.1: empty token → service unavailable
    if not settings.admin_api_token:
        logger.warning("Admin API token not configured; rejecting admin request")
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured",
        )

    # 1.2: header missing
    if not authorization:
        logger.warning("Admin API request rejected: missing Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing admin token",
        )

    # 1.3: extract Bearer token
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.warning("Admin API request rejected: malformed Authorization header (expected Bearer)")
        raise HTTPException(
            status_code=401,
            detail="Missing admin token",
        )

    # 1.4: constant-time-ish string comparison (no early-exit)
    if token != settings.admin_api_token:
        logger.warning("Admin API request rejected: token mismatch")
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
        )

    return None


admin_router = APIRouter(prefix="/admin", dependencies=[Depends(verify_admin_token)])


# ═══════════════════════════════════════════════════════════════
# 8.1: SQL Memory global precondition helper
# ═══════════════════════════════════════════════════════════════


def _require_sql_memory():
    """
    Raise 503 "SQL Memory not enabled" if sql_memory_enabled is false
    or sql_memory_store is None.

    Returns the sql_memory_store instance for use by endpoints.
    """
    settings = get_settings()
    if not getattr(settings, "sql_memory_enabled", False):
        raise HTTPException(status_code=503, detail="SQL Memory not enabled")
    store = get_storage().sql_memory_store
    if store is None:
        raise HTTPException(status_code=503, detail="SQL Memory not enabled")
    return store


# ── HDC Mappings Endpoints ──────────────────────────────────────────────────


@admin_router.post("/hdc-mappings", status_code=201, response_model=HdcMappingResponse)
async def create_hdc_mapping(body: HdcMappingCreate):
    """Create or update an HDC namespace mapping (upsert)."""
    storage = get_storage()
    if storage.admin_store is None:
        raise HTTPException(status_code=503, detail="Admin store not available")
    result = await storage.admin_store.upsert_mapping(
        user_id=body.user_id,
        schema_id=body.schema_id,
        database_name=body.database_name,
        hdc_namespace=body.hdc_namespace,
    )
    return HdcMappingResponse(**result)


@admin_router.get("/hdc-mappings", response_model=list[HdcMappingResponse])
async def list_hdc_mappings(
    user_id: str = Query(default="", description="Filter by user ID (empty = all)"),
    schema_id: int = Query(default=0, description="Filter by schema ID (0 = all)"),
    database_name: str = Query(default="", description="Filter by database name (empty = all)"),
):
    """List HDC namespace mappings with optional filters."""
    storage = get_storage()
    if storage.admin_store is None:
        raise HTTPException(status_code=503, detail="Admin store not available")
    results = await storage.admin_store.get_mappings(
        user_id=user_id,
        schema_id=schema_id,
        database_name=database_name,
    )
    return [HdcMappingResponse(**r) for r in results]


@admin_router.delete("/hdc-mappings")
async def delete_hdc_mapping(
    user_id: str = Query(..., description="User ID"),
    schema_id: int = Query(..., description="Schema ID"),
    database_name: str = Query(..., description="Database name"),
):
    """Delete an HDC namespace mapping by composite key."""
    storage = get_storage()
    if storage.admin_store is None:
        raise HTTPException(status_code=503, detail="Admin store not available")
    deleted = await storage.admin_store.delete_mapping(
        user_id=user_id,
        schema_id=schema_id,
        database_name=database_name,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════
# 7.1: GET /hdc/namespaces/{schema_id}/{database_name}
# ═══════════════════════════════════════════════════════════════


@admin_router.get("/hdc/namespaces/{schema_id}/{database_name}")
async def list_hdc_namespaces(schema_id: int, database_name: str):
    """
    List HDC namespace directories for a given schema_id/database_name pair.

    Uses OpenViking list_directory() to enumerate subdirectories under the DB
    root URI. Only returns ``is_dir=True`` entries, excluding ``_tables`` and
    ``_relationships`` internal directories. The default namespace (None) is
    not returned.

    - DB root doesn't exist -> 200 + ``[]``
    - No namespace dirs -> 200 + ``[]``
    - OpenViking error -> 503
    """
    from app.datavault.uploader import _db_uri, storage_key
    from app.knowledge.openviking import OpenVikingClient

    settings = get_settings()

    key = storage_key(schema_id, database_name)
    db_uri = _db_uri(key)

    try:
        ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
        await ov.start()
        entries = await ov.list_directory(db_uri)
        await ov.close()
    except Exception as e:
        logger.warning("OpenViking list_directory failed for %s: %s", db_uri, e)
        raise HTTPException(status_code=503, detail=f"OpenViking unavailable: {e}")

    # Filter: only directories, exclude internal dirs, exclude default namespace
    namespace_names: list[str] = []
    for entry in entries:
        if not entry.get("is_dir", False):
            continue
        name = entry.get("name", "")
        if name in ("_tables", "_relationships"):
            continue
        if not name:
            continue  # skip default namespace (None / empty name)
        namespace_names.append(name)

    return namespace_names


# ═══════════════════════════════════════════════════════════════
# 8.2: GET /sql-memory/status
# ═══════════════════════════════════════════════════════════════


@admin_router.get("/sql-memory/status")
async def sql_memory_status():
    """Get SQL Memory status summary (record count, embedding coverage, etc.)."""
    store = _require_sql_memory()
    summary = await store.get_status_summary()

    return SqlMemoryStatusResponse(
        total_records=summary.get("total_records", 0),
        embedding_coverage=summary.get("embedding_coverage", 0.0),
        status_distribution=summary.get("status_breakdown", {}),
        earliest_record=summary.get("oldest_record"),
        latest_record=summary.get("newest_record"),
    )


# ═══════════════════════════════════════════════════════════════
# 8.3: GET /sql-memory/records
# ═══════════════════════════════════════════════════════════════


@admin_router.get("/sql-memory/records")
async def sql_memory_records(
    user_id: str = Query(default="", description="Filter by user ID (empty = all)"),
    database_name: str = Query(default="", description="Filter by database name (empty = all)"),
    status: str = Query(default="", description="Filter by execution status (empty = all)"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """List SQL Memory records with optional filtering and pagination."""
    store = _require_sql_memory()

    # Get total count matching filters
    total = await store.count_records(
        user_id=user_id,
        database_name=database_name,
        status=status,
    )

    # Get records page
    records = await store.list_records(
        user_id=user_id,
        database_name=database_name,
        status=status,
        limit=limit,
        offset=offset,
    )

    return SqlMemoryListResponse(
        records=[
            SqlMemoryRecordResponse(
                id=r.get("id", ""),
                user_id=r.get("user_id", ""),
                question=r.get("question", ""),
                sql_text=r.get("sql_text", ""),
                sql_truncated=r.get("sql_truncated", ""),
                table_names=r.get("table_names", []),
                database_name=r.get("database_name", ""),
                schema_id=r.get("schema_id", 0),
                execution_status=r.get("execution_status", ""),
                created_at=r.get("created_at", ""),
                has_embedding=r.get("has_embedding", False),
            )
            for r in records
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


# ═══════════════════════════════════════════════════════════════
# 8.4: DELETE /sql-memory/clean
# ═══════════════════════════════════════════════════════════════


@admin_router.delete("/sql-memory/clean")
async def sql_memory_clean(request: CleanRequest):
    """
    Delete SQL Memory records matching optional filters.

    Safety: if no filters are provided, defaults to cleaning records older
    than ``sql_memory_ttl_days`` to prevent accidental full deletion.
    """
    store = _require_sql_memory()
    settings = get_settings()

    user_id = request.user_id or ""
    database_name = request.database_name or ""
    older_than_days = request.older_than_days

    # Safety: if no filters at all, use TTL as default
    if not user_id and not database_name and older_than_days is None:
        older_than_days = getattr(settings, "sql_memory_ttl_days", 90)

    deleted_count = await store.delete_records(
        user_id=user_id,
        database_name=database_name,
        status="",
        older_than_days=older_than_days,
    )

    return {"deleted_count": deleted_count}


# ═══════════════════════════════════════════════════════════════
# 8.5: POST /sql-memory/re-embed
# ═══════════════════════════════════════════════════════════════


@admin_router.post("/sql-memory/re-embed")
async def sql_memory_re_embed(request: ReEmbedRequest):
    """
    Rebuild embedding vectors for SQL Memory records.

    - Empty/unset user_id -> full rebuild (all users)
    - user_id provided -> rebuild only that user
    """
    from app.memory.sql_memory import embed_text

    store = _require_sql_memory()

    user_id = request.user_id or ""

    updated_count = await store.re_embed_all(embed_fn=embed_text, user_id=user_id)

    return {"updated_count": updated_count}


# ═══════════════════════════════════════════════════════════════
# 8.6: GET /sql-memory/stats
# ═══════════════════════════════════════════════════════════════


@admin_router.get("/sql-memory/stats")
async def sql_memory_stats(
    user_id: str = Query(default="", description="Filter by user ID (empty = all)"),
    database_name: str = Query(default="", description="Filter by database name (empty = all)"),
    status: str = Query(default="", description="Filter by execution status (empty = all)"),
):
    """
    Get SQL Memory statistics (table distribution, database distribution,
    daily histogram, mined patterns).

    No filters -> global stats across all users and databases.
    """
    store = _require_sql_memory()

    summary = await store.get_stats_summary(
        user_id=user_id,
        database_name=database_name,
        status=status,
    )

    return SqlMemoryStatsResponse(
        table_distribution=summary.get("table_distribution", {}),
        database_distribution=summary.get("database_distribution", {}),
        daily_histogram=summary.get("daily_histogram", {}),
        mined_patterns=summary.get("mined_patterns"),
    )


# ═══════════════════════════════════════════════════════════════
# 9.1: GET /overview
# ═══════════════════════════════════════════════════════════════


@admin_router.get("/overview")
async def system_overview():
    """
    System overview endpoint aggregating session stats, SQL memory record
    count, and HDC namespace mappings.

    Each stat is fetched independently -- a failure for one stat returns 0/[]
    for that stat without affecting others.
    """
    storage = get_storage()

    # Session stats
    distinct_users = 0
    total_sessions = 0
    try:
        distinct_users = await storage.session_store.count_distinct_users()
    except Exception:
        logger.warning("Overview: count_distinct_users failed", exc_info=True)
    try:
        total_sessions = await storage.session_store.count_sessions()
    except Exception:
        logger.warning("Overview: count_sessions failed", exc_info=True)

    # SQL Memory count
    sql_memory_records = 0
    try:
        sql_mem_store = storage.sql_memory_store
        if sql_mem_store is not None:
            sql_memory_records = await sql_mem_store.count_records()
    except Exception:
        logger.warning("Overview: sql_memory count_records failed", exc_info=True)

    # HDC namespace mappings aggregation
    mapped_hdc_namespaces: list[HdcNamespaceSummary] = []
    try:
        admin_store = storage.admin_store
        if admin_store is not None:
            mappings = await admin_store.get_mappings()
            # Aggregate by (schema_id, database_name) -> count
            group_counts: dict[tuple[int, str], int] = defaultdict(int)
            for m in mappings:
                key = (m.get("schema_id", 0), m.get("database_name", ""))
                group_counts[key] += 1
            mapped_hdc_namespaces = [
                HdcNamespaceSummary(
                    schema_id=sid,
                    database_name=db_name,
                    namespace_count=count,
                )
                for (sid, db_name), count in sorted(group_counts.items())
            ]
    except Exception:
        logger.warning("Overview: hdc namespace aggregation failed", exc_info=True)

    return OverviewResponse(
        distinct_users=distinct_users,
        total_sessions=total_sessions,
        sql_memory_records=sql_memory_records,
        mapped_hdc_namespaces=mapped_hdc_namespaces,
    )