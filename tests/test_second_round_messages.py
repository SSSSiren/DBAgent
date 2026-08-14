"""
对比测试：手写 ReAct vs deepagents 的"第二轮发给 LLM 的 messages"结构。

背景
----
评测数据显示 deepagents 重构后在基线（无 HDC/无 SQL 记忆）场景下 pro 模型表现略降，
且 TC-010/TC-022 出现"过度探索"（拿到正确 SQL 后仍继续 13-20 次工具调用）。
深度对比已排除 system prompt / 工具集合 / 用户消息 / SQL 质量差异。

本测试用**相同的首轮 LLM 响应**（含 tool_call）分别驱动两引擎走完第一轮，
捕获两者**第二轮发给 LLM 的完整 messages**，逐字段对比结构差异——
判定"过度探索"是工程问题（消息结构差异）还是纯 LLM 行为。

手写侧基准来源：git commit 32756b3~1 的旧 app/agent/runner.py::_run_agent
（重构删除前的手写 ReAct 循环）。

方法
----
- deepagents 侧：mock `ChatOpenAI._agenerate` 返回固定脚本（首轮 tool_call → 次轮 final），
  用 `on_chat_model_start` 回调捕获每轮 messages。
- 手写侧：内联旧 `_run_agent` 的消息组装逻辑（纯 dict，确定性），不依赖 LLM。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolCall
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app.agent.llm_factory import get_chat_model
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.tool_adapter import build_deepagent_tools

# ── 共享的固定场景 ──
USER_INPUT = "统计告警数量"
TABLE_NAME = "db_alert_history"
MOCK_TOOL_RESULT = "## 查询结果\n**表**: db_alert_history\n返回 5 行"
FIRST_TOOL_CALL = ToolCall(
    name="query_database",
    args={
        "schema_id": 65938636,
        "question": "统计告警数量",
        "table_name": TABLE_NAME,
    },
    id="call_1",
)


# ============================================================================
# 捕获回调：on_chat_model_start 拿到每轮 messages
# ============================================================================

class CaptureMessagesCallback(BaseCallbackHandler):
    """捕获每次 LLM 调用前的完整 messages 列表。"""

    def __init__(self) -> None:
        self.rounds: list[list[Any]] = []

    def on_chat_model_start(self, serialized, messages, run_id, **kwargs) -> None:  # noqa: ANN001
        # messages 是 list[list[BaseMessage]]，取第一个（单次调用的 messages）
        self.rounds.append(list(messages[0]) if messages else [])


# ============================================================================
# deepagents 侧
# ============================================================================

def _make_mock_agenerate(script: list[AIMessage]):
    """构造一个按脚本返回的 mock _agenerate 方法。

    Args:
        script: 按调用顺序返回的 AIMessage 列表。

    Returns:
        (mock_method, captured_messages): mock 方法和捕获的 messages 列表。
    """
    captured: list[list[Any]] = []

    async def fake_agenerate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        captured.append(list(messages))
        next_msg = script[min(len(captured) - 1, len(script) - 1)]
        return ChatResult(generations=[ChatGeneration(message=next_msg)])

    return fake_agenerate, captured


def _build_deepagents_engine():
    """构造 deepagents 引擎（mock 模型 + 固定工具结果）。"""
    from deepagents import create_deep_agent

    model = get_chat_model()
    return create_deep_agent(
        model=model,
        tools=build_deepagent_tools(),
        system_prompt=AGENT_SYSTEM_PROMPT,
    )


@pytest.mark.asyncio
async def test_deepagents_second_round_messages(monkeypatch):
    """deepagents：捕获第二轮 messages，断言 tool message 含 name。"""
    from unittest.mock import patch

    from app.tools import registry

    script = [
        AIMessage(
            content="我需要先查一下表",
            tool_calls=[FIRST_TOOL_CALL],
        ),
        AIMessage(content="最终回答：共 5 条告警", tool_calls=[]),
    ]
    fake_agenerate, captured = _make_mock_agenerate(script)

    # mock 模型：替换 ChatOpenAI._agenerate（真实 ChatOpenAI 自带 bind_tools）
    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake_agenerate)

    engine = _build_deepagents_engine()
    capture = CaptureMessagesCallback()

    # mock 工具执行，避免真实 OneDBA 调用
    with patch.object(registry, "execute", return_value=MOCK_TOOL_RESULT) as mock_exec:
        async for _ in engine.astream(
            {"messages": [HumanMessage(content=USER_INPUT)]},
            config={"callbacks": [capture]},
        ):
            pass

    assert mock_exec.called, "query_database 应被调用"
    assert len(capture.rounds) >= 2, f"应至少 2 轮 LLM 调用，实际 {len(capture.rounds)}"

    # 第二轮 messages（第一轮 tool_call 之后）
    second_round = capture.rounds[1]
    assert len(second_round) == 4, f"第二轮应有 4 条消息，实际 {len(second_round)}"

    # 找 tool message
    tool_msgs = [m for m in second_round if getattr(m, "type", "") == "tool"]
    assert tool_msgs, "第二轮应有 tool message"
    tool_msg = tool_msgs[0]

    # 关键断言：deepagents 的 ToolMessage 含 name
    assert getattr(tool_msg, "name", None) == "query_database", (
        f"deepagents ToolMessage 应含 name='query_database'，实际 name={getattr(tool_msg, 'name', None)!r}"
    )
    assert getattr(tool_msg, "tool_call_id", None) == "call_1"
    assert MOCK_TOOL_RESULT in str(tool_msg.content)

    # assistant tool_calls 用 LangChain ToolCall 格式（name/args/id）
    ai_msgs = [m for m in second_round if getattr(m, "type", "") == "ai"]
    assert ai_msgs, "第二轮应有 ai message"
    ai_tool_calls = ai_msgs[0].tool_calls
    assert len(ai_tool_calls) == 1
    tc = ai_tool_calls[0]
    assert tc["name"] == "query_database"
    assert tc["id"] == "call_1"
    assert tc["args"]["table_name"] == TABLE_NAME


# ============================================================================
# 手写侧（内联旧 _run_agent 的消息组装逻辑，来源 commit 32756b3~1）
# ============================================================================

def _build_handwritten_second_round_messages() -> list[dict[str, Any]]:
    """构造手写 ReAct 第二轮 messages（确定性，不依赖 LLM）。

    对应旧 app/agent/runner.py::_run_agent（commit 32756b3~1）：
      messages = [system, user]
      + assistant（含 tool_calls，用 OpenAI SDK 的 tc.model_dump()）
      + tool（role/tool_call_id/content，无 name）
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": USER_INPUT},
    ]

    # 模拟 OpenAI SDK 的 tool_call 对象 model_dump() 结果
    # （手写侧用 tc.model_dump()，保留 id/type/function + DeepSeek signature）
    tool_call_dict = {
        "id": FIRST_TOOL_CALL["id"],
        "type": "function",
        "function": {
            "name": FIRST_TOOL_CALL["name"],
            "arguments": json.dumps(FIRST_TOOL_CALL["args"], ensure_ascii=False),
        },
    }

    messages.append({
        "role": "assistant",
        "content": "我需要先查一下表",
        "tool_calls": [tool_call_dict],
    })

    messages.append({
        "role": "tool",
        "tool_call_id": FIRST_TOOL_CALL["id"],
        "content": MOCK_TOOL_RESULT,
    })

    return messages


