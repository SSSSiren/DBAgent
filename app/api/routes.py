"""
API 路由 — HTTP/WebSocket 接口与会话管理

参考 DBAgent 的 app/api/routes.py

职责：
1. 定义 HTTP/WebSocket 接口
2. 管理会话状态（从存储后端恢复/保存）
3. 协调 Agent 执行流程
4. 格式化 SSE 响应

接口：
- POST /api/chat      — SSE 流式聊天
- POST /api/chat/sync — 同步聊天
- WS /api/ws/{id}     — WebSocket 聊天
- GET /api/sessions/{id} — 获取会话状态
"""

import asyncio
import json
import time
from typing import Any, AsyncIterator

import uuid6
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.agent.runner import run_agent_stream
from app.api.schemas import (
    CancelResponse,
    ChatRequest,
    ChatResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionDeleteResponse,
    SessionListResponse,
    SessionState,
    SessionSummary,
    SessionUpdateRequest,
    SessionUpdateResponse,
)
from app.memory import get_storage
from app.memory.store import DEFAULT_SESSION

# 创建路由器
router = APIRouter()


# ========== 后台 LLM 标题生成 ==========

async def _generate_session_title(user_input: str, assistant_reply: str) -> str:
    """
    后台异步任务：使用 LLM 为会话生成简短标题。

    仅使用用户首条消息和 Agent 的最终回答，用轻量 prompt 生成 ≤15 字的标题。
    失败时静默返回空字符串，不阻塞主流程。
    """
    try:
        from app.agent.runner import _get_llm_client

        client = _get_llm_client()
        prompt = (
            "根据以下对话，生成一个简短的会话标题（不超过15个字），"
            "直接返回标题文本，不要加引号或任何额外内容。\n\n"
            f"用户：{user_input[:200]}\n"
            f"助手：{assistant_reply[:300]}"
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=32,
            temperature=0.3,
        )
        title = response.choices[0].message.content or ""
        return title.strip()[:30]  # 最多 30 字符
    except Exception:
        return ""


# ========== SSE 格式化 ==========

def sse_event(event_type: str, data: dict[str, Any]) -> str:
    """
    将事件格式化为 SSE (Server-Sent Events) 标准格式。

    格式：
    data: {"type": "step", "step": "tool:xxx", "status": "running"}\n\n

    Args:
        event_type: 事件类型（"step" / "sql" / "final"）
        data: 事件数据字典

    Returns:
        SSE 格式的字符串
    """
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


# ========== Agent 流包装 ==========

async def _get_or_create_session(user_id: str, session_id: str) -> dict[str, Any]:
    """获取会话状态，不存在时自动创建"""
    store = get_storage().session_store
    state = await store.get_session(user_id, session_id)
    if state is not None:
        return state
    now_iso = __import__("datetime").datetime.now().isoformat()
    new_state = {
        **DEFAULT_SESSION,
        "chat_history": [],
        "session_id": session_id,
        "user_id": user_id,
        "created_at": now_iso,
        "last_active_at": now_iso,
    }
    await store.create_session(user_id, session_id, new_state)
    print(f"[Session] 新建会话: user={user_id} session={session_id}")
    return new_state


