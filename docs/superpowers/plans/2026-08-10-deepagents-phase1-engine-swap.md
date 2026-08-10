# Deepagents 阶段 1：引擎替换实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把手写 ReAct Agent 引擎（`app/agent/runner.py`）替换为 deepagents（LangGraph `create_agent`），保持 SSE 事件流、HTTP API、前端、业务逻辑（上下文检索/记忆记录）完全兼容。

**Architecture:** 保留 `run_agent_stream` 为唯一对外接口（API 层零改动），其内部从手写 `_run_agent` 循环改为 `create_deep_agent(...)` + `stream_events` 事件适配。8 段上下文（`build_context`）阶段 1 保留原样注入。6 个现有工具适配为 deepagents tools。`_execute_agent_stream` 的检索/记忆业务逻辑完全不动。

**Tech Stack:** Python 3.12, deepagents, langchain-openai (ChatOpenAI), langgraph, langgraph-checkpoint-sqlite, openai, FastAPI, pytest。

**参考 spec:** `docs/superpowers/specs/2026-08-10-deepagents-refactor-design.md`（阶段 1 对应第 2、5、7 节）

## Global Constraints

- 保持 `run_agent_stream(user_input, session_state, trace_name, cancel_event)` 签名与产出事件类型（`step`/`sql`/`llm_call`/`final`）不变
- SSE 事件格式逐字段兼容：`step`（thinking / tool:xxx running·completed）、`sql`、`llm_call`、`final`
- `_execute_agent_stream`（app/api/routes.py）的业务逻辑（上下文检索/记忆记录）**零改动**
- `memory/`、`nl2sql/`、`datavault/`、`knowledge/`、`client/onedba.py` 模块零改动
- LLM 经 `ChatOpenAI` 接入 DeepSeek（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`，OpenAI 兼容代理）
- 现有测试 `tests/` 全量通过为阶段 1 验收红线
- 提交信息末尾附 `Co-Authored-By: Claude <noreply@anthropic.com>`

---

### Task 1: 引入 deepagents 依赖

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: 无
- Produces: 新依赖（deepagents、langchain-openai、langgraph、langgraph-checkpoint-sqlite），供 Task 2-6 使用

- [ ] **Step 1: 在 requirements.txt 追加依赖**

```txt
# deepagents 引擎（阶段 1 引入）
deepagents>=0.6.8
langchain-openai>=0.2.0
langgraph>=0.2.60
langgraph-checkpoint-sqlite>=2.0.0
```

- [ ] **Step 2: 安装依赖验证**

Run: `pip install -r requirements.txt`
Expected: 成功安装无报错

- [ ] **Step 3: 验证可导入**

Run: `python -c "from deepagents import create_deep_agent; from langchain_openai import ChatOpenAI; import langgraph; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 4: 提交**

```bash
git add requirements.txt
git commit -m "chore(deps): add deepagents + langchain/langgraph for phase-1 engine swap"
```

---

### Task 2: ChatOpenAI 客户端工厂

**Files:**
- Create: `app/agent/llm_factory.py`
- Test: `tests/test_llm_factory.py`

**Interfaces:**
- Consumes: `app.config.get_settings()`（`llm_api_key` / `llm_base_url` / `llm_model`）
- Produces: `get_chat_model() -> langchain_openai.ChatOpenAI`（供 Task 4 的 `create_deep_agent` 使用）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_llm_factory.py
import pytest
from app.agent.llm_factory import get_chat_model


