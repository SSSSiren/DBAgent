import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.agent.graph import agent_graph
from app.agent.state import AgentState, ToolCall
from app.api.schemas import ChatRequest, ChatResponse, SessionResponse

router = APIRouter()

SESSION_STORE: dict[str, dict[str, Any]] = {}


def _tool_call_to_dict(call: ToolCall | dict[str, Any]) -> dict[str, Any]:
    if isinstance(call, ToolCall):
        payload = {
            "tool": call.tool,
            "args": call.args,
            "result": call.result.get("content") if isinstance(call.result, dict) else call.result,
            "status": call.status,
        }
        if isinstance(call.result, dict):
            if call.tool == "nl2sql_query":
                payload["nl2sql"] = {
                    "steps": call.result.get("steps", []),
                    "sql": call.result.get("sql", ""),
                    "table_name": call.result.get("table_name", ""),
                    "assumptions": call.result.get("assumptions", []),
                    "selected_schema_id": call.result.get("selected_schema_id"),
                    "selected_database": call.result.get("selected_database"),
                }
            if call.tool == "select_database":
                payload["selected_database"] = call.result.get("selected_database")
                payload["selected_schema_id"] = call.result.get("selected_schema_id")
        return payload
    return call


def _json_default(value: Any) -> str:
    return str(value)


def sse_event(event_type: str, data: dict[str, Any]) -> str:
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False, default=_json_default)
    return f"data: {payload}\n\n"


def build_initial_state(session_id: str, message: str) -> AgentState:
    session = SESSION_STORE.get(session_id, {})
    pending_action = session.get("pending_action")
    confirmed = message.strip() == "确认执行" and pending_action
    cancelled = pending_action and not confirmed

    state: AgentState = {
        "user_input": message,
        "session_id": session_id,
        "chat_history": session.get("chat_history", []),
        "summary": session.get("summary", ""),
        "selected_schema_id": session.get("selected_schema_id"),
        "selected_database": session.get("selected_database"),
        "table_schemas": session.get("table_schemas", {}),
        "current_step": "",
        "parsed_intent": None,
        "execution_plan": [pending_action] if confirmed else [],
        "tool_calls": [],
        "response": "已取消执行。" if cancelled else "",
        "needs_confirmation": False,
        "pending_action": None,
        "confirmed_action": pending_action if confirmed else None,
        "pending_nl2sql": session.get("pending_nl2sql"),
    }
    if cancelled:
        SESSION_STORE[session_id] = {**session, "pending_action": None, "needs_confirmation": False}
    return state


def save_session(final_state: AgentState) -> None:
    session_id = final_state["session_id"]
    previous = SESSION_STORE.get(session_id, {})
    history = previous.get("chat_history", [])
    if final_state.get("response"):
        history = history + [
            {"role": "user", "content": final_state.get("user_input", "")},
            {"role": "assistant", "content": final_state.get("response", "")},
        ]
        history = history[-20:]

    SESSION_STORE[session_id] = {
        "chat_history": history,
        "summary": final_state.get("summary", previous.get("summary", "")),
        "selected_schema_id": final_state.get("selected_schema_id", previous.get("selected_schema_id")),
        "selected_database": final_state.get("selected_database", previous.get("selected_database")),
        "table_schemas": final_state.get("table_schemas", previous.get("table_schemas", {})),
        "pending_action": final_state.get("pending_action") if final_state.get("needs_confirmation") else None,
        "pending_nl2sql": final_state.get("pending_nl2sql"),
        "needs_confirmation": final_state.get("needs_confirmation", False),
    }


async def run_agent_stream(initial_state: AgentState) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    if initial_state.get("response") == "已取消执行。":
        save_session(initial_state)
        yield "final", {
            "session_id": initial_state["session_id"],
            "reply": initial_state["response"],
            "tool_calls": [],
            "needs_confirmation": False,
        }
        return

    final_state: AgentState | None = None
    async for update in agent_graph.astream(initial_state):
        node_name, node_state = next(iter(update.items()))
        final_state = {**(final_state or initial_state), **node_state}
        yield "step", {"step": node_name, "state": node_state}

    if final_state is None:
        final_state = initial_state
    save_session(final_state)
    yield "final", {
        "session_id": final_state["session_id"],
        "reply": final_state.get("response", ""),
        "tool_calls": [_tool_call_to_dict(call) for call in final_state.get("tool_calls", [])],
        "needs_confirmation": final_state.get("needs_confirmation", False),
    }


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Return Server-Sent Events for an agent run."""

    async def event_stream() -> AsyncIterator[str]:
        initial_state = build_initial_state(request.session_id, request.message)
        async for event_type, data in run_agent_stream(initial_state):
            yield sse_event(event_type, data)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest) -> ChatResponse:
    """Non-streaming endpoint useful for tests and integrations."""

    final_payload: dict[str, Any] = {}
    initial_state = build_initial_state(request.session_id, request.message)
    async for event_type, data in run_agent_stream(initial_state):
        if event_type == "final":
            final_payload = data
    return ChatResponse(**final_payload)


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            initial_state = build_initial_state(session_id, message)
            async for event_type, data in run_agent_stream(initial_state):
                await websocket.send_json({"type": event_type, **data})
    except WebSocketDisconnect:
        return


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    session = SESSION_STORE.get(session_id, {})
    return SessionResponse(
        session_id=session_id,
        summary=session.get("summary", ""),
        selected_schema_id=session.get("selected_schema_id"),
        selected_database=session.get("selected_database"),
        needs_confirmation=session.get("needs_confirmation", False),
    )
