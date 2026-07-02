"""
Langfuse 可观测性 — trace 和 metrics 收集

参考 DBAgent 的 app/observation/langfuse_observer.py

在 SDK 模式下，Langfuse 不再通过 LangChain CallbackHandler 集成，
而是通过手动埋点在 Agent 执行过程中创建 trace 和 span。

v4.x API 迁移说明：
- client.trace() → client.start_observation(as_type="span")
- trace.span()   → parent_span.start_observation(as_type=...)
- trace.update() → span.update()
- trace.score()  → span.score()
- span 需要显式 .end() 调用
- session_id/user_id/tags 通过 span.update(**kwargs) 传入

Tool span 生命周期：
- tool_start → record_tool_call() 创建 span，不 end
- tool_end   → update_tool_result() 补充 output，end span
- flush()    → 兜底：end 所有未关闭的 span（SDK MCP 模式无 tool_end 时）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings


@dataclass
class TraceMetrics:
    """Agent 执行指标"""

    llm_call_count: int = 0
    tool_call_count: int = 0
    tool_call_details: dict[str, int] = field(default_factory=dict)
    data_sizes: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_llm_call(self) -> None:
        self.llm_call_count += 1

    def record_tool_call(self, tool_name: str) -> None:
        self.tool_call_count += 1
        self.tool_call_details[tool_name] = (
            self.tool_call_details.get(tool_name, 0) + 1
        )

    def record_data_size(
        self, tool_name: str, row_count: int, col_count: int
    ) -> None:
        self.data_sizes[tool_name] = {
            "rows": row_count,
            "columns": col_count,
        }

    def total_rows(self) -> int:
        return sum(info.get("rows", 0) for info in self.data_sizes.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm_call_count": self.llm_call_count,
            "tool_call_count": self.tool_call_count,
            "tool_call_details": self.tool_call_details,
            "data_sizes": self.data_sizes,
            "total_rows": self.total_rows(),
        }


def _get_langfuse_client():
    """获取 Langfuse 客户端（懒初始化）"""
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return client
    except ImportError as e:
        print(f"[Langfuse] ImportError: {e}")
        return None
    except Exception as e:
        print(f"[Langfuse] Client init error: {e}")
        return None


class LangfuseObserver:
    """
    Langfuse 观测器（v4.x API）。

    在 Agent 执行过程中手动埋点，替代 LangChain 的 CallbackHandler。

    v4.x 架构：trace 由 root span 承载，子 span 挂在 root span 下。
    session_id/user_id/tags 通过 root span 的 update(**kwargs) 传入。

    Tool span 采用延迟关闭策略：
    - tool_start 时创建 span，暂不 end
    - tool_end 时补充 output + end（fallback 模式）
    - flush 时兜底 end 所有未关闭的 span（SDK MCP 模式）
    """

    def __init__(self, session_id: str, user_input: str = "", user_id: str = ""):
        self.session_id = session_id
        self.user_input = user_input
        self.user_id = user_id
        self.metrics = TraceMetrics()
        self._client = _get_langfuse_client()
        self._trace_id: str | None = None
        self._root_span: Any = None
        # 未关闭的 tool span：tool_name → span 对象列表
        self._pending_tool_spans: dict[str, list[Any]] = {}

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def start_trace(self, name: str = "SDK-DBAgent-Chat") -> None:
        """
        开始一个 trace（创建 root span）。

        v4.x: 用 client.start_observation(as_type="span") 创建 root span，
        并通过 update(**kwargs) 传入 session_id/user_id/tags。
        """
        if not self._client:
            return
        try:
            self._trace_id = self._client.create_trace_id()
            self._root_span = self._client.start_observation(
                trace_context={"trace_id": self._trace_id},
                name=name,
                as_type="span",
                input=self.user_input[:500] if self.user_input else None,
                metadata={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                },
            )
            # session_id/user_id/tags 在 v4.x 通过 update kwargs 传入
            update_kwargs: dict[str, Any] = {
                "tags": ["sdk-dbagent", "nl2sql"],
            }
            if self.session_id:
                update_kwargs["session_id"] = self.session_id
            if self.user_id:
                update_kwargs["user_id"] = self.user_id
            self._root_span.update(**update_kwargs)
        except Exception:
            self._root_span = None
            self._trace_id = None

    def record_llm_call(
        self,
        name: str = "llm-reasoning",
        input_data: dict | None = None,
        output_data: dict | None = None,
    ) -> None:
        """
        记录 LLM 调用（generation span）。

        v4.x: 用 root_span.start_observation(as_type="generation") 创建子 span。
        """
        self.metrics.record_llm_call()
        if self._root_span:
            try:
                child = self._root_span.start_observation(
                    name=name,
                    as_type="generation",
                    input=input_data,
                    output=output_data,
                )
                child.end()
            except Exception:
                pass

    def record_tool_call(
        self,
        tool_name: str,
        input_data: dict | None = None,
    ) -> None:
        """
        记录工具调用开始（tool span）。

        创建 span 但不立即 end，等待 tool_end 补充 output。
        如果 tool_end 未触发（SDK MCP 模式），flush() 时会兜底 end。
        """
        self.metrics.record_tool_call(tool_name)
        if self._root_span:
            try:
                child = self._root_span.start_observation(
                    name=f"tool:{tool_name}",
                    as_type="tool",
                    input=input_data,
                )
                pending = self._pending_tool_spans.setdefault(tool_name, [])
                pending.append(child)
            except Exception:
                pass

    def update_tool_result(
        self,
        tool_name: str,
        output_data: str | None = None,
        row_count: int = 0,
        col_count: int = 0,
    ) -> None:
        """
        补充工具调用结果（在 tool_end 时调用）。

        找到第一个未关闭的同名 tool span，更新 output/metadata 并 end。
        仅 fallback 模式有效；SDK MCP 模式无 tool_end 事件，不会触发此方法。
        """
        if row_count > 0 or col_count > 0:
            self.metrics.record_data_size(tool_name, row_count, col_count)

        pending = self._pending_tool_spans.get(tool_name, [])
        while pending:
            span = pending.pop(0)
            try:
                span.update(
                    output=output_data[:2000] if output_data else None,
                    metadata={
                        "rows": row_count,
                        "columns": col_count,
                    },
                )
                span.end()
                return
            except Exception:
                pass

    def flush(self, response: str = "") -> None:
        """
        写入最终指标并发送数据。

        1. 兜底 end 所有未关闭的 tool span（SDK MCP 模式）
        2. 更新 root span 的 output/metadata，打分，end
        3. flush client
        """
        # 兜底：end 所有未关闭的 tool span
        for tool_name, spans in self._pending_tool_spans.items():
            for span in spans:
                try:
                    span.end()
                except Exception:
                    pass
        self._pending_tool_spans.clear()

        if self._root_span:
            try:
                existing_meta = (
                    self._root_span.metadata
                    if hasattr(self._root_span, "metadata") and self._root_span.metadata
                    else {}
                )
                self._root_span.update(
                    output=response[:1000] if response else None,
                    metadata={
                        **existing_meta,
                        "metrics": self.metrics.to_dict(),
                    },
                )
                self._root_span.score(
                    name="tool_calls",
                    value=float(self.metrics.tool_call_count),
                )
                self._root_span.end()
            except Exception:
                pass

        if self._client:
            try:
                self._client.flush()
                if self._trace_id:
                    trace_url = self._client.get_trace_url(trace_id=self._trace_id)
                    if trace_url:
                        print(f"[Langfuse] Trace URL: {trace_url}")
            except Exception:
                pass

    def record_score(self, name: str, value: float, comment: str = "") -> None:
        """记录自定义评分"""
        if self._root_span:
            try:
                self._root_span.score(name=name, value=value, comment=comment)
            except Exception:
                pass


def extract_result_size(output: str) -> tuple[int, int]:
    """
    从 Markdown 表格输出中提取行数和列数。

    解析格式：
    | col1 | col2 | ... |
    | val1 | val2 | ... |
    共 N 行
    """
    import re

    lines = output.split("\n")
    row_count = 0
    col_count = 0

    # 提取列数：从表头行
    for line in lines:
        if line.startswith("|") and "---" not in line:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if cols:
                col_count = max(col_count, len(cols))
                break

    # 提取行数：从 "共 N 行" 文本
    match = re.search(r"共\s*(\d+)\s*行", output)
    if match:
        row_count = int(match.group(1))

    return row_count, col_count