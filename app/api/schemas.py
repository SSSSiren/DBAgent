"""
API 数据模型 — Pydantic 请求/响应模型

参考 DBAgent 的 app/api/schemas.py
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: str = Field(default="default", description="会话 ID")
    user_id: str = Field(default="default", description="用户标识（用于多用户记忆隔离）")
    message: str = Field(..., description="用户消息")


class ChatResponse(BaseModel):
    """同步聊天响应"""
    response: str = Field(default="", description="Agent 回复")
    session_id: str = Field(default="", description="会话 ID")
    needs_confirmation: bool = Field(default=False, description="是否需要用户确认")


class SessionState(BaseModel):
    """会话状态"""
    session_id: str = Field(default="", description="会话 ID")
    chat_history: list[dict[str, str]] = Field(default_factory=list, description="对话历史")
    summary: str = Field(default="", description="对话摘要")
    selected_schema_id: Optional[int] = Field(default=None, description="已选数据库 schema ID")
    selected_database: Optional[dict[str, Any]] = Field(default=None, description="已选数据库详情")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    engine: str = "openai-fallback"