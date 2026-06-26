"""
Agent 状态定义

定义 Agent 执行过程中的状态结构，包括：
- 输入：用户消息、会话 ID
- 上下文：对话历史、摘要、已选数据库
- 执行状态：中间步骤、确认状态
- 输出：最终响应

使用 TypedDict 定义，确保类型安全和 IDE 提示
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """
    Agent 状态字典

    在 Agent 执行流程中传递的状态对象，包含：
    1. 用户输入和会话标识
    2. 对话记忆（历史消息 + 摘要）
    3. 数据库上下文（当前选择的数据库）
    4. Agent 执行状态（中间步骤、确认状态）
    5. 最终输出

    Attributes:
        user_input: 用户当前输入的消息
        session_id: 会话唯一标识，用于追踪对话历史
        chat_history: 对话历史，LangChain 消息对象列表（HumanMessage/AIMessage）
        summary: 对话摘要，用于上下文压缩（不超过 500 字）
        selected_schema_id: 当前选择的数据库 schema ID
        selected_database: 当前选择的数据库详细信息（包含 schemaName, instanceName 等）
        intermediate_steps: Agent 执行的中间步骤（工具调用记录）
        response: Agent 的最终响应内容
        needs_confirmation: 是否需要用户确认（如写操作）
        pending_action: 待确认的操作信息（包含工具名、参数等）
    """

    # ========== 基础输入 ==========
    user_input: str           # 用户当前输入的消息
    session_id: str           # 会话唯一标识

    # ========== 对话记忆 ==========
    chat_history: list[dict]  # 对话历史（LangChain 消息对象列表）
    summary: str              # 对话摘要（压缩后的上下文）

    # ========== 数据库上下文 ==========
    selected_schema_id: int | None   # 当前选择的数据库 schema ID
    selected_database: dict | None   # 当前选择的数据库详细信息

    # ========== Agent 执行状态 ==========
    intermediate_steps: list[tuple]  # 中间步骤（工具调用记录）

    # ========== 最终输出 ==========
    response: str                    # Agent 的最终响应

    # ========== 确认状态 ==========
    needs_confirmation: bool         # 是否需要用户确认（写操作）
    pending_action: dict | None      # 待确认的操作信息
