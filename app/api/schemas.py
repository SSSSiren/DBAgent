from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    needs_confirmation: bool = False


class SessionResponse(BaseModel):
    session_id: str
    summary: str = ""
    selected_schema_id: int | None = None
    selected_database: dict[str, Any] | None = None
    needs_confirmation: bool = False
