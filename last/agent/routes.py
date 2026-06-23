# ============================================================================
# API 路由层 — 用户请求入口与会话管理
# ============================================================================
# 职责：
#   1. 接收用户请求（HTTP SSE / HTTP 同步 / WebSocket 三种方式）
#   2. 管理会话状态（SESSION_STORE），跨请求保持上下文
#   3. 启动 LangGraph Agent 执行流
#   4. 将 Agent 执行过程通过 SSE 实时推送给前端
#
# 数据流：
#   用户请求 → chat() → build_initial_state() → run_agent_stream()
#   → agent_graph.astream() → 逐节点执行 → save_session() → SSE 返回前端
# ============================================================================

import json
import re
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.agent.graph import agent_graph
from app.agent.state import AgentState, ToolCall
from app.api.schemas import ChatRequest, ChatResponse, SessionResponse
from app.nl2sql.semantics import SemanticContext, parse_custom_semantic_rule
from app.nl2sql.schema import ColumnSchema

# FastAPI 路由器，在 main.py 中通过 app.include_router(router, prefix="/api") 挂载
router = APIRouter()

# ============================================================================
# 会话存储 — 进程内存中的会话状态管理
# ============================================================================
# 结构：{session_id: {状态字段...}}
# 每个 session 保存：对话历史、摘要、选中的数据库、表结构缓存、NL2SQL 任务记忆等
# 注意：进程重启后会丢失，生产环境应替换为 Redis 或数据库
# ============================================================================
SESSION_STORE: dict[str, dict[str, Any]] = {}


# ============================================================================
# 辅助函数
# ============================================================================

def _tool_call_to_dict(call: ToolCall | dict[str, Any]) -> dict[str, Any]:
    """
    将 ToolCall 对象转换为字典，用于 SSE 返回给前端。

    特殊处理：
    - 如果工具结果包含 sql 字段（NL2SQL 查询），额外暴露 nl2sql 元数据
    - 如果是 select_database 工具，暴露选中的数据库信息
    """
    if isinstance(call, ToolCall):
        payload = {
            "tool": call.tool,
            "args": call.args,
            "result": call.result.get("content") if isinstance(call.result, dict) else call.result,
            "status": call.status,
        }
        # 如果工具结果是字典且包含 sql 字段，说明是 NL2SQL 查询，暴露更多元数据
        if isinstance(call.result, dict):
            if call.result.get("sql"):
                payload["nl2sql"] = {
                    "steps": call.result.get("steps", []),
                    "sql": call.result.get("sql", ""),
                    "table_name": call.result.get("table_name", ""),
                    "assumptions": call.result.get("assumptions", []),
                    "selected_schema_id": call.result.get("selected_schema_id"),
                    "selected_database": call.result.get("selected_database"),
                }
            # select_database 工具单独暴露选中的数据库信息
            if call.tool == "select_database":
                payload["selected_database"] = call.result.get("selected_database")
                payload["selected_schema_id"] = call.result.get("selected_schema_id")
        return payload
    return call


def _json_default(value: Any) -> str:
    """JSON 序列化时的默认处理函数，将无法序列化的对象转为字符串"""
    return str(value)


def sse_event(event_type: str, data: dict[str, Any]) -> str:
    """
    将事件格式化为 SSE (Server-Sent Events) 标准格式。

    SSE 格式：data: {JSON}\n\n
    前端通过 EventSource 接收这些事件，实现实时推送。
    """
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False, default=_json_default)
    return f"data: {payload}\n\n"


def latest_sql_from_state(state: dict[str, Any]) -> str:
    """
    从状态中提取最新的 SQL，用于前端展示。

    优先级：last_validated_sql > last_generated_sql > 空字符串
    - validated_sql 是经过验证的 SQL，优先使用
    - generated_sql 是 LLM 生成的原始 SQL，作为备选
    """
    return str(state.get("last_validated_sql") or state.get("last_generated_sql") or "")