async def _record_to_openviking(
    initial_state: dict[str, Any],
    updated_state: dict[str, Any],
    user_input: str,
    response: str,
) -> None:
    """
    将本轮对话记录到 OpenViking，并定期提取长期记忆。

    副作用：更新 initial_state 和 updated_state 中的 kb_session_id 和 kb_turn_count。
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.kb_enabled:
        return

    user_id = initial_state.get("user_id", "default")
    print(f"[KB][INFO] _record_to_openviking: user={user_id} kb_session_id={initial_state.get('kb_session_id', '')} turn={initial_state.get('kb_turn_count', 0)}")

    from app.knowledge.openviking import OpenVikingClient

    kb = OpenVikingClient(settings.kb_openviking_url, user_id)
    try:
        await kb.start()
        print(f"[KB][OK] client started, url={settings.kb_openviking_url}")

        # 懒创建 OpenViking session
        kb_session_id = initial_state.get("kb_session_id", "")
        if not kb_session_id:
            kb_session_id = await kb.create_session()
            print(f"[KB][OK] session created: {kb_session_id}")
            initial_state["kb_session_id"] = kb_session_id
            updated_state["kb_session_id"] = kb_session_id

        # 记录本轮对话
        await kb.add_message(kb_session_id, "user", user_input)
        await kb.add_message(kb_session_id, "assistant", response)
        print(f"[KB][OK] messages recorded")

        # 定期 commit 提取长期记忆
        turn = initial_state.get("kb_turn_count", 0) + 1
        initial_state["kb_turn_count"] = turn
        updated_state["kb_turn_count"] = turn
        if settings.kb_auto_commit_turns > 0 and turn % settings.kb_auto_commit_turns == 0:
            print(f"[KB][INFO] triggering commit at turn {turn}")
            # keep_recent_count=3: 只保留最近 3 条消息，其余都参与记忆提取
            result = await kb.commit(kb_session_id, keep_recent_count=3)
            print(f"[KB][OK] commit result: {result}")
        else:
            print(f"[KB][INFO] turn={turn}, no commit yet (interval={settings.kb_auto_commit_turns})")

    except Exception as e:
        # OpenViking 不可用时不应影响正常对话
        print(f"[KB][ERROR] {type(e).__name__}: {e}")
    finally:
        await kb.close()


async def _execute_agent_stream(
    initial_state: dict[str, Any],
    user_id: str = "default",
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    运行 Agent 流，逐步产出事件。

    包装 run_agent_stream，在 final 事件中保存会话状态。

    Args:
        initial_state: 会话状态字典
        user_id: 用户标识（用于存储层的用户命名空间隔离）
    """
    session_id = initial_state.get("session_id", "")
    print(f"[Agent] 开始执行: session={session_id} user={user_id}")

    # ── 创建取消事件 ──
    from app.agent.cancel import get_cancel_registry
    cancel_registry = get_cancel_registry()
    cancel_event = cancel_registry.create(session_id)

    # ── 记录请求到达时间 ──
    t0 = time.monotonic()
    ctx_timings: dict[str, float | None] = {
        "memories_ms": None,
        "preferences_ms": None,
        "sql_memories_ms": None,
        "hdc_ms": None,
    }

    try:
        # ── 检索长期记忆 ──
        from app.config import get_settings as _get_kb_settings
        _kb_settings = _get_kb_settings()
        memories: list[dict[str, str]] = []
        memory_count = 0
        if _kb_settings.kb_enabled:
            try:
                t_mem_start = time.monotonic()
                from app.knowledge.openviking import OpenVikingClient
                kb = OpenVikingClient(_kb_settings.kb_openviking_url, user_id)
                await kb.start()
                memories = await kb.retrieve_memories()
                memory_count = len(memories)
                await kb.close()
                ctx_timings["memories_ms"] = (time.monotonic() - t_mem_start) * 1000
                print(f"[KB][OK] 记忆检索: user={user_id} count={memory_count}")
            except Exception as e:
                print(f"[KB][ERROR] 记忆检索失败: {type(e).__name__}: {e}")

        if memories:
            initial_state["_memories"] = memories
            initial_state["_memory_count"] = memory_count
        else:
            initial_state["_memory_count"] = memory_count

        # ── 检索操作记忆（查询偏好）──
        from app.config import get_settings as _get_pref_settings
        _pref_settings = _get_pref_settings()
        preferences: list[dict[str, Any]] = []
        preference_count = 0
        if _pref_settings.preference_enabled:
            try:
                t_pref_start = time.monotonic()
                pref_store = get_storage().preference_store
                if pref_store is not None:
                    user_input = initial_state.get("user_input", "")
                    preferences = await pref_store.retrieve_preferences(user_id, user_input)
                    if not preferences:
                        preferences = await pref_store.retrieve_top_preferences(user_id)
                    preference_count = len(preferences)
                    ctx_timings["preferences_ms"] = (time.monotonic() - t_pref_start) * 1000
                    print(f"[Pref][OK] 偏好检索: user={user_id} count={preference_count}")
                else:
                    print(f"[Pref][WARN] 偏好功能已禁用")
            except Exception as e:
                print(f"[Pref][ERROR] 偏好检索失败: {type(e).__name__}: {e}")

        if preferences:
            initial_state["_preferences"] = preferences
        initial_state["_preference_count"] = preference_count

        # ── 检索 SQL 历史记忆 ──
        sql_memories: list[dict[str, Any]] = []
        sql_memory_count = 0
        if getattr(get_settings(), "sql_memory_enabled", False):
            try:
                t_sql_start = time.monotonic()
                sql_mem_store = get_storage().sql_memory_store
                if sql_mem_store is not None:
                    user_input = initial_state.get("user_input", "")
                    selected_db = initial_state.get("selected_database") or {}
                    database_name = selected_db.get("schemaName", "")
                    scope = getattr(get_settings(), "sql_memory_scope", "user")
                    top_k = getattr(get_settings(), "sql_memory_top_k", 5)
                    min_sim = getattr(get_settings(), "sql_memory_min_similarity", 0.0)

                    from app.memory.sql_memory import embed_text
                    query_embedding = await embed_text(user_input)
                    if query_embedding is not None:
                        sql_memories = await sql_mem_store.search_similar(
                            user_id=user_id,
                            query_embedding=query_embedding,
                            database_name=database_name,
                            scope=scope,
                            limit=top_k,
                            min_similarity=min_sim,
                        )
                    sql_memory_count = len(sql_memories)
                    ctx_timings["sql_memories_ms"] = (time.monotonic() - t_sql_start) * 1000
                    print(f"[SQLMem][OK] 检索: user={user_id} count={sql_memory_count} scope={scope}")
                    if sql_memories:
                        for i, m in enumerate(sql_memories):
                            sql_preview = (m.get("sql_truncated") or m.get("sql_text", ""))[:80]
                            print(f"[SQLMem]   {i+1}. sim={m.get('similarity', 0):.4f} | {m.get('question', '')[:50]} | {sql_preview}")
                else:
                    print(f"[SQLMem][WARN] SQL 记忆存储未初始化")
            except Exception as e:
                print(f"[SQLMem][ERROR] 检索失败: {type(e).__name__}: {e}")

        if sql_memories:
            initial_state["_sql_memories"] = sql_memories
        initial_state["_sql_memory_count"] = sql_memory_count

        # ── 检索 HDC 数据底座 ──
        from app.config import get_settings as _get_hdc_settings
        _hdc_settings = _get_hdc_settings()
        if _hdc_settings.hdc_enabled:
            try:
                t_hdc_start = time.monotonic()
                from app.datavault.retriever import HDCRetriever
                from app.knowledge.openviking import OpenVikingClient as OVC
                selected_db = initial_state.get("selected_database")
                if selected_db:
                    hdc_ov = OVC(_hdc_settings.kb_openviking_url, user_id)
                    await hdc_ov.start()
                    retriever = HDCRetriever(hdc_ov)
                    hdc_ctx = await retriever.retrieve(
                        initial_state["user_input"],
                        selected_db.get("schemaId", 0),
                        selected_db.get("schemaName", ""),
                    )
                    if hdc_ctx:
                        initial_state["_hdc_context"] = retriever.format_context(hdc_ctx)
                        print(f"[HDC][OK] 检索成功: db={selected_db.get('schemaName')}, tables={len(hdc_ctx.matched_tables)}")
                    await hdc_ov.close()
                    ctx_timings["hdc_ms"] = (time.monotonic() - t_hdc_start) * 1000
            except Exception as e:
                print(f"[HDC][ERROR] 检索失败: {type(e).__name__}: {e}")

        # ── 上下文准备完成，记录 prep_ms ──
        t_prep = time.monotonic()
        prep_ms = (t_prep - t0) * 1000

        final_payload = None
        latest_sql = ""
        cancelled = False

        async for event_type, data in run_agent_stream(
            initial_state["user_input"],
            initial_state,
            cancel_event=cancel_event,
        ):
            if event_type == "step":
                step_name = data.get("step", "")
                status = data.get("status", "")
                print(f"[Tool] {step_name}: {status}")
                yield "step", data
            elif event_type == "sql":
                latest_sql = data.get("sql", "")
                print(f"[SQL] 提取SQL: len={len(latest_sql)}")
                yield "sql", data
            elif event_type == "final":
                final_payload = data
                if data.get("subtype") == "cancelled":
                    cancelled = True

        # 确保有 final_payload
        if final_payload is None:
            final_payload = {
                "response": "",
                "updated_state": initial_state,
                "needs_confirmation": False,
                "pending_action": None,
                "tool_calls": [],
                "stats": {},
            }

        # 将本次 SQL 持久化到会话状态
        if latest_sql:
            final_payload["updated_state"]["latest_sql"] = latest_sql

        # 持久化记忆计数
        final_payload["updated_state"]["_memory_count"] = memory_count

        # 持久化偏好计数
        final_payload["updated_state"]["_preference_count"] = preference_count

        if cancelled:
            # 取消场景：保留部分结果，但仍记录和保存
            print(f"[Cancel][OK] 取消完成: session_id={session_id}")

        # ── 记录操作记忆（查询偏好）──
        if _pref_settings.preference_enabled and final_payload:
            tool_calls = final_payload.get("tool_calls", [])
            try:
                pref_store = get_storage().preference_store
                if pref_store is not None:
                    for tc in tool_calls:
                        args = tc.get("args", {})
                        table_name = args.get("table_name", "")
                        schema_id = args.get("schema_id", 0)
                        # 按参数特征匹配：任何有 table_name + schema_id + 成功结果的工具调用都记录
                        if table_name and tc.get("result") is not None:
                            # 从 updated_state 获取 database_name（Agent 对话中选库后存入 updated_state）
                            # Agent 不会显式设置 selected_database，用 schema_id 作为兜底标识
                            updated = final_payload.get("updated_state") or {}
                            db_info = updated.get("selected_database") or initial_state.get("selected_database") or {}
                            database_name = db_info.get("schemaName", "")
                            if not database_name and schema_id > 0:
                                database_name = str(schema_id)
                            if table_name and database_name:
                                # 多表 JOIN 场景：逐表记录
                                for t_name in table_name.split(","):
                                    t_name = t_name.strip()
                                    if t_name:
                                        await pref_store.record_query(
                                            user_id, t_name, database_name, schema_id
                                        )
            except Exception as e:
                print(f"[Pref][ERROR] 偏好记录失败: {type(e).__name__}: {e}")

        # ── 记录 SQL 历史记忆 ──
        if getattr(get_settings(), "sql_memory_enabled", False) and final_payload:
            tool_calls = final_payload.get("tool_calls", [])
            try:
                sql_mem_store = get_storage().sql_memory_store
                if sql_mem_store is not None:
                    user_input = initial_state.get("user_input", "")
                    updated = final_payload.get("updated_state") or {}
                    db_info = updated.get("selected_database") or initial_state.get("selected_database") or {}
                    database_name = db_info.get("schemaName", "")

                    from app.memory.sql_memory import embed_text

                    for tc in tool_calls:
                        name = tc.get("name", "")
                        if name not in ("query_database", "execute_sql"):
                            continue

                        args = tc.get("args", {})
                        schema_id = args.get("schema_id", 0)
                        table_name = args.get("table_name", "")

                        if not database_name and schema_id > 0:
                            database_name = str(schema_id)

                        # 提取 SQL 文本
                        sql_text = args.get("sql", "")
                        if not sql_text and name == "query_database":
                            sql_text = args.get("question", "")
                            if sql_text:
                                sql_text = f"[NL2SQL] {sql_text}"

                        if not sql_text:
                            continue

                        # 提取执行结果
                        result = tc.get("result")
                        execution_status = "success"
                        row_count = None
                        column_names: list[str] = []
                        data_preview: list[list[Any]] = []

                        if result is None:
                            execution_status = "error"
                        elif isinstance(result, str):
                            if "错误" in result or "error" in result.lower():
                                execution_status = "error"
                            elif "返回 0 行" in result or "empty" in result.lower():
                                execution_status = "empty"
                            else:
                                # Try to parse row count from result text
                                import re as _re
                                row_match = _re.search(r"返回\s*(\d+)\s*行", result)
                                if row_match:
                                    row_count = int(row_match.group(1))
                                    if row_count == 0:
                                        execution_status = "empty"

                        table_names = [t.strip() for t in table_name.split(",") if t.strip()] if table_name else []

                        # Generate embedding
                        sql_truncated_text = sql_text[:500] if len(sql_text) > 500 else sql_text
                        embedding = await embed_text(sql_truncated_text)

                        await sql_mem_store.record(
                            user_id=user_id,
                            question=user_input if user_input else sql_text[:200],
                            sql=sql_text,
                            table_names=table_names,
                            database_name=database_name,
                            schema_id=schema_id,
                            execution_result={
                                "row_count": row_count,
                                "column_names": column_names,
                                "data_preview": data_preview,
                                "execution_status": execution_status,
                            },
                            embedding=embedding,
                        )
                    print(f"[SQLMem][OK] 记录完成: user={user_id} tool_calls={len(tool_calls)}")
                else:
                    print(f"[SQLMem][WARN] SQL 记忆存储未初始化，跳过记录")
            except Exception as e:
                print(f"[SQLMem][ERROR] 记录失败: {type(e).__name__}: {e}")

        # ── 记录对话到 OpenViking ──
        user_input = initial_state.get("user_input", "")
        final_response = final_payload["response"]
        await _record_to_openviking(
            initial_state,
            final_payload["updated_state"],
            user_input,
            final_response,
        )

        # 保存会话状态
        await get_storage().session_store.save_session(
            user_id,
            initial_state.get("session_id", ""),
            final_payload["updated_state"],
        )
        print(f"[Session] 保存会话: user={user_id} session={initial_state.get('session_id', '')}")

        # 首轮对话完成后，后台异步生成会话标题
        current_summary = final_payload["updated_state"].get("summary", "")
        if not current_summary and not cancelled:
            user_input = initial_state.get("user_input", "")
            session_id = initial_state.get("session_id", "")

            async def _auto_title():
                title = await _generate_session_title(user_input, final_response)
                if title:
                    print(f"[Title] 生成标题: session={session_id} title={title}")
                    try:
                        state = await get_storage().session_store.get_session(
                            user_id, session_id
                        )
                        if state and not state.get("summary", ""):
                            state["summary"] = title
                            await get_storage().session_store.save_session(
                                user_id, session_id, state
                            )
                    except Exception:
                        pass  # 后台任务失败不影响主流程

            asyncio.create_task(_auto_title())

        # ── 注入上下文准备耗时到 stats ──
        final_stats = final_payload.get("stats", {})
        final_stats["prep_ms"] = prep_ms
        final_stats["ctx_timings"] = ctx_timings

        yield "final", {
            "session_id": initial_state.get("session_id", ""),
            "reply": final_response,
            "needs_confirmation": final_payload["needs_confirmation"],
            "tool_calls": final_payload["tool_calls"],
            "stats": final_stats,
            "latest_sql": latest_sql,
            "memory_count": memory_count,
            "preference_count": preference_count,
            "cancelled": cancelled,
        }

    finally:
        # 清理取消事件
        cancel_registry.remove(session_id)


