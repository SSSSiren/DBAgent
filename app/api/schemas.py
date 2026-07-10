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
    latest_sql: str = Field(default="", description="最近生成的 SQL 语句")
    memory_count: int = Field(default=0, description="长期记忆条数")
    preference_count: int = Field(default=0, description="操作记忆中的偏好表数量")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    engine: str = "openai-fallback"


# ── Session CRUD Models ──────────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    """会话创建请求"""
    user_id: str = Field(..., min_length=1, description="用户标识（必填，非空）")


class SessionSummary(BaseModel):
    """会话摘要信息"""
    session_id: str = Field(..., description="会话 ID")
    summary: str = Field(default="", description="会话摘要")
    created_at: str = Field(..., description="创建时间（ISO 8601）")
    last_active_at: str = Field(..., description="最近活动时间（ISO 8601）")
    message_count: int = Field(default=0, description="消息数量")


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: list[SessionSummary] = Field(default_factory=list, description="会话摘要列表")
    total_count: int = Field(default=0, description="会话总数")


class SessionCreateResponse(BaseModel):
    """会话创建响应"""
    session_id: str = Field(..., description="新创建的会话 ID")
    user_id: str = Field(..., description="用户标识")
    created_at: str = Field(..., description="创建时间（ISO 8601）")


class SessionDeleteResponse(BaseModel):
    """会话删除响应"""
    deleted: bool = Field(..., description="是否删除成功")
    session_id: str = Field(..., description="被删除的会话 ID")