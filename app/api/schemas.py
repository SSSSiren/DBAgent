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
    schema_id: Optional[int] = Field(default=None, description="OneDBA schema ID（用于 HDC/SQL Memory 检索）")
    database_name: Optional[str] = Field(default=None, description="数据库名称（用于 HDC/SQL Memory 检索）")
    hdc_namespace: Optional[str] = Field(default=None, description="HDC 知识库命名空间（如 recall_extra）")


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


class SessionUpdateRequest(BaseModel):
    """会话更新请求"""
    summary: str = Field(default="", description="会话摘要/标题")


class SessionUpdateResponse(BaseModel):
    """会话更新响应"""
    session_id: str = Field(..., description="会话 ID")
    summary: str = Field(default="", description="更新后的会话摘要")


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


class CancelResponse(BaseModel):
    """取消 Agent 执行响应"""
    cancelled: bool = Field(..., description="是否成功触发取消；false 表示该会话没有活跃的 Agent 执行")
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(default="", description="状态描述")


# ── Admin API Models ───────────────────────────────────────────────────────────


class HdcMappingCreate(BaseModel):
    """HDC namespace 映射创建/更新请求"""
    user_id: str = Field(..., min_length=1, description="用户标识")
    schema_id: int = Field(..., gt=0, description="OneDBA schema ID")
    database_name: str = Field(..., min_length=1, description="数据库名称")
    hdc_namespace: str = Field(..., min_length=1, description="HDC 知识库命名空间")


class HdcMappingResponse(BaseModel):
    """HDC namespace 映射响应"""
    user_id: str = Field(..., description="用户标识")
    schema_id: int = Field(..., description="OneDBA schema ID")
    database_name: str = Field(..., description="数据库名称")
    hdc_namespace: str = Field(..., description="HDC 知识库命名空间")
    updated_at: str = Field(..., description="更新时间（ISO 8601）")


class SqlMemoryStatusResponse(BaseModel):
    """SQL Memory 状态概览响应"""
    total_records: int = Field(..., description="总记录数")
    embedding_coverage: float = Field(..., description="embedding 覆盖率")
    status_distribution: dict = Field(default_factory=dict, description="状态分布")
    earliest_record: Optional[str] = Field(default=None, description="最早记录时间（ISO 8601）")
    latest_record: Optional[str] = Field(default=None, description="最晚记录时间（ISO 8601）")


class SqlMemoryRecordResponse(BaseModel):
    """SQL Memory 记录响应（不含 embedding_json）"""
    id: str = Field(..., description="记录 ID")
    user_id: str = Field(..., description="用户标识")
    question: str = Field(..., description="用户问题")
    sql_text: str = Field(..., description="SQL 文本")
    sql_truncated: str = Field(..., description="截断后的 SQL 文本")
    table_names: list[str] = Field(default_factory=list, description="涉及的表名列表")
    database_name: str = Field(..., description="数据库名称")
    schema_id: int = Field(..., description="OneDBA schema ID")
    execution_status: str = Field(..., description="执行状态")
    created_at: str = Field(..., description="创建时间（ISO 8601）")
    has_embedding: bool = Field(..., description="是否有 embedding")


class SqlMemoryListResponse(BaseModel):
    """SQL Memory 记录列表响应"""
    records: list[SqlMemoryRecordResponse] = Field(default_factory=list, description="记录列表")
    total: int = Field(..., description="总记录数")
    limit: int = Field(..., description="每页条数")
    offset: int = Field(..., description="偏移量")


class SqlMemoryStatsResponse(BaseModel):
    """SQL Memory 统计分析响应"""
    table_distribution: dict = Field(default_factory=dict, description="表分布")
    database_distribution: dict = Field(default_factory=dict, description="数据库分布")
    daily_histogram: dict = Field(default_factory=dict, description="每日记录直方图")
    mined_patterns: Optional[dict] = Field(default=None, description="挖掘出的查询模式")


class HdcNamespaceSummary(BaseModel):
    """HDC namespace 摘要"""
    schema_id: int = Field(..., description="OneDBA schema ID")
    database_name: str = Field(..., description="数据库名称")
    namespace_count: int = Field(..., description="namespace 数量")


class OverviewResponse(BaseModel):
    """系统概览响应"""
    distinct_users: int = Field(..., description="不重复用户数")
    total_sessions: int = Field(..., description="会话总数")
    sql_memory_records: int = Field(..., description="SQL Memory 记录总数")
    mapped_hdc_namespaces: list[HdcNamespaceSummary] = Field(default_factory=list, description="已映射的 HDC namespace 摘要列表")


class CleanRequest(BaseModel):
    """SQL Memory 清理请求"""
    user_id: Optional[str] = Field(default="", description="按用户过滤（空字符串表示全部）")
    database_name: Optional[str] = Field(default="", description="按数据库过滤（空字符串表示全部）")
    older_than_days: Optional[int] = Field(default=None, gt=0, description="清理 N 天前的记录")


class ReEmbedRequest(BaseModel):
    """SQL Memory embedding 重建请求"""
    user_id: Optional[str] = Field(default="", description="按用户过滤（空字符串表示全部）")