def test_get_chat_model_returns_chatopenai(monkeypatch):
    from langchain_openai import ChatOpenAI
    monkeypatch.setenv("LLM_BASE_URL", "http://fake:8000/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash-260425")
    # 重置单例
    from app.agent import llm_factory
    llm_factory._chat_model = None
    model = get_chat_model()
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-v4-flash-260425"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_llm_factory.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError`（`llm_factory` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# app/agent/llm_factory.py
"""ChatOpenAI 客户端工厂 — 将 DeepSeek(OpenAI 兼容代理) 接入 LangChain ChatOpenAI。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import get_settings

_chat_model: ChatOpenAI | None = None


def get_chat_model() -> ChatOpenAI:
    """获取 ChatOpenAI 客户端（模块级懒加载单例，复用连接池）。"""
    global _chat_model
    if _chat_model is None:
        settings = get_settings()
        _chat_model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.1,
        )
    return _chat_model
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_llm_factory.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agent/llm_factory.py tests/test_llm_factory.py
git commit -m "feat(agent): add ChatOpenAI factory for deepseek via langchain"
```

---

### Task 3: 现有工具适配为 deepagents tools

**Files:**
- Create: `app/agent/tool_adapter.py`
- Test: `tests/test_tool_adapter.py`

**Interfaces:**
- Consumes: `app.tools.registry`（现有 6 工具：`list_databases`/`select_database`/`find_table`/`describe_table`/`query_database`/`execute_sql`，各含 `handler` + `parameters` schema）
- Produces: `build_deepagent_tools() -> list`（langchain StructuredTool 列表，供 Task 4 的 `create_deep_agent` 使用）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tool_adapter.py
import pytest
from langchain_core.tools import BaseTool
from app.agent.tool_adapter import build_deepagent_tools
from app.tools import registry


def test_builds_all_six_tools():
    tools = build_deepagent_tools()
    assert len(tools) == len(registry.tool_names) >= 6
    for t in tools:
        assert isinstance(t, BaseTool)
        assert t.name in registry.tool_names
        assert t.description


@pytest.mark.asyncio
async def test_tool_invokes_registry_handler():
    tools = build_deepagent_tools()
    by_name = {t.name: t for t in tools}
    # list_databases 有默认参数，直接调用应返回字符串
    tool = by_name["list_databases"]
    result = await tool.ainvoke({"keyword": ""})
    assert isinstance(result, str)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_tool_adapter.py -v`
Expected: FAIL（`tool_adapter` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# app/agent/tool_adapter.py
"""将现有 ToolRegistry 的 6 个工具适配为 langchain StructuredTool。

关键点：
- 复用现有 registry.execute()，保留中间件（timeout/error_normalize）与幻觉参数过滤
- 工具 schema 从 registry 的 OpenAI parameters 转换
- async handler 包装为 langchain 可调用的工具
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.tools import registry


def build_deepagent_tools() -> list[StructuredTool]:
    """从现有 registry 构建 langchain StructuredTool 列表。"""
    tools: list[StructuredTool] = []
    for tool_def in registry:
        tool = StructuredTool.from_function(
            coroutine=_make_async_handler(tool_def.name),
            name=tool_def.name,
            description=tool_def.description,
            args_schema=_make_args_schema(tool_def.parameters),
        )
        tools.append(tool)
    return tools


def _make_async_handler(name: str):
    """包装 registry.execute 为可被 langchain 调用的 async 函数。"""
    async def _handler(**kwargs) -> str:
        return await registry.execute(name, **kwargs)
    _handler.__name__ = name
    return _handler


def _make_args_schema(parameters: dict):
    """将 OpenAI parameters 字典转换为 pydantic schema 类。"""
    from langchain_core.pydantic_v1 import create_model, Field
    props = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    fields = {}
    for pname, pdef in props.items():
        ptype = pdef.get("type", "string")
        if ptype == "integer":
            pytype = int
        elif ptype == "number":
            pytype = float
        elif ptype == "boolean":
            pytype = bool
        else:
            pytype = str
        fields[pname] = (pytype, Field(description=pdef.get("description", "")))
    return create_model(f"{name}Args", **fields)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_tool_adapter.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agent/tool_adapter.py tests/test_tool_adapter.py
