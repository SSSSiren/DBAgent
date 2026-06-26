"""
API 路由 - 用户请求入口与会话管理

职责：
1. 定义 HTTP/WebSocket 接口
2. 管理会话状态（SESSION_STORE）
3. 协调 Agent 执行流程
4. 格式化 SSE 响应
"""

import json
from typing import Any, AsyncIterator
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.agent.llm_agent import run_agent_stream as agent_run_stream
from app.agent.state import AgentState
from app.api.schemas import ChatRequest, ChatResponse, SessionState

# 创建 FastAPI 路由器
# 在 main.py 中通过 app.include_router(router, prefix="/agent") 挂载
# 最终路由前缀为 /agent
router = APIRouter()

# ========== 会话存储 ==========
# 使用进程内存字典存储所有会话状态
# 键：session_id（字符串）
# 值：会话状态字典，包含 chat_history、summary、selected_database 等
# 注意：进程重启后会话数据会丢失
SESSION_STORE: dict[str, dict[str, Any]] = {}


# ========== 消息序列化工具函数 ==========

def message_to_dict(message: BaseMessage) -> dict[str, str]:
    """
    将 LangChain 消息对象转换为字典格式

    用途：
    - 会话状态需要存储到 SESSION_STORE 时，LangChain 消息对象无法直接 JSON 序列化
    - 转换为 {"role": "user/assistant", "content": "..."} 格式便于存储和传输

    Args:
        message: LangChain 消息对象（HumanMessage 或 AIMessage）

    Returns:
        字典格式的消息，包含 role 和 content 字段
    """
    return {
        "role": "user" if isinstance(message, HumanMessage) else "assistant",
        "content": message.content,
    }


def dict_to_message(data: dict[str, str]) -> BaseMessage:
    """
    将字典格式的消息转换回 LangChain 消息对象

    用途：
    - 从 SESSION_STORE 恢复会话状态时，需要把字典格式的消息还原为 LangChain 对象
    - Agent 执行时需要 LangChain 消息对象作为输入

    Args:
        data: 字典格式的消息，包含 role 和 content 字段

    Returns:
        LangChain 消息对象（HumanMessage 或 AIMessage）
    """
    if data.get("role") == "user":
        return HumanMessage(content=data.get("content", ""))
    return AIMessage(content=data.get("content", ""))


# ========== 阶段5：SSE 响应格式化 ==========

def sse_event(event_type: str, data: dict[str, Any]) -> str:
    """
    将事件格式化为 SSE (Server-Sent Events) 标准格式

    SSE 协议规范：
    - 每条消息以 "data: " 开头
    - 消息内容必须是单行 JSON（不能包含换行符）
    - 每条消息以两个换行符 \n\n 结尾

    格式示例：
    data: {"type": "step", "step": "tool:list_databases_tool", "status": "running"}\n\n
    data: {"type": "final", "reply": "查询结果...", "tool_calls": [...]}\n\n

    参数：
        event_type: 事件类型（"step" / "sql" / "final"）
        data: 事件数据字典

    返回：
        SSE 格式的字符串
    """
    # 特殊处理：转换 chat_history 中的 LangChain 消息对象为字典
    # 因为 SSE 响应需要 JSON 序列化，而 LangChain 消息对象不能直接序列化
    if "state" in data and "chat_history" in data["state"]:
        data["state"]["chat_history"] = [
            message_to_dict(msg) if isinstance(msg, BaseMessage) else msg
            for msg in data["state"]["chat_history"]
        ]

    # 将事件类型和数据合并为 JSON
    # ensure_ascii=False 确保中文字符正常显示（不被转义为 \uXXXX）
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)

    # 返回 SSE 标准格式：data: {json}\n\n
    return f"data: {payload}\n\n"


# ========== 阶段2：会话状态恢复 ==========

def build_initial_state(session_id: str, message: str) -> AgentState:
    """
    构建 Agent 的初始状态

    职责：
    1. 从 SESSION_STORE 中按 session_id 查找历史会话
    2. 恢复对话历史（chat_history）、摘要（summary）、已选数据库等上下文
    3. 组装成 AgentState 字典传给 Agent 执行器

    数据流：
    SESSION_STORE[session_id] → 字典格式 → 转换为 LangChain 消息对象 → AgentState

    Args:
        session_id: 会话唯一标识，用于追踪对话历史
        message: 用户当前输入的消息

    Returns:
        AgentState: 包含完整上下文的初始状态字典，结构如下：
        {
            "user_input": str,              # 用户当前输入
            "session_id": str,              # 会话 ID
            "chat_history": list[Message],  # LangChain 消息对象列表
            "summary": str,                 # 对话摘要（压缩后的上下文）
            "selected_schema_id": int|None, # 当前选择的数据库 schema ID
            "selected_database": dict|None, # 当前选择的数据库详细信息
            "needs_confirmation": bool,     # 是否需要用户确认（写操作）
            "pending_action": dict|None,    # 待确认的操作
        }
    """
    # 从 SESSION_STORE 中查找该 session_id 的历史状态
    # 如果是新会话，返回空字典 {}
    session = SESSION_STORE.get(session_id, {})

    # 恢复对话历史：将字典格式转换回 LangChain 消息对象
    # SESSION_STORE 中存储的是 [{"role": "user", "content": "..."}] 格式
    # Agent 执行需要 [HumanMessage(...), AIMessage(...)] 格式
    chat_history_dicts = session.get("chat_history", [])
    chat_history = [dict_to_message(msg) for msg in chat_history_dicts]

    # 组装 AgentState 字典
    state: AgentState = {
        "user_input": message,                    # 用户当前输入
        "session_id": session_id,                 # 会话 ID
        "chat_history": chat_history,             # 恢复的对话历史（LangChain 对象）
        "summary": session.get("summary", ""),    # 对话摘要（用于上下文压缩）
        "selected_schema_id": session.get("selected_schema_id"),  # 已选数据库 ID
        "selected_database": session.get("selected_database"),    # 已选数据库详情
        "needs_confirmation": False,              # 初始状态：无需确认
        "pending_action": None,                   # 初始状态：无待确认操作
    }

    return state


