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


# ========== 真实引擎测试 ==========

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
