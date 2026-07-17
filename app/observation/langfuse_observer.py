"""
Langfuse 可观测性模块

为 DBAgent 提供 LLM 调用链路追踪，重点观测指标：
- Token 消耗：Langfuse CallbackHandler 自动捕获
- 工具调用次数：Agent 循环中累加，写入 trace metadata
- 推理步骤：统计 LLM 推理调用次数，写入 trace metadata
- 捞出的数据大小：记录 result row count / column count，写入 span metadata
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# 延迟初始化，避免导入时就必须连接 Langfuse
_langfuse_client: Any = None
_langfuse_initialized: bool = False


def _is_configured() -> bool:
    """检查 Langfuse 是否已配置"""
    return bool(
        settings.LANGFUSE_ENABLED
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
        and "xxx" not in settings.LANGFUSE_PUBLIC_KEY  # 排除占位符
    )


def get_langfuse_client() -> Any:
    """获取 Langfuse 客户端实例（延迟初始化）"""
    global _langfuse_client, _langfuse_initialized

    if not _is_configured():
        return None

    if not _langfuse_initialized:
        try:
            from langfuse import Langfuse

            _langfuse_client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST,
            )
            _langfuse_initialized = True
            logger.info("Langfuse client initialized, host=%s", settings.LANGFUSE_HOST)
        except Exception as e:
            logger.warning("Failed to initialize Langfuse client: %s", e)
            _langfuse_initialized = True  # 不反复重试

    return _langfuse_client


def create_trace_and_handler(
    session_id: str = "",
    trace_name: str = "DBAgent-Chat",
    user_id: str = "",
) -> tuple[Any, Any] | tuple[None, None]:
    """
    创建 Langfuse Trace 和对应的 LangChain CallbackHandler

    使用 trace.get_langchain_handler() 方式，这样我们可以持有 trace 引用，
    在 Agent 执行完成后将自定义观测指标写入 trace metadata。

    CallbackHandler 会自动追踪：
    - 每一次 LLM 调用（prompt、completion、token 消耗、延迟、cost）
    - 每一次工具调用（工具名、输入参数、输出结果）
    - Chain 执行链路

    Args:
        session_id: 会话 ID，用于关联同一对话的多轮请求
        trace_name: trace 名称，在 Langfuse UI 中显示
        user_id: 用户标识

    Returns:
        (CallbackHandler, Trace) 元组，或 (None, None)（未配置时）
    """
    if not _is_configured():
        return None, None

    try:
        client = get_langfuse_client()
        if client is None:
            return None, None

        trace = client.trace(
            name=trace_name,
            session_id=session_id,
            user_id=user_id or "anonymous",
            tags=["dbagent"],
        )
        handler = trace.get_langchain_handler()
        logger.info("Langfuse trace created: id=%s, session=%s", trace.id, session_id)
        return handler, trace
    except Exception as e:
        logger.warning("Failed to create Langfuse trace: %s", e)
        return None, None


def create_callback(session_id: str = "", trace_name: str = "DBAgent-Chat") -> Any:
    """
    创建 LangChain CallbackHandler（兼容旧接口）

    该 handler 会自动追踪：
    - 每一次 LLM 调用（prompt、completion、token 消耗、延迟、cost）
    - 每一次工具调用（工具名、输入参数、输出结果）
    - Chain 执行链路

    Args:
        session_id: 会话 ID，用于关联同一对话的多轮请求
        trace_name: trace 名称，在 Langfuse UI 中显示

    Returns:
        CallbackHandler 实例，或 None（未配置时）
    """
    handler, _ = create_trace_and_handler(session_id=session_id, trace_name=trace_name)
    return handler


# ============================================================
# 观测指标收集
# ============================================================


@dataclass
class TraceMetrics:
    """
    单次 Agent 执行周期的观测指标

    在 Agent 流式执行过程中逐步累加，最后写入 Langfuse trace。
    """

    # 推理步骤：LLM 推理调用次数（每次 on_chat_model_end 算一次）
    llm_call_count: int = 0

    # 工具调用：各工具被调用的次数
    tool_call_count: int = 0
    tool_call_details: dict[str, int] = field(default_factory=dict)

    # 数据大小：从各工具中提取的数据量
    # (rows, columns) per tool call
    data_sizes: list[dict[str, Any]] = field(default_factory=list)

    # 总 token（由 CallbackHandler 自动计算，这里做汇总）
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def record_llm_call(self) -> None:
        """记录一次 LLM 推理调用"""
        self.llm_call_count += 1

    def record_tool_call(self, tool_name: str) -> None:
        """记录一次工具调用"""
        self.tool_call_count += 1
        self.tool_call_details[tool_name] = self.tool_call_details.get(tool_name, 0) + 1

    def record_data_size(self, tool_name: str, row_count: int, col_count: int) -> None:
        """记录一次工具返回的数据大小"""
        self.data_sizes.append({
            "tool": tool_name,
            "rows": row_count,
            "columns": col_count,
        })

    def total_rows(self) -> int:
        """累计捞出的总行数"""
        return sum(d["rows"] for d in self.data_sizes)

    def to_metadata(self) -> dict[str, Any]:
        """将指标转为 Langfuse trace metadata"""
        return {
            "llm_call_count": self.llm_call_count,
            "tool_call_count": self.tool_call_count,
            "tool_call_details": self.tool_call_details,
            "total_data_rows": self.total_rows(),
            "data_size_details": self.data_sizes,
        }

    def to_score_comment(self) -> str:
        """生成可读的观测摘要"""
        lines = [
            f"🔢 推理步骤: {self.llm_call_count}",
            f"🔧 工具调用: {self.tool_call_count}",
        ]
        for tool_name, count in self.tool_call_details.items():
            lines.append(f"  - {tool_name}: {count} 次")
        lines.append(f"📊 捞取数据总行数: {self.total_rows()}")
        return "\n".join(lines)


def extract_result_size(result: str) -> tuple[int, int]:
    """
    从工具返回的 Markdown 表格字符串中提取数据大小

    format_as_markdown_table 输出的最后一行格式为：
    "共 N 行" 或 "共 N 行，已显示前 M 行"

    Returns:
        (row_count, col_count)
    """
    import re

    row_count = 0
    col_count = 0

    # 提取列数（表格头中 | 的数量 - 1）
    # 先找表头行（后面紧跟 |---|---| 分隔行）
    lines = result.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("|") and i + 1 < len(lines):
            # 检查下一行是否是分隔行
            next_line = lines[i + 1]
            if next_line.startswith("|") and "---" in next_line:
                col_count = line.count("|") - 1
                break

    # 提取行数："共 N 行"
    match = re.search(r"共\s*(\d+)\s*行", result)
    if match:
        row_count = int(match.group(1))

    return row_count, col_count


def flush_metrics(
    trace: Any,
    metrics: TraceMetrics,
) -> None:
    """
    将观测指标写入 Langfuse trace

    在 Agent 执行完成后调用，将自定义指标（工具调用次数、推理步骤、数据大小）
    作为 trace metadata 写入，同时在 trace 上创建一条 score comment 作为可读摘要。

    Token 消耗由 CallbackHandler 自动捕获，不需要手动写入。

    Args:
        trace: Langfuse Trace 对象
        metrics: 累计的观测指标
    """
    if trace is None:
        return

    try:
        trace.update(
            metadata=metrics.to_metadata(),
        )
        # 创建一条 score 级别的观测摘要
        trace.score(
            name="observation_summary",
            value=metrics.llm_call_count,
            comment=metrics.to_score_comment(),
        )
        logger.info(
            "Langfuse metrics flushed: trace=%s, llm_calls=%d, tool_calls=%d, rows=%d",
            trace.id,
            metrics.llm_call_count,
            metrics.tool_call_count,
            metrics.total_rows(),
        )
    except Exception as e:
        logger.warning("Failed to flush Langfuse metrics: %s", e)