def build_initial_state(session_id: str, message: str) -> AgentState:
    """
    构建 Agent 的初始状态。

    职责：
    1. 从 SESSION_STORE 恢复该 session 的历史上下文
    2. 处理用户确认/取消逻辑（写操作确认、语义规则确认）
    3. 返回完整的 AgentState 供 Agent 使用

    参数：
    - session_id: 会话标识，用于查找历史状态
    - message: 用户当前输入的消息

    返回：
    - AgentState: 包含所有必要状态的字典
    """
    # 从会话存储中获取历史状态，新 session 返回空字典
    session = SESSION_STORE.get(session_id, {})

    # 获取待确认的操作（写操作或语义规则）
    pending_action = session.get("pending_action")
    pending_semantic_confirmation = session.get("pending_semantic_confirmation")

    # 判断用户是否确认了写操作
    confirmed = message.strip() == "确认执行" and pending_action
    cancelled = pending_action and not confirmed

    # 判断用户是否确认了语义规则
    semantic_confirmed = is_semantic_confirmation(message) and pending_semantic_confirmation
    custom_semantic_rule = is_custom_semantic_rule(message, pending_semantic_confirmation)
    semantic_cancelled = pending_semantic_confirmation and not semantic_confirmed and not custom_semantic_rule

    # 构建 AgentState，包含所有必要的状态字段
    state: AgentState = {
        # 基础输入
        "user_input": message,
        "session_id": session_id,

        # 对话记忆（从 session 恢复）
        "chat_history": session.get("chat_history", []),
        "summary": session.get("summary", ""),

        # 数据库上下文（从 session 恢复）
        "selected_schema_id": session.get("selected_schema_id"),
        "selected_database": session.get("selected_database"),
        "table_schemas": session.get("table_schemas", {}),

        # 执行状态（初始化为空）
        "current_step": "",
        "parsed_intent": None,

        # 执行计划：如果是确认操作，构建确认后的执行计划；否则为空
        "execution_plan": build_confirmed_execution_plan(
            pending_action,
            pending_semantic_confirmation,
            message=message if custom_semantic_rule else "",
        )
        if (confirmed or semantic_confirmed or custom_semantic_rule)
        else [],

        # 工具调用记录（初始化为空）
        "tool_calls": [],

        # 响应：如果是取消操作，设置取消消息
        "response": "已取消执行。" if cancelled else ("已取消语义规则确认。" if semantic_cancelled else ""),
        "needs_confirmation": False,
        "pending_action": None,

        # 确认的操作（如果是确认操作）
        "confirmed_action": pending_action if confirmed else None,

        # NL2SQL 相关状态（从 session 恢复）
        "pending_nl2sql": session.get("pending_nl2sql"),
        "pending_semantic_confirmation": None if (semantic_confirmed or custom_semantic_rule) else session.get("pending_semantic_confirmation"),
        "last_nl2sql_task": session.get("last_nl2sql_task"),
        "nl2sql_task_stack": session.get("nl2sql_task_stack"),
        "last_generated_sql": session.get("last_generated_sql"),
        "last_validated_sql": session.get("last_validated_sql"),
        "last_result_preview": session.get("last_result_preview", []),
        "last_result_summary": session.get("last_result_summary"),
        "last_query_topic": session.get("last_query_topic"),
        "followup_patch": session.get("followup_patch"),
        "long_term_memory_hints": session.get("long_term_memory_hints", []),
    }

    # 如果用户取消了写操作，清除待确认状态
    if cancelled:
        SESSION_STORE[session_id] = {**session, "pending_action": None, "needs_confirmation": False}

    # 如果用户取消了语义规则确认，清除待确认状态
    if semantic_cancelled:
        SESSION_STORE[session_id] = {**session, "pending_semantic_confirmation": None}

    return state


def is_semantic_confirmation(message: str) -> bool:
    """判断用户消息是否是确认语义规则的简单回复（如"确认""记住""是"等）"""
    normalized = message.strip().lower()
    return normalized in {"确认", "记住", "是", "yes", "y", "确认记住"}


def is_custom_semantic_rule(message: str, pending_semantic_confirmation: dict[str, Any] | None) -> bool:
    """
    判断用户消息是否是自定义语义规则修正（而非简单确认）。
    例如用户说"有效订单其实是 order_status = 'paid'"，
    这不是简单确认，而是提供了修正后的业务口径。
    """
    if not pending_semantic_confirmation:
        return False
    context = semantic_context_from_pending(pending_semantic_confirmation)
    return parse_custom_semantic_rule(message, context) is not None or looks_like_natural_language_semantic_rule(message)


def looks_like_natural_language_semantic_rule(message: str) -> bool:
    """
    判断消息是否看起来像自然语言形式的语义规则。
    匹配模式："<业务词> 其实是/就是/是/= <SQL 条件>"
    例如："有效订单其实是 order_status = 'paid'"
    """
    text = message.strip()
    return bool(re.search(r"[一-鿿A-Za-z0-9_ -]{1,40}?(?:其实是|就是|是|=|：|:).+", text))


