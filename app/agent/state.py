"""
Agent 状态定义
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Agent 状态"""

    # 基础输入
    user_input: str
    session_id: str

    # 对话记忆
    chat_history: list[dict]
    summary: str

    # 数据库上下文
    selected_schema_id: int | None
    selected_database: dict | None

    # Agent 执行状态（由 AgentExecutor 管理）
    intermediate_steps: list[tuple]

    # 最终输出
    response: str

    # 确认状态
    needs_confirmation: bool
    pending_action: dict | None
