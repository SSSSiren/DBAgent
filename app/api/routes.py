"""
API 路由 — HTTP/WebSocket 接口与会话管理

参考 DBAgent 的 app/api/routes.py

职责：
1. 定义 HTTP/WebSocket 接口
2. 管理会话状态（从 SESSION_STORE 恢复/保存）
3. 协调 Agent 执行流程
4. 格式化 SSE 响应

接口：
- POST /api/chat      — SSE 流式聊天
- POST /api/chat/sync — 同步聊天
- WS /api/ws/{id}     — WebSocket 聊天
- GET /api/sessions/{id} — 获取会话状态
"""

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.agent.runner import run_agent_stream
from app.api.schemas import ChatRequest, ChatResponse, SessionState
from app.memory.store import get_session, save_session

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
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    运行 Agent 流，逐步产出事件。

    包装 run_agent_stream，在 final 事件中保存会话状态。
    """
    final_payload = None

    async for event_type, data in run_agent_stream(
        initial_state["user_input"],
        initial_state,
    ):
        if event_type == "step":
            yield "step", data
        elif event_type == "sql":
            yield "sql", data
        elif event_type == "final":
            final_payload = data

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

    # ── 记录对话到 OpenViking（在 save 之前，确保 kb_session_id 被持久化）──
    user_input = initial_state.get("user_input", "")
    final_response = final_payload["response"]
    await _record_to_openviking(
        initial_state,
        final_payload["updated_state"],
        user_input,
        final_response,
    )

    # 保存会话状态
    save_session(
        initial_state.get("session_id", ""),
        final_payload["updated_state"],
    )

    yield "final", {
        "session_id": initial_state.get("session_id", ""),
        "reply": final_response,
        "needs_confirmation": final_payload["needs_confirmation"],
        "tool_calls": final_payload["tool_calls"],
        "stats": final_payload.get("stats", {}),
    }


# ========== HTTP 接口 ==========

@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    SSE 流式输出接口 — 用户请求的主入口。

    数据流：
    1. 接收 POST /api/chat 请求（包含 session_id + message）
    2. 从 SESSION_STORE 恢复会话状态
    3. 调用 Agent 执行流
    4. 通过 SSE 实时推送事件给前端
    5. 保存会话状态

    SSE 事件类型：
    - step: 工具调用进度（running/completed）
    - sql: 提取的 SQL 语句
    - final: 最终响应（包含回复 + 工具调用记录）
    """

    async def event_stream() -> AsyncIterator[str]:
        # 恢复会话状态
        session_state = get_session(request.session_id)
        session_state["user_input"] = request.message
        session_state["user_id"] = request.user_id

        # 执行 Agent 流，每个事件通过 SSE 格式化后推送
        async for event_type, data in _execute_agent_stream(session_state):
            yield sse_event(event_type, data)

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
    session_state = get_session(request.session_id)
    session_state["user_input"] = request.message
    session_state["user_id"] = request.user_id

    final_payload: dict[str, Any] = {}

    async for event_type, data in _execute_agent_stream(session_state):
        if event_type == "final":
            final_payload = data

    return ChatResponse(
        response=final_payload.get("reply", ""),
        session_id=final_payload.get("session_id", request.session_id),
        needs_confirmation=final_payload.get("needs_confirmation", False),
    )


# ========== WebSocket 接口 ==========

@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str, user_id: str = "default") -> None:
    """
    WebSocket 双向通信接口。

    客户端发送文本消息，服务端流式返回 Agent 事件。
    支持 user_id 查询参数：ws://host/api/ws/{session_id}?user_id=alice
    """
    await websocket.accept()

    try:
        while True:
            # 接收用户消息
            message = await websocket.receive_text()

            # 恢复会话
            session_state = get_session(session_id)
            session_state["user_input"] = message
            session_state["user_id"] = user_id

            # 流式返回事件
            async for event_type, data in _execute_agent_stream(session_state):
                await websocket.send_json({"type": event_type, **data})

    except WebSocketDisconnect:
        # 客户端断开连接
        return
    except Exception as e:
        # 尝试发送错误信息
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass


# ========== 会话管理接口 ==========

@router.get("/sessions/{session_id}", response_model=SessionState)
async def get_session_info(session_id: str) -> SessionState:
    """
    获取会话信息。

    返回会话的摘要、已选数据库、对话历史等。
    """
    session = get_session(session_id)
    return SessionState(
        session_id=session_id,
        chat_history=session.get("chat_history", []),
        summary=session.get("summary", ""),
        selected_schema_id=session.get("selected_schema_id"),
        selected_database=session.get("selected_database"),
    )