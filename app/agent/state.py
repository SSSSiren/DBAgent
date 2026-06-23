# ============================================================================
# Agent 状态定义 — AgentState 和 ToolCall
# ============================================================================
# 这个文件定义了 LangGraph Agent 的核心数据结构：
#
# 1. ToolCall — 工具调用记录（dataclass）
#    记录每一次工具调用的名称、参数、结果和状态
#
# 2. AgentState — Agent 状态字典（TypedDict）
#    贯穿整个 Agent 执行过程的状态容器，每个节点读取并更新它
#
# LangGraph 的状态管理机制：
#   - 每个节点函数接收 AgentState，返回一个 partial dict
#   - LangGraph 自动将返回的 dict 合并到当前状态中
#   - total=False 表示所有字段都是可选的，节点只需返回需要更新的字段
# ============================================================================

from dataclasses import dataclass
from typing import Any, Optional, TypedDict


# ============================================================================
# ToolCall — 工具调用记录
# ============================================================================
# 每次工具调用都会创建一个 ToolCall 实例，追加到 state["tool_calls"] 列表。
# 生命周期：pending → running → completed / failed
#
# 使用场景：
#   - act_node 创建 ToolCall 并执行工具
#   - reflect_node 检查最后一个 ToolCall 的状态
#   - summarize_node 遍历所有 ToolCall 生成最终响应
#   - routes.py 通过 _tool_call_to_dict 将 ToolCall 转为字典返回给前端
# ============================================================================

@dataclass
class ToolCall:
    """记录一次工具调用的完整信息"""

    tool: str                           # 工具名称，如 "execute_sql"、"nl2sql_query"
    args: dict[str, Any]                # 工具调用参数
    result: Optional[Any] = None        # 工具返回结果，执行前为 None
    status: str = "pending"             # 状态：pending / running / completed / failed


# ============================================================================
# AgentState — Agent 状态字典
# ============================================================================
# 这是 LangGraph 状态图的核心数据结构。每个节点函数签名都是：
#   async def xxx_node(state: AgentState) -> dict[str, Any]
#
# 节点读取 state 中的字段做决策，返回一个 partial dict 来更新状态。
# LangGraph 会自动将返回的 dict 合并（shallow merge）到当前状态中。
#
# total=False 表示所有字段都是 Optional 的，节点不需要返回所有字段。
# ============================================================================

class AgentState(TypedDict, total=False):

    # -----------------------------------------------------------------------
    # 第一类：基础输入 — 每轮请求的原始输入
    # -----------------------------------------------------------------------
    user_input: str                                         # 用户当前输入的消息
    session_id: str                                         # 会话标识，用于查找/保存会话状态

    # -----------------------------------------------------------------------
    # 第二类：对话记忆 — 跨轮次的上下文保持
    # -----------------------------------------------------------------------
    chat_history: list[dict[str, Any]]                      # 最近 20 条对话历史（user/assistant 交替）
    summary: str                                            # LLM 压缩的对话摘要，保留关键信息

    # -----------------------------------------------------------------------
    # 第三类：数据库上下文 — 当前会话选中的库和已加载的表结构
    # -----------------------------------------------------------------------
    selected_schema_id: Optional[int]                       # 当前选中的数据库 schema ID
    selected_database: Optional[dict[str, Any]]             # 选中的数据库详细信息（schemaName, instanceName 等）
    table_schemas: dict[str, list[dict[str, Any]]]          # 表结构缓存：{表名: [字段列表]}

    # -----------------------------------------------------------------------
    # 第四类：执行过程 — Agent 执行期间的中间状态
    # -----------------------------------------------------------------------
    current_step: str                                       # 当前执行的节点名称（understand/plan/act/reflect/finish）
    parsed_intent: Optional[dict[str, Any]]                 # understand_node 解析出的用户意图
    execution_plan: list[dict[str, Any]]                    # 待执行的工具调用队列：[{"tool": "...", "args": {...}}, ...]
    tool_calls: list[ToolCall]                              # 已执行的工具调用记录列表
    response: str                                           # 最终返回给用户的响应文本
    needs_confirmation: bool                                # 是否需要用户确认（写操作场景）
    pending_action: Optional[dict[str, Any]]                # 待确认的写操作（用户说"确认执行"后继续）
    confirmed_action: Optional[dict[str, Any]]              # 用户已确认的操作，用于 act_node 跳过二次确认

    # -----------------------------------------------------------------------
    # 第五类：NL2SQL 追问记忆 — 支撑多轮追问能力的结构化状态
    # -----------------------------------------------------------------------
    # --- 待处理状态 ---
    pending_nl2sql: Optional[dict[str, Any]]                # 多库候选时保存的未完成的 NL2SQL 查询
    pending_semantic_confirmation: Optional[dict[str, Any]] # 待用户确认的业务语义规则候选

    # --- 上一轮查询的结构化任务（追问的核心） ---
    last_nl2sql_task: Optional[dict[str, Any]]              # 上一轮 NL2SQL 的完整结构化任务
    #   包含：database, table, operation, select_fields, where, group_by,
    #         order_by, limit, time_field, table_schema, sql, assumptions
    #   追问时通过 patch 这个 task 来重建 SQL，而不是直接修改 SQL 字符串

    nl2sql_task_stack: Optional[dict[str, Any]]             # 任务版本栈（预留，支持"撤回"操作）

    # --- 上一轮查询的 SQL 和结果 ---
    last_generated_sql: Optional[str]                       # 上一轮 LLM 生成的原始 SQL
    last_validated_sql: Optional[str]                       # 上一轮经过 validator 校验的 SQL（优先级更高）
    last_result_preview: list[dict[str, Any]]               # 上一轮查询结果的前 20 行预览
    last_result_summary: Optional[dict[str, Any]]           # 上一轮结果摘要：{row_count, columns, top_rows, empty}

    # --- 其他追问相关 ---
    last_query_topic: Optional[str]                         # 上一轮查询主题（预留）
    followup_patch: Optional[dict[str, Any]]                # 最近一次追问的 patch 信息
    long_term_memory_hints: list[dict[str, Any]]            # 长期领域记忆提示（预留）
