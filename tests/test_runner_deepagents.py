"""验证 run_agent_stream 产出事件结构与旧版一致（不依赖真实 LLM，用 monkeypatch）。"""
import asyncio
import pytest

from app.agent import runner
from app.agent.prompts import AGENT_SYSTEM_PROMPT


class _FakeAgent:
    """模拟 create_deep_agent 产物，固定产出两轮工具调用 + 最终回答。"""

    def __init__(self):
        self.turns = iter([
            {
                "messages": [{"content": "先查一下表", "tool_calls": [
                    {"name": "find_table", "input": {"keyword": "order"}}
                ]}],
            },
            {
                "messages": [{"content": "好的，最终回答", "tool_calls": []}],
            },
        ])

    def astream(self, input, config=None):
        """同步版本用 async 生成器模拟。"""

        async def _gen():
            for turn in self.turns:
                yield turn
        return _gen()

    def invoke(self, input, config=None):
        return {"messages": [{"content": "mock"}]}


def test_run_agent_stream_produces_expected_events(monkeypatch):
    monkeypatch.setattr(runner, "_build_engine", lambda: _FakeAgent())
    # 覆盖 _get_llm_client 供 token 统计使用
    monkeypatch.setattr(runner, "_get_llm_client", lambda: object())

    events = []
    session_state = {
        "session_id": "s1", "user_id": "u1",
        "chat_history": [], "summary": "",
    }

    async def _run():
        async for etype, data in runner.run_agent_stream("查订单", session_state):
            events.append((etype, data))

    asyncio.run(_run())

    etypes = [e[0] for e in events]
    assert "step" in etypes  # thinking
    assert "final" in etypes
    final = [e for e in events if e[0] == "final"][0]
    assert "response" in final[1]
    assert "updated_state" in final[1]

    # Token 统计可观测性（Phase 1 final review fix 4）：
    # FakeAgent 不会触发真实 LLM 回调，因此 token_callback 始终为 0。
    # TODO: 当 token 跟踪通过真实 LLM 回调恢复后将 >= 0 改为 > 0。
    stats = final[1].get("stats", {})
    assert "tokens" in stats, "final stats must include 'tokens' field"
    assert "input_tokens" in stats, "final stats must include 'input_tokens' field"
    assert "output_tokens" in stats, "final stats must include 'output_tokens' field"
    assert stats["tokens"] >= 0, f"tokens should be >= 0, got {stats['tokens']}"
    assert stats["input_tokens"] >= 0, f"input_tokens should be >= 0, got {stats['input_tokens']}"
    assert stats["output_tokens"] >= 0, f"output_tokens should be >= 0, got {stats['output_tokens']}"
    assert stats["tokens"] == stats["input_tokens"] + stats["output_tokens"], (
        f"tokens ({stats['tokens']}) must equal input ({stats['input_tokens']}) + output ({stats['output_tokens']})"
    )


# ========== 真实引擎测试 ==========

class _FakeAgentConcurrentSameTool:
    """模拟同一 LLM 回合内两次调用同一工具（如 find_table("orders") + find_table("users")）。"""

    def __init__(self):
        self.turns = iter([
            {
                "messages": [{"content": "查两个表", "tool_calls": [
                    {"name": "find_table", "input": {"keyword": "orders"}, "id": "call_orders"},
                    {"name": "find_table", "input": {"keyword": "users"}, "id": "call_users"},
                ]}],
            },
            {
                "messages": [{"role": "tool", "name": "find_table", "tool_call_id": "call_orders", "content": "orders 表结果"}],
            },
            {
                "messages": [{"role": "tool", "name": "find_table", "tool_call_id": "call_users", "content": "users 表结果"}],
            },
            {
                "messages": [{"content": "两个表都查了，回答", "tool_calls": []}],
            },
        ])

    def astream(self, input, config=None):
        async def _gen():
            for turn in self.turns:
                yield turn
        return _gen()

    def invoke(self, input, config=None):
        return {"messages": [{"content": "mock"}]}


class _FakeAgentOrphanToolMessage:
    """模拟 deepagents 引擎内部产生 ToolMessage 但无前置 tool_start 的情况。"""

    def __init__(self):
        self.turns = iter([
            {
                "messages": [{"role": "tool", "name": "internal_query", "tool_call_id": "call_orphan", "content": "内部查询结果"}],
            },
            {
                "messages": [{"content": "处理完成", "tool_calls": []}],
            },
        ])

    def astream(self, input, config=None):
        async def _gen():
            for turn in self.turns:
                yield turn
        return _gen()

    def invoke(self, input, config=None):
        return {"messages": [{"content": "mock"}]}


