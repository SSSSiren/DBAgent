"""
API 路由 - 用户请求入口与会话管理
"""

import json
from typing import Any, AsyncIterator
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.api.schemas import ChatRequest, ChatResponse, SessionState

router = APIRouter()

# 会话存储 - 进程内存中的会话状态管理
SESSION_STORE: dict[str, dict[str, Any]] = {}


def message_to_dict(message: BaseMessage) -> dict[str, str]:
    """将 LangChain 消息对象转换为字典"""
    return {
        "role": "user" if isinstance(message, HumanMessage) else "assistant",
        "content": message.content,
    }


def dict_to_message(data: dict[str, str]) -> BaseMessage:
    """将字典转换回 LangChain 消息对象"""
    if data.get("role") == "user":
        return HumanMessage(content=data.get("content", ""))
    return AIMessage(content=data.get("content", ""))


def sse_event(event_type: str, data: dict[str, Any]) -> str:
    """
    将事件格式化为 SSE (Server-Sent Events) 标准格式
    """
    # 转换 chat_history 中的消息对象为字典
    if "state" in data and "chat_history" in data["state"]:
        data["state"]["chat_history"] = [
            message_to_dict(msg) if isinstance(msg, BaseMessage) else msg
            for msg in data["state"]["chat_history"]
        ]

    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def build_initial_state(session_id: str, message: str) -> AgentState:
    """
    构建 Agent 的初始状态

    从 SESSION_STORE 恢复该 session 的历史上下文
    """
    session = SESSION_STORE.get(session_id, {})

    # 将字典格式的 chat_history 转换回 LangChain 消息对象
    chat_history_dicts = session.get("chat_history", [])
    chat_history = [dict_to_message(msg) for msg in chat_history_dicts]

    state: AgentState = {
        "user_input": message,
        "session_id": session_id,
        "chat_history": chat_history,
        "summary": session.get("summary", ""),
        "selected_schema_id": session.get("selected_schema_id"),
        "selected_database": session.get("selected_database"),
        "needs_confirmation": False,
        "pending_action": None,
    }

    return state


def save_session(final_state: AgentState) -> None:
    """
    保存 Agent 执行后的最终状态到会话存储
    """
    session_id = final_state.get("session_id", "")
    if not session_id:
        return

    # 将 LangChain 消息对象转换为字典格式以便序列化
    chat_history = final_state.get("chat_history", [])
    chat_history_dicts = [
        message_to_dict(msg) if isinstance(msg, BaseMessage) else msg
        for msg in chat_history
    ]

    SESSION_STORE[session_id] = {
        "chat_history": chat_history_dicts,
        "summary": final_state.get("summary", ""),
        "selected_schema_id": final_state.get("selected_schema_id"),
        "selected_database": final_state.get("selected_database"),
    }


async def run_agent_stream(initial_state: AgentState) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    运行 Agent 流，逐步产出事件
    """
    final_state: AgentState | None = None

    async for update in agent_graph.astream(initial_state):
        node_name, node_state = next(iter(update.items()))
        final_state = {**(final_state or initial_state), **node_state}
        yield "step", {"step": node_name, "state": node_state}

    if final_state is None:
        final_state = initial_state

    save_session(final_state)

    yield "final", {
        "session_id": final_state.get("session_id", ""),
        "reply": final_state.get("response", ""),
        "needs_confirmation": final_state.get("needs_confirmation", False),
    }


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    SSE 流式输出接口 - 用户请求的主入口
    """

    async def event_stream() -> AsyncIterator[str]:
        initial_state = build_initial_state(request.session_id, request.message)

        async for event_type, data in run_agent_stream(initial_state):
            yield sse_event(event_type, data)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest) -> ChatResponse:
    """
    同步接口 - 用于测试和集成
    """
    final_payload: dict[str, Any] = {}
    initial_state = build_initial_state(request.session_id, request.message)

    async for event_type, data in run_agent_stream(initial_state):
        if event_type == "final":
            final_payload = data

    return ChatResponse(
        response=final_payload.get("reply", ""),
        session_id=final_payload.get("session_id", request.session_id),
        needs_confirmation=final_payload.get("needs_confirmation", False),
    )


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket 双向通信接口
    """
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            initial_state = build_initial_state(session_id, message)
            async for event_type, data in run_agent_stream(initial_state):
                await websocket.send_json({"type": event_type, **data})
    except WebSocketDisconnect:
        return


@router.get("/sessions/{session_id}", response_model=SessionState)
async def get_session(session_id: str) -> SessionState:
    """
    获取会话信息接口
    """
    session = SESSION_STORE.get(session_id, {})
    return SessionState(
        session_id=session_id,
        chat_history=session.get("chat_history", []),
        summary=session.get("summary", ""),
        selected_schema_id=session.get("selected_schema_id"),
        selected_database=session.get("selected_database"),
    )