git commit -m "feat(agent): adapt existing ToolRegistry tools to langchain StructuredTool"
```

---

### Task 4: 事件适配层（deepagents stream → 现有 SSE 事件）

**Files:**
- Create: `app/agent/event_adapter.py`
- Test: `tests/test_event_adapter.py`

**Interfaces:**
- Consumes: deepagents `agent.stream_events(input, version="v3")` 或 `agent.astream_events(...)` 的原始事件；现有 `run_agent_stream` 产出的事件类型
- Produces: `translate_event(raw_event: dict) -> list[tuple[str, dict]]`（内部事件元组列表：`text`/`tool_start`/`tool_end`/`llm_call`/`final`），供 Task 5 的 `_run_agent` 替代逻辑使用

**说明：** 阶段 1 先实现**事件类型映射函数**，其输入为 deepagents 流中识别出的"语义事件"（用简单结构化 dict 模拟，不依赖 langgraph 原始事件模型）。真正接线（Task 5）时再对接 stream。这样 Task 4 可独立单测。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_event_adapter.py
from app.agent.event_adapter import translate_event


def test_translate_thinking_text():
    # 模拟 deepagents messages 流中的文本增量
    raw = {"kind": "text_delta", "text": "我需要先查表"}
    events = translate_event(raw)
    assert events == [("text", {"text": "我需要先查表"})]


def test_translate_tool_start():
    raw = {"kind": "tool_call", "name": "find_table", "input": {"keyword": "order"}}
    events = translate_event(raw)
    assert events == [("tool_start", {"name": "find_table", "input": {"keyword": "order"}})]


def test_translate_tool_end():
    raw = {"kind": "tool_result", "name": "find_table", "content": "找到 3 张表", "elapsed_ms": 12.5}
    events = translate_event(raw)
    assert events == [("tool_end", {"name": "find_table", "content": "找到 3 张表", "elapsed_ms": 12.5})]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_event_adapter.py -v`
Expected: FAIL（`event_adapter` 不存在）

- [ ] **Step 3: 写最小实现**

```python
# app/agent/event_adapter.py
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_event_adapter.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agent/event_adapter.py tests/test_event_adapter.py
git commit -m "feat(agent): add event adapter for deepagents stream to internal events"
```

---

### Task 5: 替换 runner.py 手写 ReAct 为 deepagents 引擎

**Files:**
- Modify: `app/agent/runner.py`（`_run_agent` → `create_deep_agent` 引擎；`_get_llm_client` 保留供 embed 使用）
- Test: `tests/test_runner_deepagents.py`

**Interfaces:**
- Consumes: `app.agent.llm_factory.get_chat_model()`、`app.agent.tool_adapter.build_deepagent_tools()`、`app.agent.event_adapter.translate_event()`、`app.agent.prompts.AGENT_SYSTEM_PROMPT`、`app.agent.context.build_context`
- Produces: `run_agent_stream(user_input, session_state, trace_name, cancel_event)` 保持原签名与原产出事件（`step`/`sql`/`llm_call`/`final`）

**关键设计：**
- 阶段 1 保留 8 段上下文注入：`build_context(session_state)` 生成 context_str 作为 user prompt 前缀（与现状一致）
- `create_deep_agent(model=get_chat_model(), tools=build_deepagent_tools(), system_prompt=AGENT_SYSTEM_PROMPT)`
- 引擎执行用 `agent.astream(...)` 迭代工具调用 + 消息；将 deepagents 输出经 `translate_event` 翻译为内部事件；`llm_call`/`final` 在引擎层重建（保持现有评测框架依赖的格式）
- `cancel_event`：在流迭代边界检查，置位则终止并产出 `final(subtype="cancelled")`

- [ ] **Step 1: 写失败测试（验证 run_agent_stream 事件结构不回归）**

```python
# tests/test_runner_deepagents.py
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_runner_deepagents.py -v`
Expected: FAIL（`runner._build_engine` 不存在；现 runner 无该属性）

