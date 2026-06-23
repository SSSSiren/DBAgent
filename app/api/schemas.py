"""
API 请求/响应模型
"""

from pydantic import BaseModel
from typing import Optional, Any


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: str


class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    session_id: str
    needs_confirmation: bool = False


class SessionState(BaseModel):
    """会话状态"""
    session_id: str
    chat_history: list[dict] = []
    summary: str = ""
    selected_schema_id: Optional[int] = None
    selected_database: Optional[dict] = None