def semantic_context_from_pending(pending_semantic_confirmation: dict[str, Any]) -> SemanticContext:
    """
    从待确认的语义规则中提取语义上下文。
    将字典转换为 SemanticContext 对象，用于校验字段是否存在于当前表。
    """
    raw_context = pending_semantic_confirmation.get("context") or {}
    return SemanticContext(
        schema_id=raw_context.get("schema_id"),
        database=raw_context.get("database", ""),
        domain=raw_context.get("domain", ""),
        tables=tuple(raw_context.get("tables") or ()),
        columns=tuple(ColumnSchema(**column) for column in raw_context.get("columns") or ()),
        user_input=raw_context.get("user_input", ""),
    )


def build_confirmed_execution_plan(
    pending_action: dict[str, Any] | None,
    pending_semantic_confirmation: dict[str, Any] | None,
    message: str = "",
) -> list[dict[str, Any]]:
    """
    构建用户确认后的执行计划。

    三种情况：
    1. 用户确认了写操作 → 直接执行原 pending_action
    2. 用户简单确认了语义规则 → 执行 confirm_semantic_rules，然后恢复原查询
    3. 用户提供了自定义规则 → 执行 save_custom_semantic_rule，然后恢复原查询
    """
    # 情况1：用户确认了写操作，直接执行原计划
    if pending_action:
        return [pending_action]
    if not pending_semantic_confirmation:
        return []
    # 情况2/3：先保存/确认语义规则
    tool = "save_custom_semantic_rule" if message else "confirm_semantic_rules"
    args = {"pending": pending_semantic_confirmation}
    if message:
        args["message"] = message
    plan = [{"tool": tool, "args": args}]
    # 如果语义规则确认时有待恢复的查询，追加到执行计划
    resume = pending_semantic_confirmation.get("resume") or {}
    if resume:
        plan.append({"tool": "nl2sql_query", "args": resume})
    return plan


def save_session(final_state: AgentState) -> None:
    """
    保存 Agent 执行后的最终状态到会话存储。

    职责：
    1. 追加本轮对话到聊天历史（保留最近 20 条）
    2. 更新摘要、数据库上下文、NL2SQL 记忆等
    3. 处理待确认操作的持久化

    参数：
    - final_state: Agent 执行后的最终状态
    """
    session_id = final_state["session_id"]
    previous = SESSION_STORE.get(session_id, {})
    history = previous.get("chat_history", [])

    # 如果有响应，追加本轮对话到历史（保留最近 20 条，避免历史过长）
    if final_state.get("response"):
        history = history + [
            {"role": "user", "content": final_state.get("user_input", "")},
            {"role": "assistant", "content": final_state.get("response", "")},
        ]
        history = history[-20:]

    # 更新会话存储，优先使用新状态，如果没有则保留旧状态
    SESSION_STORE[session_id] = {
        "chat_history": history,
        "summary": final_state.get("summary", previous.get("summary", "")),
        "selected_schema_id": final_state.get("selected_schema_id", previous.get("selected_schema_id")),
        "selected_database": final_state.get("selected_database", previous.get("selected_database")),
        "table_schemas": final_state.get("table_schemas", previous.get("table_schemas", {})),
        # 只有在需要确认时才保存 pending_action，否则清空
        "pending_action": final_state.get("pending_action") if final_state.get("needs_confirmation") else None,
        "pending_nl2sql": final_state.get("pending_nl2sql"),
        "pending_semantic_confirmation": final_state.get("pending_semantic_confirmation"),
        # NL2SQL 追问记忆：优先使用新状态，如果没有则保留旧状态
        "last_nl2sql_task": final_state.get("last_nl2sql_task", previous.get("last_nl2sql_task")),
        "nl2sql_task_stack": final_state.get("nl2sql_task_stack", previous.get("nl2sql_task_stack")),
        "last_generated_sql": final_state.get("last_generated_sql", previous.get("last_generated_sql")),
        "last_validated_sql": final_state.get("last_validated_sql", previous.get("last_validated_sql")),
        "last_result_preview": final_state.get("last_result_preview", previous.get("last_result_preview", [])),
        "last_result_summary": final_state.get("last_result_summary", previous.get("last_result_summary")),
        "last_query_topic": final_state.get("last_query_topic", previous.get("last_query_topic")),
        "followup_patch": final_state.get("followup_patch", previous.get("followup_patch")),
        "long_term_memory_hints": final_state.get(
            "long_term_memory_hints", previous.get("long_term_memory_hints", [])
        ),
        "needs_confirmation": final_state.get("needs_confirmation", False),
    }


