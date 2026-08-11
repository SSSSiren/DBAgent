"""deepagents 流事件 → 现有 run_agent_stream 内部事件 的适配层。

阶段 1 将 deepagents astream 产出的 LangChain 消息对象（AIMessage/ToolMessage/dict）
翻译为内部事件（text/tool_start/tool_end）。llm_call/final 由 runner._run_agent_deepagents
在引擎层重建。
"""

from __future__ import annotations

from typing import Any


def _normalize_message(msg: Any) -> dict[str, Any]:
    """将消息规范化为统一 dict 格式。

    兼容：
    - 普通 dict（FakeAgent 测试用）：{"content": ..., "tool_calls": [{"name": ..., "input": ...}]}
    - LangChain AIMessage 对象：msg.content, msg.tool_calls
    - LangChain ToolMessage 对象：msg.type="tool", msg.content, msg.name, msg.tool_call_id

    返回 dict 含 role/name/content/tool_calls/tool_call_id 字段。
    tool_calls[*].arguments 保持为 dict（llm_call 产出时再序列化为 JSON 字符串）。
    """
    if isinstance(msg, dict):
        content = msg.get("content", "") or ""
        raw_tool_calls = msg.get("tool_calls", []) or []
        role = msg.get("role", msg.get("type", ""))
        name = msg.get("name", "")
        tool_call_id = msg.get("tool_call_id", "")
        # 带 tool_call_id 的 dict 是工具结果
        if tool_call_id:
            role = "tool"
        normalized_tc = []
        for tc in raw_tool_calls:
            tc_name = tc.get("name", "")
            tc_id = tc.get("id", "")
            # 兼容 "input"（FakeAgent）、"args"（LangChain）、"arguments"（OpenAI 格式）
            args = tc.get("input", tc.get("args", tc.get("arguments", {})))
            normalized_tc.append({"name": tc_name, "arguments": args, "id": tc_id})
        return {
            "role": role,
            "name": name,
            "content": content,
            "tool_calls": normalized_tc,
            "tool_call_id": tool_call_id,
        }
    else:
        # LangChain 消息对象
        content = getattr(msg, "content", "") or ""
        raw_tool_calls = getattr(msg, "tool_calls", []) or []
        role = getattr(msg, "type", "")
        name = getattr(msg, "name", "")
        tool_call_id = getattr(msg, "tool_call_id", "")
        normalized_tc = []
        for tc in raw_tool_calls:
            if isinstance(tc, dict):
                tc_name = tc.get("name", "")
                tc_id = tc.get("id", "")
                # 兼容 "input"/"args"/"arguments"
                args = tc.get("input", tc.get("args", tc.get("arguments", {})))
            else:
                tc_name = getattr(tc, "name", "")
                tc_id = getattr(tc, "id", "")
                args = getattr(tc, "args", {})
            normalized_tc.append({"name": tc_name, "arguments": args, "id": tc_id})
        return {
            "role": role,
            "name": name,
            "content": content,
            "tool_calls": normalized_tc,
            "tool_call_id": tool_call_id,
        }


def translate_event(msg: Any) -> list[tuple[str, dict[str, Any]]]:
    """将 deepagents astream 产出的单个消息翻译为内部事件元组列表。

    接受 LangChain 消息对象（AIMessage / ToolMessage）或等价的 dict，
    输出内部事件（text / tool_start / tool_end）。

    Args:
        msg: 单个消息，可以是：
            - AIMessage 对象：type="ai"，含 content 和可选的 tool_calls
            - ToolMessage 对象：type="tool"，含 name、content、tool_call_id
            - dict：等价于上述对象，字段名兼容 role/type、input/args/arguments

    Returns:
        内部事件元组列表 [(event_type, data), ...]：
            - ("text", {"text": str}) — AI 文本内容
            - ("tool_start", {"name": str, "input": dict}) — 工具调用开始
            - ("tool_end", {"name": str, "content": str, "elapsed_ms": float}) — 工具结果

        对于不含文本内容且无 tool_calls 的 AI 消息，返回空列表。
        无法识别的消息类型返回空列表。

    注意：
        tool_end 的 elapsed_ms 目前固定为 0，因为 deepagents 引擎内部执行工具时
        ToolMessage 不携带耗时信息。若后续需要准确耗时，需在工具 handler 层面埋点。
    """
    normalized = _normalize_message(msg)
    role = normalized.get("role", "")
    content = normalized.get("content", "")
    name = normalized.get("name", "")
    tool_calls = normalized.get("tool_calls", [])
    tool_call_id = normalized.get("tool_call_id", "")

    events: list[tuple[str, dict[str, Any]]] = []

    if role == "tool":
        # ToolMessage → tool_end
        events.append(("tool_end", {
            "name": name,
            "content": content,
            "elapsed_ms": 0,
        }))
    elif role == "ai" or tool_calls:
        # AIMessage → text（如有内容）+ tool_start（每个 tool_call）
        if content:
            events.append(("text", {"text": content}))
        for tc in tool_calls:
            events.append(("tool_start", {
                "name": tc["name"],
                "input": tc["arguments"],
                "tool_call_id": tc.get("id", ""),
            }))

    return events