- [ ] **Step 3: 改造 runner.py**

在 `runner.py` 中：
1. 新增 `_build_engine()` 工厂，内部调用 `create_deep_agent`，将 `_run_agent` 手写循环替换为对 engine 的 astream 迭代
2. 保留 `_get_llm_client`（embed_text 依赖，见 `sql_memory.py:1833`）
3. 新增 `_run_agent_deepagents(...)` 异步生成器，产出与旧 `_run_agent` **相同的事件字典**（`llm_call`/`text`/`tool_start`/`tool_end`/`final`）
4. `run_agent_stream` 内调用改为 `_run_agent_deepagents`，其余（TTFB/统计/Langfuse/会话更新）不动

核心实现骨架：

```python
# 在 runner.py 内新增

def _build_engine():
    """构建 deepagents 引擎（模块级懒加载，测试可 monkeypatch）。"""
    from app.agent.llm_factory import get_chat_model
    from app.agent.tool_adapter import build_deepagent_tools
    from deepagents import create_deep_agent
    return create_deep_agent(
        model=get_chat_model(),
        tools=build_deepagent_tools(),
        system_prompt=AGENT_SYSTEM_PROMPT,
    )


async def _run_agent_deepagents(
    prompt: str,
    tool_schemas: list[dict],
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """deepagents 引擎驱动的 Agent 循环，产出与旧 _run_agent 一致的事件。"""
    from app.agent.event_adapter import translate_event
    engine = _build_engine()
    # 阶段 1：8 段上下文已由调用方拼进 prompt，直接作为用户消息
    # 此处用 engine.astream 迭代，将事件翻译为内部事件
    # （完整实现需解析 astream 产出的消息/tool_calls，经 translate_event 映射）
    ...
```

> 注：由于 deepagents `astream` 产出的原始消息结构与 `translate_event` 期望的语义事件不完全一致，Task 5 的实现在测试驱动下逐步逼近——先跑通 `_FakeAgent` 测试（验证事件结构），再对接真实 engine（Task 6 验证）。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_runner_deepagents.py -v`
Expected: PASS（`_FakeAgent` 驱动，事件结构正确）

- [ ] **Step 5: 运行现有 agent 相关测试确认不回归**

Run: `pytest tests/test_agent_observability.py tests/test_cancel_integration.py tests/test_streaming_integration.py tests/test_sse_integration.py -v`
Expected: 尽量通过；失败项记入 Task 6 的修复清单

- [ ] **Step 6: 提交**

```bash
git add app/agent/runner.py tests/test_runner_deepagents.py
git commit -m "refactor(agent): swap hand-written ReAct loop for deepagents engine"
```

---

### Task 6: 真实引擎集成与回归修复

**Files:**
- Modify: `app/agent/runner.py`
- Modify（如需）: `tests/test_cancel_integration.py`、`tests/test_streaming_integration.py`、`tests/test_sse_integration.py`
- Test: `tests/test_runner_deepagents.py`（追加真实引擎用例）

**Interfaces:**
- Consumes: Task 5 的 `_run_agent_deepagents` 骨架
- Produces: 与真实 `create_deep_agent` 正确对接的完整实现

- [ ] **Step 1: 用真实 engine 替换 _FakeAgent，验证流解析**

```python
# tests/test_runner_deepagents.py 追加
@pytest.mark.asyncio
async def test_real_engine_streams(monkeypatch):
    """真实 engine：用最小输入验证 astream 可被迭代并产出事件。"""
    from app.agent import runner
    # 保留默认 engine（真实 create_deep_agent）
    events = []
    session_state = {
        "session_id": "s2", "user_id": "u2",
        "chat_history": [], "summary": "",
    }
    async for etype, data in runner.run_agent_stream("你好", session_state):
        events.append((etype, data))
    etypes = [e[0] for e in events]
    assert "final" in etypes
