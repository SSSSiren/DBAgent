from dataclasses import dataclass
from typing import Any, Optional, TypedDict


@dataclass
class ToolCall:
    """Record for one tool invocation."""

    tool: str
    args: dict[str, Any]
    result: Optional[str] = None
    status: str = "pending"


class AgentState(TypedDict, total=False):
    user_input: str
    session_id: str
    chat_history: list[dict[str, Any]]
    summary: str
    selected_schema_id: Optional[int]
    selected_database: Optional[dict[str, Any]]
    table_schemas: dict[str, list[dict[str, Any]]]
    current_step: str
    parsed_intent: Optional[dict[str, Any]]
    execution_plan: list[dict[str, Any]]
    tool_calls: list[ToolCall]
    response: str
    needs_confirmation: bool
    pending_action: Optional[dict[str, Any]]
    confirmed_action: Optional[dict[str, Any]]
