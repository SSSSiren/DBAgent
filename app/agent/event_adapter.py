"""deepagents 流事件 → 现有 run_agent_stream 内部事件 的适配层。

阶段 1 仅映射语义事件（text/tool_start/tool_end），llm_call/final 由 Task 5 在引擎层重建。
"""

from __future__ import annotations

from typing import Any


def translate_event(raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """将 deepagents 流的单个语义事件翻译为内部事件元组列表。

    Args:
        raw: 语义事件字典，含 kind 字段：
            - {"kind": "text_delta", "text": ...}
            - {"kind": "tool_call", "name": ..., "input": ...}
            - {"kind": "tool_result", "name": ..., "content": ..., "elapsed_ms": ...}

    Returns:
        内部事件元组列表 [(event_type, data), ...]。
    """
    kind = raw.get("kind", "")
    if kind == "text_delta":
        return [("text", {"text": raw.get("text", "")})]
    if kind == "tool_call":
        return [("tool_start", {"name": raw.get("name", ""), "input": raw.get("input", {})})]
    if kind == "tool_result":
        return [("tool_end", {
            "name": raw.get("name", ""),
            "content": raw.get("content", ""),
            "elapsed_ms": raw.get("elapsed_ms", 0),
        })]
    return []