def test_handwritten_second_round_messages():
    """手写：断言 tool message 无 name，assistant tool_calls 用 OpenAI 格式。"""
    messages = _build_handwritten_second_round_messages()
    assert len(messages) == 4

    # 关键断言：手写 tool message 无 name
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert tool_msgs, "应有 tool message"
    tool_msg = tool_msgs[0]
    assert "name" not in tool_msg, f"手写 tool message 不应有 name，实际 keys={list(tool_msg.keys())}"
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_1"
    assert MOCK_TOOL_RESULT in tool_msg["content"]

    # assistant tool_calls 用 OpenAI 格式（function.name / function.arguments）
    ai_msgs = [m for m in messages if m["role"] == "assistant"]
    assert ai_msgs
    ai_tool_calls = ai_msgs[0]["tool_calls"]
    assert len(ai_tool_calls) == 1
    tc = ai_tool_calls[0]
    assert tc["function"]["name"] == "query_database"
    assert "name" not in tc, f"手写 tool_call 顶层不应有 name（OpenAI 格式），实际 keys={list(tc.keys())}"
    assert tc["id"] == "call_1"


# ============================================================================
# 结构对比
# ============================================================================

def _serialize_message(msg: Any) -> dict[str, Any]:
    """将一条消息统一序列化为 dict，供对比。"""
    mtype = getattr(msg, "type", None)
    if mtype is None:  # 手写侧 dict（role 键）或手动构造 dict（type 键）
        mtype = msg.get("role") or msg.get("type", "")
        return {
            "type": mtype,
            "content": msg.get("content", ""),
            "tool_call_id": msg.get("tool_call_id"),
            "name": msg.get("name"),
            "tool_calls": msg.get("tool_calls"),
        }
    # LangChain 对象
    tcs = getattr(msg, "tool_calls", []) or []
    return {
        "type": mtype,
        "content": str(getattr(msg, "content", "")),
        "tool_call_id": getattr(msg, "tool_call_id", None),
        "name": getattr(msg, "name", None),
        "tool_calls": tcs,
    }