```

> 该用例需要真实 LLM 调用（DeepSeek）。若无凭据则标记 `@pytest.mark.skipif`（读取 `LLM_API_KEY`），CI 无凭据时跳过。

- [ ] **Step 2: 运行真实引擎测试**

Run: `pytest tests/test_runner_deepagents.py::test_real_engine_streams -v`
Expected: PASS（有 LLM 凭据时）或 SKIP（无凭据时）

- [ ] **Step 3: 修复 Task 5 步骤 5 记录的回归项**

逐项修复 `test_cancel_integration.py` / `test_streaming_integration.py` / `test_sse_integration.py` 的失败，保持事件结构与取消语义不变。

- [ ] **Step 4: 运行全量测试**

Run: `pytest -v`
Expected: 全绿（或仅有明确记录的 skip）

- [ ] **Step 5: 运行冒烟脚本**

Run: `bash scripts/acceptance.sh`
Expected: 通过

- [ ] **Step 6: 提交**

```bash
git add app/agent/runner.py tests/
git commit -m "fix(agent): integrate real deepagents engine and restore regression tests"
```

---

### Task 7: 阶段 1 验收核对

**Files:**
- Test: 无新文件，运行既有验证

**Interfaces:**
- Consumes: 前 6 个任务的产物
- Produces: 阶段 1 完成确认

- [ ] **Step 1: SSE 事件逐字段 diff 验证**

写一个对比脚本（临时）或手动验证：同一输入下，新旧引擎产出的 `step`/`sql`/`llm_call`/`final` 字段结构一致。记录差异。

- [ ] **Step 2: 手动 cancel API 验证**

Run: 起服务 `python -m app.main`，POST `/api/chat` 触发长任务，POST `/api/chat/{id}/cancel`。
Expected: cancel 后产出 `final` 且 `subtype="cancelled"`，前端正常结束。

- [ ] **Step 3: 手动 SSE 验证**

Run: `curl -N -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"session_id":"v1","message":"查一下订单表"}'`
Expected: 逐事件输出 `step`/`sql`/`final`，格式与重构前一致。

- [ ] **Step 4: 更新 spec 状态**

在 `docs/superpowers/specs/2026-08-10-deepagents-refactor-design.md` 的阶段 1 验收清单打勾（标 `[x]`）。

- [ ] **Step 5: 提交**

```bash
git add docs/superpowers/specs/2026-08-10-deepagents-refactor-design.md
git commit -m "docs(superpowers): mark phase-1 acceptance items as verified"
```

---

## Self-Review 记录

**1. Spec 覆盖**：
- 阶段 1 引擎替换 → Task 5、6
- SSE 事件流兼容 → Task 4、5
- ChatOpenAI 接入 → Task 2
- 工具适配 → Task 3
- 8 段上下文保留 → Task 5（明确保留 build_context 注入）
- 测试与验收 → Task 6（全量 + 冒烟）、Task 7（SSE diff + cancel 手动）
- 依赖引入 → Task 1

**2. 占位符扫描**：Task 5 Step 3 的 `_run_agent_deepagents` 标注"完整实现需解析 astream 产出"。这是**已知的待接线点**（依赖 deepagents 实际流结构），计划里用 `_FakeAgent` 先行验证事件结构、Task 6 对接真实引擎，符合 TDD 渐进逼近。已避免"TBD/implement later"式空占位。

**3. 类型一致性**：
- `run_agent_stream` 签名在各任务中保持一致
- `translate_event` 产出事件类型（`text`/`tool_start`/`tool_end`）与 runner 内部事件字典一致
- `build_deepagent_tools()` 返回 `list[StructuredTool]`，`get_chat_model()` 返回 `ChatOpenAI`，供 Task 5 `_build_engine` 使用——跨任务类型一致
- `registry` 引用与 `_execute_tool` 用法在 Task 3 保持一致

## Execution Handoff

保存后向用户提供执行选择（subagent-driven vs inline）。
