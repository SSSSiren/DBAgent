"""
API 请求/响应模型定义

使用 Pydantic 定义数据验证模型，确保：
1. 请求参数类型正确
2. 响应格式统一
3. 自动序列化/反序列化
"""

from pydantic import BaseModel
from typing import Optional, Any


class ChatRequest(BaseModel):
    """
    聊天请求模型

    Attributes:
        message: 用户输入的消息内容
        session_id: 会话唯一标识，用于追踪对话历史和上下文
    """
    message: str
    session_id: str


class ChatResponse(BaseModel):
    """
    聊天响应模型（同步接口使用）

    Attributes:
        response: 助手的回复内容
        session_id: 会话 ID
        needs_confirmation: 是否需要用户确认（如写操作）
    """
    response: str
    session_id: str
    needs_confirmation: bool = False


class SessionState(BaseModel):
    """
    会话状态模型

    用于返回会话的完整状态信息，包括：
    - 对话历史
    - 对话摘要
    - 当前选择的数据库上下文

    Attributes:
        session_id: 会话 ID
        chat_history: 对话历史，格式为 [{"role": "user/assistant", "content": "..."}]
        summary: 对话摘要（压缩后的上下文）
        selected_schema_id: 当前选择的数据库 schema ID
        selected_database: 当前选择的数据库详细信息
    """
    session_id: str
    chat_history: list[dict] = []
    summary: str = ""
    selected_schema_id: Optional[int] = None
    selected_database: Optional[dict] = None