def test_concurrent_same_tool_yields_both_tool_ends(monkeypatch):
    """同一回合两次调用同一工具时，tool_end 应通过 tool_call_id 正确匹配。"""
    monkeypatch.setattr(runner, "_build_engine", lambda: _FakeAgentConcurrentSameTool())
    monkeypatch.setattr(runner, "_get_llm_client", lambda: object())

    events = []
    session_state = {
        "session_id": "s1", "user_id": "u1",
        "chat_history": [], "summary": "",
    }

    async def _run():
        async for etype, data in runner.run_agent_stream("查订单", session_state):
            events.append((etype, data))

    asyncio.run(_run())

    tool_ends = [(e[1]) for e in events if e[0] == "step" and "completed" in str(e[1].get("status", ""))]
    assert len(tool_ends) >= 2, (
        f"Expected at least 2 tool_end events for concurrent same-tool calls, got {len(tool_ends)}"
    )


def test_orphan_tool_message_still_yields_tool_end(monkeypatch):
    """无匹配 pending 的 ToolMessage 仍应产出 tool_end（不静默丢弃）。"""
    monkeypatch.setattr(runner, "_build_engine", lambda: _FakeAgentOrphanToolMessage())
    monkeypatch.setattr(runner, "_get_llm_client", lambda: object())

    events = []
    session_state = {
        "session_id": "s1", "user_id": "u1",
        "chat_history": [], "summary": "",
    }

    async def _run():
        async for etype, data in runner.run_agent_stream("查订单", session_state):
            events.append((etype, data))

    asyncio.run(_run())

    tool_ends = [(e[0], e[1]) for e in events if e[0] == "step" and "completed" in str(e[1].get("status", ""))]
    assert len(tool_ends) >= 1, (
        f"Orphan ToolMessage should still yield tool_end, got {len(tool_ends)} tool_end events"
    )
    # 确认孤儿 tool_end 不含 nl2sql_timings
    orphan_tool_end = tool_ends[0][1]
    assert orphan_tool_end.get("nl2sql_timings") is None, (
        "Orphan tool_end should not have nl2sql_timings"
    )


import os as _os

_real_engine_available = bool(_os.environ.get("LLM_API_KEY"))


@pytest.mark.skipif(
    not _real_engine_available,
    reason="LLM_API_KEY 未设置，跳过真实 LLM 调用测试",
)
@pytest.mark.asyncio
async def test_real_engine_streams():
    """真实 engine：用最小输入验证 astream 可被迭代并产出事件。

    需要 LLM_API_KEY 环境变量。无凭据时自动跳过。
    """
    from app.agent import runner

    events = []
    session_state = {
        "session_id": "s2", "user_id": "u2",
        "chat_history": [], "summary": "",
    }

    async for etype, data in runner.run_agent_stream("你好", session_state):
        events.append((etype, data))

    etypes = [e[0] for e in events]
    assert "final" in etypes


class _CancellingFakeAgent:
    """模拟 cancel_event 预置时引擎立即产出 cancelled final。"""

    def astream(self, input, config=None):
        async def _gen():
            # 模拟：LLM 调用前已被取消 → 产出 subtype=cancelled
            yield {"messages": [{"content": "", "tool_calls": []}]}
        return _gen()

    def invoke(self, input, config=None):
        return {"messages": [{"content": ""}]}


def test_run_agent_stream_forwards_cancel_subtype(monkeypatch):
    """端到端 cancel 语义：run_agent_stream 最终 final 必须带 subtype='cancelled'。

    回归测试：_run_agent_deepagents 正确产出 subtype='cancelled' 内部事件，
    但 run_agent_stream 曾丢弃 subtype，导致 routes.py 的
    data.get("subtype") == "cancelled" 恒为 False，端到端 cancelled 标记丢失。
    """
    monkeypatch.setattr(runner, "_build_engine", lambda: _CancellingFakeAgent())
    monkeypatch.setattr(runner, "_get_llm_client", lambda: object())

    events = []
    session_state = {
        "session_id": "s3", "user_id": "u3",
        "chat_history": [], "summary": "",
    }
    cancel_event = asyncio.Event()
    cancel_event.set()  # 预置取消：引擎应在首个迭代边界立即取消

    async def _run():
        async for etype, data in runner.run_agent_stream(
            "查订单", session_state, cancel_event=cancel_event,
        ):
            events.append((etype, data))

    asyncio.run(_run())

    finals = [e for e in events if e[0] == "final"]
    assert finals, "must emit a final event"
    final_data = finals[-1][1]
    assert final_data.get("subtype") == "cancelled", (
        f"final must carry subtype='cancelled' for end-to-end cancel, "
        f"got {final_data.get('subtype')!r}"
    )