# ========== 阶段4：会话状态保存 ==========

def save_session(final_state: AgentState) -> None:
    """
    保存 Agent 执行后的最终状态到会话存储

    职责：
    1. 从 Agent 执行后的最终状态中提取需要持久化的信息
    2. 将 LangChain 消息对象转换为字典格式（便于 JSON 序列化）
    3. 写入 SESSION_STORE，供下次请求恢复时使用

    数据流：
    AgentState（LangChain 对象） → 转换为字典格式 → 写入 SESSION_STORE

    保存的内容：
    - chat_history: 对话历史（用户 + AI 的消息）
    - summary: 对话摘要（压缩后的上下文）
    - selected_schema_id: 当前选择的数据库 ID
    - selected_database: 当前选择的数据库详情

    注意：
    - 不保存 needs_confirmation 和 pending_action（这些是临时状态）
    - 不保存 intermediate_steps（中间步骤不需要跨请求保留）

    Args:
        final_state: Agent 执行后的最终状态字典
    """
    # 获取 session_id，如果没有则跳过保存
    session_id = final_state.get("session_id", "")
    if not session_id:
        return

    # 将 LangChain 消息对象转换为字典格式，LangChain无法直接序列化
    # HumanMessage(content="...") → {"role": "user", "content": "..."}
    # AIMessage(content="...")     → {"role": "assistant", "content": "..."}
    chat_history = final_state.get("chat_history", [])
    chat_history_dicts = [
        message_to_dict(msg) if isinstance(msg, BaseMessage) else msg
        for msg in chat_history
    ]

    # 写入 SESSION_STORE，覆盖该 session 的旧状态
    SESSION_STORE[session_id] = {
        "chat_history": chat_history_dicts,                 # 对话历史（字典格式）
        "summary": final_state.get("summary", ""),          # 对话摘要
        "selected_schema_id": final_state.get("selected_schema_id"),  # 已选数据库 ID
        "selected_database": final_state.get("selected_database"),    # 已选数据库详情
    }


async def run_agent_stream(initial_state: AgentState) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    运行 Agent 流，逐步产出事件
    """
    from app.agent.llm_agent import run_agent_stream as agent_stream

    final_payload = None
    async for event_type, data in agent_stream(
        initial_state["user_input"],
        initial_state,
    ):
        if event_type == "step":
            yield "step", data
        elif event_type == "sql":
            yield "sql", data
        elif event_type == "final":
            final_payload = data

    if final_payload is None:
        final_payload = {
            "response": "",
            "updated_state": initial_state,
            "needs_confirmation": False,
            "pending_action": None,
            "tool_calls": [],
        }

    # 保存会话状态
    save_session(final_payload["updated_state"])

    yield "final", {
        "session_id": initial_state.get("session_id", ""),
        "reply": final_payload["response"],
        "needs_confirmation": final_payload["needs_confirmation"],
        "tool_calls": final_payload["tool_calls"],
    }


# ========== 阶段1+5：HTTP 入口 + SSE 响应流 ==========

@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    SSE 流式输出接口 - 用户请求的主入口

    数据流：
    1. 接收 POST /agent/chat 请求（包含 session_id + message）
    2. 构建初始状态（阶段2）
    3. 调用 Agent 执行流（阶段3）
    4. 保存会话状态（阶段4）
    5. 通过 SSE 实时推送事件给前端（阶段5）

    SSE 事件类型：
    - step: 工具调用进度（running/completed）
    - sql: 提取的 SQL 语句
    - final: 最终响应（包含回复 + 工具调用记录）

    返回：
        StreamingResponse: SSE 流式响应
    """

    async def event_stream() -> AsyncIterator[str]:
        """
        异步生成器：逐步产出 SSE 事件

        流程：
        1. build_initial_state() → 恢复会话状态
        2. run_agent_stream() → 执行 Agent，产出事件
        3. sse_event() → 格式化为 SSE 标准格式
        """
        # 阶段2：构建初始状态（从 SESSION_STORE 恢复历史）
        initial_state = build_initial_state(request.session_id, request.message)

        # 阶段3+4：执行 Agent 流（内部会保存会话状态）
        # 每个事件通过 sse_event() 格式化后 yield 给前端
        async for event_type, data in run_agent_stream(initial_state):
            yield sse_event(event_type, data)

    # 返回 SSE 流式响应
    # media_type="text/event-stream" 告诉浏览器这是 SSE 流
    # 浏览器会通过 EventSource API 或 fetch + ReadableStream 接收
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
