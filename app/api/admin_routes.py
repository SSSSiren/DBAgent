"""
Admin API routes — authentication dependency and management endpoints.

Provides `verify_admin_token` as a FastAPI dependency that validates Bearer
tokens against the configured `admin_api_token` setting.
"""

import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.schemas import (
    CleanRequest,
    HdcMappingCreate,
    HdcMappingResponse,
    HdcNamespaceSummary,
    OverviewResponse,
    ReEmbedRequest,
    SeedSqlMemoryRequest,
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


@admin_router.delete("/sql-memory/records/{record_id}")
async def sql_memory_delete_one(record_id: str):
    """按记录 ID 删除单条 SQL 记忆记录。"""
    store = _require_sql_memory()
    deleted = await store.delete_record_by_id(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"deleted": True, "record_id": record_id}


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

    # ── Session stats ──
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

    # ── SQL Memory count ──
    sql_memory_records = 0
    try:
        sql_mem_store = storage.sql_memory_store
        if sql_mem_store is not None:
            sql_memory_records = await sql_mem_store.count_records()
    except Exception:
        logger.warning("Overview: sql_memory count_records failed", exc_info=True)

    # ── HDC namespace mappings aggregation ──
    mapped_hdc_namespaces: list[HdcNamespaceSummary] = []
    try:
        admin_store = storage.admin_store
        if admin_store is not None:
            mappings = await admin_store.get_mappings()
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


@admin_router.post("/sql-memory/seed")
async def seed_sql_memory(request: SeedSqlMemoryRequest) -> dict:
    """批量灌入 SQL Memory 记录。

    为指定用户批量写入 SQL 记忆记录，每条记录自动生成 embedding。
    适用于评测数据灌入、冷启动数据填充等场景。
    """
    store = _require_sql_memory()

    from app.memory.sql_memory import embed_text

    success_count = 0
    fail_count = 0
    for i, rec in enumerate(request.records):
        try:
            question = rec.get("question", "")
            sql = rec.get("sql", "")
            table_names = rec.get("table_names", [])
            database_name = rec.get("database_name", "")
            schema_id = rec.get("schema_id", 0)
            execution_result = rec.get("execution_result", {})

            if not question or not sql:
                fail_count += 1
                logger.warning(f"Seed record {i}: missing question or sql, skipped")
                continue

            embedding = await embed_text(question)
            await store.record(
                user_id=request.user_id,
                question=question,
                sql=sql,
                table_names=table_names,
                database_name=database_name,
                schema_id=schema_id,
                execution_result=execution_result,
                embedding=embedding,
            )
            success_count += 1
        except Exception:
            fail_count += 1
            logger.warning(f"Seed record {i}: failed", exc_info=True)

    return {
        "user_id": request.user_id,
        "total": len(request.records),
        "success": success_count,
        "failed": fail_count,
    }


@admin_router.get("/options/users")
async def list_known_users() -> list[str]:
    """返回系统中出现过的所有用户。

    数据来源：sessions + admin mappings + sql_memories + OpenViking。
    OpenViking 仅作为补充来源——如果用户只存在于 OpenViking 但无任何实际数据，则不出现在列表中。
    """
    users = set()
    confirmed = set()  # 来自 sessions / mappings / sql_memories 的"已确认"用户

    # 从 sessions（最全面的来源——每个对话过的人都有 session）
    try:
        storage = get_storage()
        sess_store = storage.session_store
        if sess_store is not None:
            if hasattr(sess_store, "_conn") and sess_store._conn is not None:
                cursor = await sess_store._conn.execute("SELECT DISTINCT user_id FROM sessions")
                rows = await cursor.fetchall()
                for row in rows:
                    uid = row[0] if isinstance(row, tuple) else row["user_id"]
                    if uid:
                        users.add(uid)
                        confirmed.add(uid)
    except Exception:
        logger.warning("Options: failed to load sessions", exc_info=True)

    # 从 admin mappings
    try:
        storage = get_storage()
        if storage.admin_store:
            mappings = await storage.admin_store.get_mappings()
            for m in mappings:
                uid = m["user_id"]
                users.add(uid)
                confirmed.add(uid)
    except Exception:
        logger.warning("Options: failed to load admin mappings", exc_info=True)

    # 从 sql_memories
    try:
        store = get_storage().sql_memory_store
        if store is not None:
            records = await store.list_records(limit=1000)
            for r in records:
                uid = r.get("user_id", "")
                if uid:
                    users.add(uid)
                    confirmed.add(uid)
    except Exception:
        pass  # SQL memory may be disabled

    # 从 OpenViking（仅补充——只添加"已确认"用户的 OpenViking 目录，不引入仅存在于 OpenViking 的孤立用户）
    try:
        from app.config import get_settings
        from app.knowledge.openviking import OpenVikingClient
        settings = get_settings()
        if settings.kb_enabled:
            ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
            await ov.start()
            try:
                entries = await ov.list_directory("viking://user")
                for entry in entries:
                    if entry.get("is_dir") and entry.get("name"):
                        ov_user = entry["name"]
                        if ov_user in confirmed:
                            users.add(ov_user)
            finally:
                await ov.close()
    except Exception:
        pass  # OpenViking may be unavailable

    return sorted([u for u in users if u])


@admin_router.get("/options/schemas")
async def list_known_schemas() -> list[dict]:
    """返回系统中出现过的所有 (schema_id, database_name) 组合。

    数据来源：HDC 文件系统 + admin mappings + sql_memories。
    """
    schemas: dict[str, dict] = {}  # key = f"{schema_id}/{database_name}"

    # 从 HDC 文件系统（最全面的来源——扫描所有已生成的知识库目录）
    try:
        from app.config import get_settings
        from app.knowledge.openviking import OpenVikingClient
        settings = get_settings()
        if settings.kb_enabled:
            ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
            await ov.start()
            try:
                schema_entries = await ov.list_directory("viking://resources/hdc")
                for schema_entry in schema_entries:
                    if not schema_entry.get("is_dir") or not schema_entry.get("name"):
                        continue
                    schema_name = schema_entry["name"]
                    # 跳过非数字 schema ID（如 l0test、test_smoke）
                    try:
                        schema_id = int(schema_name)
                    except (ValueError, TypeError):
                        continue
                    db_entries = await ov.list_directory(schema_entry["uri"])
                    for db_entry in db_entries:
                        if not db_entry.get("is_dir") or not db_entry.get("name"):
                            continue
                        db_name = db_entry["name"]
                        key = f"{schema_id}/{db_name}"
                        schemas[key] = {"schema_id": schema_id, "database_name": db_name}
            finally:
                await ov.close()
    except Exception:
        pass  # OpenViking may be unavailable

    # 从 admin mappings
    try:
        storage = get_storage()
        if storage.admin_store:
            mappings = await storage.admin_store.get_mappings()
            for m in mappings:
                sid = m.get("schema_id", 0)
                db = m.get("database_name", "")
                if sid and db:
                    key = f"{sid}/{db}"
                    schemas[key] = {"schema_id": sid, "database_name": db}
    except Exception:
        logger.warning("Options: failed to load admin mappings", exc_info=True)

    # 从 sql_memories
    try:
        store = get_storage().sql_memory_store
        if store is not None:
            records = await store.list_records(limit=1000)
            for r in records:
                sid = r.get("schema_id", 0)
                db = r.get("database_name", "")
                if sid and db:
                    key = f"{sid}/{db}"
                    schemas[key] = {"schema_id": sid, "database_name": db}
    except Exception:
        pass

    return sorted(schemas.values(), key=lambda x: (x["schema_id"], x["database_name"]))


class PurgeUsersRequest(BaseModel):
    """批量注销用户请求"""
    user_ids: list[str] = Field(..., min_length=1, description="要注销的用户列表")
    delete_sessions: bool = Field(default=True, description="是否删除会话")
    delete_mappings: bool = Field(default=True, description="是否删除 HDC 映射")
    delete_sql_memories: bool = Field(default=True, description="是否删除 SQL 记忆")


async def _retry_on_lock(fn, *args, max_retries=5, delay=0.3, **kwargs):
    """SQLite 写锁冲突时自动重试的回调包装器。"""
    for attempt in range(max_retries):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                await asyncio.sleep(delay * (attempt + 1))  # 0.3, 0.6, 0.9, 1.2, 1.5
                continue
            raise


@admin_router.post("/users/purge")
async def purge_users(request: PurgeUsersRequest) -> dict:
    """批量注销用户：删除指定用户的会话、HDC 映射、SQL 记忆和 OpenViking 数据。

    返回每个维度的删除数量以及成功注销的用户列表。
    """
    results = {
        "deleted_sessions": 0,
        "deleted_mappings": 0,
        "deleted_sql_memories": 0,
        "deleted_openviking": 0,
        "deleted_users": [],
        "failed_users": [],
    }

    # 获取 storage 单例，避免循环内重复创建连接
    storage = get_storage()
    sess_store = storage.session_store
    admin_store = storage.admin_store
    sql_mem_store = storage.sql_memory_store

    # 批量构建 user_id 占位符
    placeholders = ",".join(["?" for _ in request.user_ids])
    valid_uids = [u.strip() for u in request.user_ids if u.strip()]
    valid_uids_set = set(valid_uids)
    if not valid_uids:
        return results

    # 占位符必须基于 valid_uids 重新构建，避免空值导致 IN() 语法错误
    placeholders = ",".join(["?" for _ in valid_uids])

    # 删除所有用户会话（单条批量 SQL，避免逐用户写锁冲突）
    try:
        if sess_store and hasattr(sess_store, "_conn") and sess_store._conn is not None:
            cursor = await sess_store._conn.execute(
                f"DELETE FROM sessions WHERE user_id IN ({placeholders})", valid_uids
            )
            results["deleted_sessions"] = cursor.rowcount
            await sess_store._conn.commit()  # 必须提交，否则重启后 WAL 回滚
    except Exception as e:
        logger.warning(f"Purge sessions failed: {e}", exc_info=True)

    # 删除所有用户 HDC 映射
    try:
        if admin_store:
            all_mappings = await admin_store.get_mappings()
            for m in all_mappings:
                if m["user_id"] in valid_uids_set:
                    await admin_store.delete_mapping(m["user_id"], m["schema_id"], m["database_name"])
                    results["deleted_mappings"] += 1
    except Exception as e:
        logger.warning(f"Purge mappings failed: {e}", exc_info=True)

    # 删除所有用户 SQL 记忆（批量 SQL，避免逐用户写锁冲突）
    try:
        if sql_mem_store:
            conn = getattr(sql_mem_store, "_conn", None)
            if conn is not None:
                # 用 IN(...) 一次删除所有用户记录，避免逐用户 DELETE 持锁冲突
                sql_ph = ",".join(["?" for _ in valid_uids])
                cursor = await conn.execute(
                    f"DELETE FROM sql_memories WHERE user_id IN ({sql_ph})", valid_uids
                )
                results["deleted_sql_memories"] = cursor.rowcount
                await conn.commit()  # 必须提交，否则重启后 WAL 回滚
            else:
                # 回退到逐用户带锁重试
                for uid in valid_uids:
                    try:
                        deleted = await _retry_on_lock(sql_mem_store.delete_records, user_id=uid)
                        results["deleted_sql_memories"] += deleted
                    except Exception as e:
                        logger.warning(f"Purge sql_memories failed for {uid}: {e}", exc_info=True)
    except Exception as e:
        logger.warning(f"Purge sql_memories failed: {e}", exc_info=True)

    # 删除 OpenViking 用户目录
    try:
        from app.config import get_settings
        from app.knowledge.openviking import OpenVikingClient
        settings = get_settings()
        if settings.kb_enabled:
            ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
            await ov.start()
            try:
                for uid in valid_uids:
                    try:
                        result = await ov.rm(f"viking://user/{uid}", recursive=True)
                        if result:
                            results["deleted_openviking"] += 1
                        # 目录不存在也视为已删除
                    except Exception as e:
                        logger.warning(f"Purge OpenViking failed for {uid}: {e}", exc_info=True)
            finally:
                await ov.close()
    except Exception as e:
        logger.warning(f"Purge OpenViking failed: {e}", exc_info=True)

    # 判断每个用户是否注销成功
    for uid in valid_uids:
        results["deleted_users"].append(uid)  # 只要没抛异常就算成功

    return results