async def run_agent_stream(initial_state: AgentState) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    运行 Agent 流，逐步产出事件。

    职责：
    1. 处理取消操作的快速返回
    2. 调用 agent_graph.astream() 启动 LangGraph 执行
    3. 逐节点产出 step 事件
    4. 执行完成后保存会话并产出 final 事件

    参数：
    - initial_state: 初始状态

    产出：
    - (event_type, data) 元组
      - event_type: "step" 或 "final"
      - data: 事件数据
    """
    # 快速返回：如果是取消操作，直接返回取消消息，不执行 Agent
    if initial_state.get("response") in {"已取消执行。", "已取消语义规则确认。"}:
        save_session(initial_state)
        yield "final", {
            "session_id": initial_state["session_id"],
            "reply": initial_state["response"],
            "tool_calls": [],
            "needs_confirmation": False,
            "latest_sql": latest_sql_from_state(initial_state),
        }
        return

    # 启动 LangGraph Agent 执行流
    final_state: AgentState | None = None
    async for update in agent_graph.astream(initial_state):
        # 每个 update 是 {node_name: node_state} 字典
        node_name, node_state = next(iter(update.items()))
        # 合并状态：将新节点的状态合并到最终状态中
        final_state = {**(final_state or initial_state), **node_state}
        # 产出 step 事件，前端可以实时展示每个节点的执行过程
        yield "step", {"step": node_name, "state": node_state}

    # 如果没有执行任何节点（不应该发生），使用 initial_state
    if final_state is None:
        final_state = initial_state

    # 保存最终状态到会话存储
    save_session(final_state)

    # 产出 final 事件，包含最终响应
    yield "final", {
        "session_id": final_state["session_id"],
        "reply": final_state.get("response", ""),
        "tool_calls": [_tool_call_to_dict(call) for call in final_state.get("tool_calls", [])],
        "needs_confirmation": final_state.get("needs_confirmation", False),
        "latest_sql": latest_sql_from_state(final_state),
    }


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    SSE 流式输出接口 - 用户请求的主入口。

    数据流：
    1. 接收用户消息（session_id + message）
    2. 构建初始状态（从 SESSION_STORE 恢复上下文）
    3. 运行 Agent 流，逐步产出事件
    4. 将事件格式化为 SSE 格式并返回

    前端通过 EventSource 接收 SSE 事件，实时展示执行过程。
    """

    async def event_stream() -> AsyncIterator[str]:
        # 1. 构建初始状态（从会话存储中恢复上下文）
        initial_state = build_initial_state(request.session_id, request.message)

        # 2. 运行 Agent 流，逐步产出事件
        async for event_type, data in run_agent_stream(initial_state):
            # 3. 将事件转换为 SSE 格式并发送给客户端
            yield sse_event(event_type, data)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest) -> ChatResponse:
    """
    同步接口 - 用于测试和集成。

    与 /chat 接口功能相同，但不使用 SSE 流式输出，
    而是等待 Agent 执行完成后一次性返回最终结果。
    """
    final_payload: dict[str, Any] = {}
    initial_state = build_initial_state(request.session_id, request.message)
    # 运行 Agent 流，但只取 final 事件
    async for event_type, data in run_agent_stream(initial_state):
        if event_type == "final":
            final_payload = data
    return ChatResponse(**final_payload)


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket 双向通信接口。

    与 SSE 接口功能相同，但使用 WebSocket 协议，
    支持双向通信，适合需要实时交互的场景。
    """
    await websocket.accept()
    try:
        # 持续接收消息，直到客户端断开连接
        while True:
            message = await websocket.receive_text()
            initial_state = build_initial_state(session_id, message)
            async for event_type, data in run_agent_stream(initial_state):
                await websocket.send_json({"type": event_type, **data})
    except WebSocketDisconnect:
        # 客户端断开连接，正常退出
        return


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """
    获取会话信息接口。

    用于前端页面刷新或切换 session 后恢复状态，
    返回会话的摘要、选中的数据库、最新 SQL 等信息。
    """
    session = SESSION_STORE.get(session_id, {})
    return SessionResponse(
        session_id=session_id,
        summary=session.get("summary", ""),
        selected_schema_id=session.get("selected_schema_id"),
        selected_database=session.get("selected_database"),
        needs_confirmation=session.get("needs_confirmation", False),
        latest_sql=latest_sql_from_state(session),
    )
