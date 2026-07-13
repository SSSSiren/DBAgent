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
)
from app.memory import get_storage
from app.memory.store import DEFAULT_SESSION

# 创建路由器
router = APIRouter()


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
    print(f"[KB] _record_to_openviking: user={user_id} kb_session_id={initial_state.get('kb_session_id', '')} turn={initial_state.get('kb_turn_count', 0)}")

    from app.knowledge.openviking import OpenVikingClient

    kb = OpenVikingClient(settings.kb_openviking_url, user_id)
    try:
        await kb.start()
        print(f"[KB] client started, url={settings.kb_openviking_url}")

        # 懒创建 OpenViking session
        kb_session_id = initial_state.get("kb_session_id", "")
        if not kb_session_id:
            kb_session_id = await kb.create_session()
            print(f"[KB] session created: {kb_session_id}")
            initial_state["kb_session_id"] = kb_session_id
            updated_state["kb_session_id"] = kb_session_id

        # 记录本轮对话
        await kb.add_message(kb_session_id, "user", user_input)
        await kb.add_message(kb_session_id, "assistant", response)
        print(f"[KB] messages recorded")

        # 定期 commit 提取长期记忆
        turn = initial_state.get("kb_turn_count", 0) + 1
        initial_state["kb_turn_count"] = turn
        updated_state["kb_turn_count"] = turn
        if settings.kb_auto_commit_turns > 0 and turn % settings.kb_auto_commit_turns == 0:
            print(f"[KB] triggering commit at turn {turn}")
            # keep_recent_count=3: 只保留最近 3 条消息，其余都参与记忆提取
            result = await kb.commit(kb_session_id, keep_recent_count=3)
            print(f"[KB] commit result: {result}")
        else:
            print(f"[KB] turn={turn}, no commit yet (interval={settings.kb_auto_commit_turns})")

    except Exception as e:
        # OpenViking 不可用时不应影响正常对话
        print(f"[KB] ERROR: {type(e).__name__}: {e}")
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

    # ── 创建取消事件 ──
    from app.agent.cancel import get_cancel_registry
    cancel_registry = get_cancel_registry()
    cancel_event = cancel_registry.create(session_id)

    try:
        # ── 检索长期记忆 ──
        from app.config import get_settings as _get_kb_settings
        _kb_settings = _get_kb_settings()
        memories: list[dict[str, str]] = []
        memory_count = 0
        if _kb_settings.kb_enabled:
            try:
                from app.knowledge.openviking import OpenVikingClient
                kb = OpenVikingClient(_kb_settings.kb_openviking_url, user_id)
                await kb.start()
                memories = await kb.retrieve_memories()
                memory_count = len(memories)
                await kb.close()
                print(f"[KB] 记忆检索: user={user_id} count={memory_count}")
            except Exception as e:
                print(f"[KB] 记忆检索失败: {type(e).__name__}: {e}")

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
                pref_store = get_storage().preference_store
                if pref_store is not None:
                    user_input = initial_state.get("user_input", "")
                    preferences = await pref_store.retrieve_preferences(user_id, user_input)
                    if not preferences:
                        preferences = await pref_store.retrieve_top_preferences(user_id)
                    preference_count = len(preferences)
                    print(f"[Pref] 偏好检索: user={user_id} count={preference_count}")
                else:
                    print(f"[Pref] 偏好功能已禁用")
            except Exception as e:
                print(f"[Pref] 偏好检索失败: {type(e).__name__}: {e}")

        if preferences:
            initial_state["_preferences"] = preferences
        initial_state["_preference_count"] = preference_count

        final_payload = None
        latest_sql = ""
        cancelled = False

        async for event_type, data in run_agent_stream(
            initial_state["user_input"],
            initial_state,
            cancel_event=cancel_event,
        ):
            if event_type == "step":
                yield "step", data
            elif event_type == "sql":
                latest_sql = data.get("sql", "")
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
            print(f"[Cancel] 取消完成: session_id={session_id}")

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
                print(f"[Pref] 偏好记录失败: {type(e).__name__}: {e}")

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

        yield "final", {
            "session_id": initial_state.get("session_id", ""),
            "reply": final_response,
            "needs_confirmation": final_payload["needs_confirmation"],
            "tool_calls": final_payload["tool_calls"],
            "stats": final_payload.get("stats", {}),
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

    try:
        while True:
            # 接收用户消息
            message = await websocket.receive_text()

            # 恢复会话（传递 user_id 实现用户命名空间隔离）
            session_state = await _get_or_create_session(user_id, session_id)
            session_state["user_input"] = message
            session_state["user_id"] = user_id

            # 流式返回事件
            async for event_type, data in _execute_agent_stream(session_state, user_id=user_id):
                await websocket.send_json({"type": event_type, **data})

    except WebSocketDisconnect:
        # 客户端断开连接，触发 Agent 取消
        from app.agent.cancel import get_cancel_registry
        get_cancel_registry().cancel(session_id)
        return
    except Exception as e:
        # 尝试发送错误信息，并触发取消
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

    return SessionDeleteResponse(
        deleted=True,
        session_id=session_id,
    )