# ========== HTTP 接口 ==========

@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    SSE 流式输出接口 — 用户请求的主入口。

    数据流：
    1. 接收 POST /api/chat 请求（包含 session_id + message）
    2. 从存储后端恢复会话状态
    3. 调用 Agent 执行流
    4. 通过 SSE 实时推送事件给前端
    5. 保存会话状态

    SSE 事件类型：
    - step: 工具调用进度（running/completed）
    - sql: 提取的 SQL 语句
    - final: 最终响应（包含回复 + 工具调用记录）
    """

    async def event_stream() -> AsyncIterator[str]:
        from starlette.requests import Request

        # 解析 user_id（向后兼容：未提供时使用 "default"）
        user_id = request.user_id if request.user_id else "default"
        print(f"[API] POST /chat: user={user_id} session={request.session_id}")

        # 恢复会话状态（传递 user_id 实现用户命名空间隔离）
        session_state = await _get_or_create_session(user_id, request.session_id)
        session_state["user_input"] = request.message
        session_state["user_id"] = user_id

        # 获取底层 Request 对象用于断开检测
        # FastAPI 中通过 request._request 访问 Starlette Request
        starlette_request: Request = getattr(request, "_request", None)

        try:
            # 执行 Agent 流，每个事件通过 SSE 格式化后推送
            async for event_type, data in _execute_agent_stream(session_state, user_id=user_id):
                # 每次 yield 前检测客户端是否断开
                if starlette_request is not None:
                    try:
                        if await starlette_request.is_disconnected():
                            from app.agent.cancel import get_cancel_registry
                            get_cancel_registry().cancel(request.session_id)
                            break
                    except Exception:
                        pass  # is_disconnected 失败不影响主流程
                yield sse_event(event_type, data)
        except asyncio.CancelledError:
            # 客户端断开时 ASGI 服务器取消任务
            from app.agent.cancel import get_cancel_registry
            get_cancel_registry().cancel(request.session_id)
            # 不 re-raise，静默终止

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest) -> ChatResponse:
    """
    同步接口 — 用于测试和集成。

    等待 Agent 完整执行后返回结果。
    """
    # 解析 user_id（向后兼容：未提供时使用 "default"）
    user_id = request.user_id if request.user_id else "default"
    print(f"[API] POST /chat/sync: user={user_id} session={request.session_id}")

    session_state = await _get_or_create_session(user_id, request.session_id)
    session_state["user_input"] = request.message
    session_state["user_id"] = user_id

    final_payload: dict[str, Any] = {}

    async for event_type, data in _execute_agent_stream(session_state, user_id=user_id):
        if event_type == "final":
            final_payload = data

    return ChatResponse(
        response=final_payload.get("reply", ""),
        session_id=final_payload.get("session_id", request.session_id),
        needs_confirmation=final_payload.get("needs_confirmation", False),
    )


# ========== 取消接口 ==========


@router.post("/chat/{session_id}/cancel", response_model=CancelResponse)
async def cancel_chat(session_id: str) -> CancelResponse:
    """
    取消正在执行的 Agent 任务。

    通过 CancelEventRegistry 触发取消信号，Agent 在下个安全点终止。
    所有响应均返回 200 OK，通过 cancelled 字段区分是否成功触发。
    """
    from app.agent.cancel import get_cancel_registry

    registry = get_cancel_registry()
    cancelled = registry.cancel(session_id)
    print(f"[Cancel] POST /chat/{session_id}/cancel: cancelled={cancelled}")

    if cancelled:
        return CancelResponse(
            cancelled=True,
            session_id=session_id,
            message="取消信号已发送",
        )
    else:
        return CancelResponse(
            cancelled=False,
            session_id=session_id,
            message="该会话没有活跃的 Agent 执行",
        )


# ========== WebSocket 接口 ==========

@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str, user_id: str = "default") -> None:
    """
    WebSocket 双向通信接口。

    客户端发送文本消息，服务端流式返回 Agent 事件。
    支持 user_id 查询参数：ws://host/api/ws/{session_id}?user_id=alice
    未提供时默认使用 "default" 保持向后兼容。
    """
    await websocket.accept()
    print(f"[WS] 连接建立: session={session_id} user={user_id}")

    try:
        while True:
            # 接收用户消息
            message = await websocket.receive_text()
            print(f"[WS] 收到消息: session={session_id} len={len(message)}")

            # 恢复会话（传递 user_id 实现用户命名空间隔离）
            session_state = await _get_or_create_session(user_id, session_id)
            session_state["user_input"] = message
            session_state["user_id"] = user_id

            # 流式返回事件
            async for event_type, data in _execute_agent_stream(session_state, user_id=user_id):
                await websocket.send_json({"type": event_type, **data})

    except WebSocketDisconnect:
        # 客户端断开连接，触发 Agent 取消
        print(f"[WS] 客户端断开: session={session_id}")
        from app.agent.cancel import get_cancel_registry
        get_cancel_registry().cancel(session_id)
        return
    except Exception as e:
        # 尝试发送错误信息，并触发取消
        print(f"[WS] 错误: session={session_id} {type(e).__name__}: {e}")
        from app.agent.cancel import get_cancel_registry
        get_cancel_registry().cancel(session_id)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass


# ========== 会话管理接口 ==========

def _validate_user_id(user_id: str | None) -> str:
    """校验 user_id 非空，否则抛出 400"""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required and must not be empty")
    return user_id


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """
    创建新会话。

    使用 uuid6.uuid7() 生成会话 ID，调用 store.create_session() 创建会话。
    """
    import datetime

    user_id = _validate_user_id(request.user_id)
    session_id = str(uuid6.uuid7())

    store = get_storage().session_store
    initial_state = {
        **DEFAULT_SESSION,
        "chat_history": [],  # 每个会话独立的 chat_history
        "session_id": session_id,
        "user_id": user_id,
    }
    await store.create_session(user_id, session_id, initial_state)
    print(f"[Session] POST /sessions: user={user_id} session={session_id}")

    # 从存储中读取以获取 accurate created_at
    created_session = await store.get_session(user_id, session_id)
    created_at = created_session.get("created_at", "") if created_session else datetime.datetime.now().isoformat()

    return SessionCreateResponse(
        session_id=session_id,
        user_id=user_id,
        created_at=created_at,
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(user_id: str = Query(...)) -> SessionListResponse:
    """
    列出用户的所有会话。

    必须提供 user_id 查询参数。
    """
    _validate_user_id(user_id)

    store = get_storage().session_store
    sessions = await store.list_sessions(user_id)

    return SessionListResponse(
        sessions=[SessionSummary(**s) for s in sessions],
        total_count=len(sessions),
    )


@router.get("/sessions/{session_id}", response_model=SessionState)
async def get_session_info(session_id: str, user_id: str = Query(...)) -> SessionState:
    """
    获取会话信息。

    返回会话的摘要、已选数据库、对话历史等。
    需要提供 user_id 查询参数用于用户隔离。
    """
    _validate_user_id(user_id)

    store = get_storage().session_store
    session = await store.get_session(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionState(
        session_id=session_id,
        chat_history=session.get("chat_history", []),
        summary=session.get("summary", ""),
        selected_schema_id=session.get("selected_schema_id"),
        selected_database=session.get("selected_database"),
        latest_sql=session.get("latest_sql", ""),
        memory_count=session.get("_memory_count", 0),
    )


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse)
async def delete_session_info(session_id: str, user_id: str = Query(...)) -> SessionDeleteResponse:
    """
    删除会话。

    需要提供 user_id 查询参数用于用户隔离。
    会话不存在时返回 404。
    """
    _validate_user_id(user_id)

    store = get_storage().session_store
    deleted = await store.delete_session(user_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    print(f"[Session] DELETE /sessions/{session_id}: user={user_id}")
    return SessionDeleteResponse(
        deleted=True,
        session_id=session_id,
    )


@router.put("/sessions/{session_id}", response_model=SessionUpdateResponse)
async def update_session_info(
    session_id: str,
    request: SessionUpdateRequest,
    user_id: str = Query(...),
) -> SessionUpdateResponse:
    """
    更新会话信息（目前支持 summary/标题）。

    需要提供 user_id 查询参数用于用户隔离。
    """
    _validate_user_id(user_id)

    store = get_storage().session_store
    session = await store.get_session(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session["summary"] = request.summary
    await store.save_session(user_id, session_id, session)

    return SessionUpdateResponse(
        session_id=session_id,
        summary=request.summary,
    )


# ═══════════════════════════════════════════════════════════════
# HDC 管理端点
# ═══════════════════════════════════════════════════════════════

# 内存任务状态存储
_hdc_tasks: dict[str, dict[str, Any]] = {}


@router.post("/hdc/generate")
async def hdc_generate(payload: dict[str, Any]):
    """触发生成指定数据库的 HDC 知识库。异步执行，立即返回 task_id。"""
    from app.config import get_settings as _gs
    settings = _gs()
    if not settings.hdc_enabled:
        raise HTTPException(status_code=503, detail="HDC 功能未启用")

    schema_id = payload.get("schema_id")
    database_name = payload.get("database_name", "").strip()
    if not schema_id or not database_name:
        raise HTTPException(status_code=400, detail="schema_id 和 database_name 为必填项")

    task_id = str(uuid6.uuid7())
    _hdc_tasks[task_id] = {
        "task_id": task_id,
        "database_name": database_name,
        "status": "started",
        "progress": {"phase": "initializing", "tables_done": 0, "tables_total": 0},
        "result": None,
    }

    # 后台异步生成
    asyncio.create_task(_run_hdc_generate(task_id, schema_id, database_name))
    return {"task_id": task_id, "status": "started"}


async def _run_hdc_generate(task_id: str, schema_id: int, database_name: str):
    """后台执行 HDC 生成任务。"""
    try:
        from app.client.onedba import get_onedba_client
        from app.datavault.collector import SchemaCollector
        from app.datavault.generator import HDCGenerator
        from app.datavault.uploader import HDCUploader
        from app.knowledge.openviking import OpenVikingClient
        from app.config import get_settings

        settings = get_settings()
        from openai import AsyncOpenAI
        llm = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
        await ov.start()
        onedba = get_onedba_client()

        collector = SchemaCollector(onedba)
        uploader = HDCUploader(ov)
        generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)

        _hdc_tasks[task_id]["status"] = "running"
        _hdc_tasks[task_id]["progress"] = {"phase": "generating", "tables_done": 0, "tables_total": 0}

        result = await generator.generate(schema_id, database_name)
        _hdc_tasks[task_id]["status"] = "completed"
        _hdc_tasks[task_id]["result"] = result

        await ov.close()
    except Exception as e:
        _hdc_tasks[task_id]["status"] = "failed"
        _hdc_tasks[task_id]["result"] = {"error": str(e)}


@router.get("/hdc/status/{database_name}")
async def hdc_status(database_name: str):
    """查询指定数据库的 HDC 状态。"""
    from app.config import get_settings as _gs
    settings = _gs()
    if not settings.hdc_enabled:
        raise HTTPException(status_code=503, detail="HDC 功能未启用")

    # Check if HDC data exists in OpenViking by listing the directory
    try:
        from app.knowledge.openviking import OpenVikingClient
        ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
        await ov.start()
        entries = await ov.ls(f"viking://user/hdc-system/memories/hdc/{database_name}")
        await ov.close()

        exists = len(entries) > 0 if isinstance(entries, list) else False
        table_count = sum(1 for e in (entries if isinstance(entries, list) else []) if e.get("isDir"))
        return {
            "database_name": database_name,
            "exists": exists,
            "table_count": table_count,
        }
    except Exception as e:
        return {
            "database_name": database_name,
            "exists": False,
            "error": str(e),
        }


@router.get("/hdc/tasks/{task_id}")
async def hdc_task_status(task_id: str):
    """查询 HDC 生成任务进度。"""
    task = _hdc_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.delete("/hdc/{database_name}")
async def hdc_delete(database_name: str):
    """删除指定数据库的全部 HDC 数据。"""
    from app.config import get_settings as _gs
    settings = _gs()
    if not settings.hdc_enabled:
        raise HTTPException(status_code=503, detail="HDC 功能未启用")

    try:
        from app.knowledge.openviking import OpenVikingClient
        ov = OpenVikingClient(settings.kb_openviking_url, "hdc-admin")
        await ov.start()
        await ov.rm(f"viking://user/hdc-system/memories/hdc/{database_name}", recursive=True)
        await ov.close()
        return {"deleted": True, "database_name": database_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")