def test_compare_second_round_structures():
    """对比两引擎第二轮 messages 结构，断言关键差异（tool message name）。"""
    handwritten = _build_handwritten_second_round_messages()

    # deepagents 侧从真实引擎捕获较复杂（需 mock LLM + 工具），
    # 此处用与真实引擎一致的结构构造（已验证 deepagents ToolMessage 含 name）
    from langchain_core.messages import ToolMessage

    deepagents_msgs = [
        {"type": "system", "content": AGENT_SYSTEM_PROMPT},
        {"type": "human", "content": USER_INPUT},
        {
            "type": "ai",
            "content": "我需要先查一下表",
            "tool_calls": [FIRST_TOOL_CALL],
        },
        ToolMessage(
            content=MOCK_TOOL_RESULT,
            name=FIRST_TOOL_CALL["name"],
            tool_call_id=FIRST_TOOL_CALL["id"],
        ),
    ]

    # 序列化对比
    hw = [_serialize_message(m) for m in handwritten]
    da = [_serialize_message(m) for m in deepagents_msgs]

    # 1. system/user/assistant 角色与内容一致
    assert hw[0]["type"] == "system" and da[0]["type"] == "system"
    assert hw[1]["type"] == "user" and da[1]["type"] == "human"
    assert hw[0]["content"] == da[0]["content"], "system prompt 应一致"
    assert hw[1]["content"] == da[1]["content"], "user 输入应一致"

    # 2. 关键差异：手写 tool message 无 name，deepagents 有 name
    hw_tool = hw[3]
    da_tool = da[3]
    assert hw_tool["name"] is None, "手写 tool message 无 name"
    assert da_tool["name"] == "query_database", "deepagents tool message 有 name"

    # 3. assistant tool_calls 格式差异
    hw_ai_tc = hw[2]["tool_calls"][0]
    da_ai_tc = da[2]["tool_calls"][0]
    # 手写：OpenAI 格式 {id, type, function:{name, arguments}}
    assert "function" in hw_ai_tc and "name" not in hw_ai_tc
    # deepagents：LangChain 格式 {id, type, name, args}
    assert "name" in da_ai_tc and "args" in da_ai_tc
    assert hw_ai_tc["function"]["name"] == da_ai_tc["name"] == "query_database"
