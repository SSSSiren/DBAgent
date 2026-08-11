"""
Agent 执行器 — 基于 deepagents 引擎

职责：
1. deepagents 引擎驱动 Agent：LLM 决策 → 工具执行 → 观察结果 → 继续
2. 将执行过程转换为 SSE 事件（step/sql/final）
3. 管理工具注册和调用
4. 收集观测指标
"""

import asyncio
import json
import time
from typing import Any, AsyncIterator

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from openai import AsyncOpenAI

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.context import build_context, update_session_state, extract_sql_from_text
from app.agent.event_adapter import translate_event, _normalize_message
from app.config import get_settings
from app.nl2sql.generator import EnrichmentContext, _nl2sql_enrichment
from app.tools import registry
from app.observation.langfuse import LangfuseObserver, extract_result_size
from app.tools.query_database import _nl2sql_timings as _nl2sql_timings_reader


# ========== LLM 客户端 ==========

_llm_client: AsyncOpenAI | None = None


def _get_llm_client() -> AsyncOpenAI:
    """获取 OpenAI 兼容客户端（模块级懒加载单例，复用 HTTP 连接池）"""
    global _llm_client
    if _llm_client is None:
        settings = get_settings()
        _llm_client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _llm_client


# ========== Token 统计回调 ==========

class TokenCountingCallback(BaseCallbackHandler):
    """LangChain 回调：从每次 LLM 调用中累计 token 用量。

    通过 on_llm_end 从 LLMResult.llm_output["token_usage"] 提取
    prompt_tokens 和 completion_tokens，累加到可变的容器属性上，
    供 _run_agent_deepagents 在流结束后读取。
    """

    def __init__(self) -> None:
        super().__init__()
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """从 LLMResult 提取 token_usage 并累计。"""
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})
        if token_usage:
            self.total_input_tokens += token_usage.get("prompt_tokens", 0)
            self.total_output_tokens += token_usage.get("completion_tokens", 0)


# ========== deepagents 引擎工厂 ==========

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


# ========== 工具适配层 ==========

def _build_tool_schemas() -> list[dict[str, Any]]:
    """将内部工具定义转换为 OpenAI function calling 格式（通过 registry）"""
    return registry.get_openai_schemas()


async def _execute_tool(name: str, input_data: dict[str, Any]) -> tuple[str, float]:
    """执行工具调用，使用 registry.execute 应用中间件（超时/错误归一化）。返回 (result, elapsed_ms)。"""
    t0 = time.monotonic()
    result = await registry.execute(name, **input_data)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return result, elapsed_ms


# ========== 消息解析辅助函数 ==========

def _extract_messages(chunk: dict[str, Any]) -> list[Any]:
    """从 astream chunk 中提取消息列表。

    兼容两种格式：
    - FakeAgent: {"messages": [...]}
    - 真实 deepagents (updates mode): {"node_name": {"messages": [...]}}
    """
    if "messages" in chunk:
        return chunk["messages"]
    for value in chunk.values():
        if isinstance(value, dict) and "messages" in value:
            return value["messages"]
    return []


# ========== Agent 引擎（deepagents）==========

async def _run_agent_deepagents(
    prompt: str,
    tool_schemas: list[dict[str, Any]],
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """deepagents 引擎驱动的 Agent 循环，产出与旧 _run_agent 一致的事件字典。

    Args:
        prompt: 用户问题（含上下文）
        tool_schemas: 工具定义列表（阶段 1 保留参数兼容，引擎内部已绑定工具）
        cancel_event: 取消信号事件，为 None 时行为不变（向后兼容）
    """
    from langchain_core.messages import HumanMessage

    settings = get_settings()
    start_time = time.monotonic()
    token_callback = TokenCountingCallback()
    cancelled = False
    iteration = 0
    max_iterations = 15
    tool_timings: dict[str, dict[str, float | int]] = {}

    # 完整对话历史（供 llm_call.input_messages 使用，与旧版 _run_agent 一致）
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # 待完成的工具调用（tool_start 已产出，等待 tool_end）
    # 每个条目含 tool_call_id，用于精确匹配（避免并发同工具调用错配）
    pending_tools: list[dict[str, Any]] = []

    # ── 取消检查：在启动引擎前 ──
    if cancel_event is not None and cancel_event.is_set():
        yield {
            "type": "final",
            "subtype": "cancelled",
            "content": "",
            "stats": {
                "duration_ms": 0,
                "num_turns": 0,
                "tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "tool_timings": {},
            },
        }
        return

    engine = _build_engine()

    try:
        async for chunk in engine.astream(
            {"messages": [HumanMessage(content=prompt)]},
            config={"callbacks": [token_callback]},
        ):
            # ── 取消检查：迭代边界 ──
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            if not isinstance(chunk, dict):
                continue

            chunk_messages = _extract_messages(chunk)
            if not chunk_messages:
                continue

            for msg in chunk_messages:
                normalized = _normalize_message(msg)
                content = normalized["content"]
                tool_calls = normalized["tool_calls"]
                role = normalized.get("role", "")

                # ── 工具结果消息（ToolMessage）→ 产出 tool_end ──
                if role == "tool":
                    tool_name = normalized.get("name", "")
                    tc_id = normalized.get("tool_call_id", "")
                    # 使用 translate_event 获取事件数据
                    translated = translate_event(msg)
                    # 按 tool_call_id 精确匹配待处理工具调用（避免并发同工具调用错配）
                    matched = None
                    for pt in pending_tools:
                        if pt.get("tool_call_id") == tc_id and not pt.get("done"):
                            matched = pt
                            break
                    if matched:
                        matched["done"] = True
                        tool_end_data = next(
                            (edata for etype, edata in translated if etype == "tool_end"),
                            {"name": tool_name, "content": content, "elapsed_ms": 0},
                        )
                        elapsed_ms = tool_end_data.get("elapsed_ms", 0)
                        if tool_name not in tool_timings:
                            tool_timings[tool_name] = {"count": 0, "total_ms": 0.0}
                        tool_timings[tool_name]["count"] += 1
                        tool_timings[tool_name]["total_ms"] += elapsed_ms
                        nl2sql_stage_timings = _nl2sql_timings_reader.get({})
                        yield {
                            "type": "tool_end",
                            "name": tool_name,
                            "content": content,
                            "elapsed_ms": elapsed_ms,
                            "nl2sql_timings": nl2sql_stage_timings if nl2sql_stage_timings else None,
                        }
                    else:
                        # 无匹配 pending（deepagents 引擎内部执行工具时可能出现）
                        # 仍然产出 tool_end 以确保 SSE 客户端可见，但省略 nl2sql_timings
                        import warnings
                        warnings.warn(
                            f"ToolMessage with tool_call_id={tc_id!r} has no matching pending tool_call. "
                            f"Yielding tool_end without nl2sql_timings.",
                            RuntimeWarning,
                        )
                        yield {
                            "type": "tool_end",
                            "name": tool_name,
                            "content": content,
                            "elapsed_ms": 0,
                            "nl2sql_timings": None,
                        }
                    # 追加 tool 消息到对话历史
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": content,
                    })
                    continue

                # ── AI 消息 → 产出 llm_call + 决策事件 ──
                # 产出 LLM 调用事件（input_messages 为当前完整对话历史）
                yield {
                    "type": "llm_call",
                    "iteration": iteration,
                    "model": settings.llm_model,
                    "input_messages": [
                        {"role": m.get("role"), "content": m.get("content", "")}
                        for m in messages
                    ],
                    "output_content": content,
                    "output_tool_calls": [
                        {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                        }
                        for tc in tool_calls
                    ],
                    "is_final": len(tool_calls) == 0,
                }

                if tool_calls:
                    # ── 追加助手消息到历史 ──
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    })

                    # ── 使用 translate_event 产出 text + tool_start ──
                    translated = translate_event(msg)
                    for etype, edata in translated:
                        if etype == "text":
                            yield {
                                "type": "text",
                                "text": edata["text"],
                            }
                        elif etype == "tool_start":
                            tool_name = edata["name"]
                            tool_input = edata["input"]
                            tc_id = edata.get("tool_call_id", "")
                            yield {
                                "type": "tool_start",
                                "name": tool_name,
                                "input": tool_input,
                            }
                            pending_tools.append({
                                "name": tool_name,
                                "input": tool_input,
                                "done": False,
                                "tool_call_id": tc_id,
                            })
                else:
                    # ── 最终响应 ──
                    messages.append({
                        "role": "assistant",
                        "content": content,
                    })
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    yield {
                        "type": "final",
                        "subtype": "completed",
                        "content": content,
                        "stats": {
                            "duration_ms": duration_ms,
                            "num_turns": iteration + 1,
                            "tokens": token_callback.total_input_tokens + token_callback.total_output_tokens,
                            "input_tokens": token_callback.total_input_tokens,
                            "output_tokens": token_callback.total_output_tokens,
                            "tool_timings": dict(tool_timings),
                        },
                    }
                    return

                iteration += 1
                if iteration >= max_iterations:
                    break

            if iteration >= max_iterations:
                break

    finally:
        if cancelled:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            yield {
                "type": "final",
                "subtype": "cancelled",
                "content": "",
                "stats": {
                    "duration_ms": duration_ms,
                    "num_turns": iteration,
                    "tokens": token_callback.total_input_tokens + token_callback.total_output_tokens,
                    "input_tokens": token_callback.total_input_tokens,
                    "output_tokens": token_callback.total_output_tokens,
                    "tool_timings": dict(tool_timings),
                },
            }

    # ── 循环结束后：处理未完成的 tool_end 和 max_iterations ──
    if not cancelled:
        # 为所有未完成的 tool call 产出 tool_end（FakeAgent 兼容 + 兜底路径）
        for pt in pending_tools:
            if not pt.get("done"):
                if pt["name"] not in tool_timings:
                    tool_timings[pt["name"]] = {"count": 0, "total_ms": 0.0}
                tool_timings[pt["name"]]["count"] += 1
                yield {
                    "type": "tool_end",
                    "name": pt["name"],
                    "content": "",
                    "elapsed_ms": 0,
                    "nl2sql_timings": None,
                }

        duration_ms = int((time.monotonic() - start_time) * 1000)
        yield {
            "type": "final",
            "subtype": "max_iterations",
            "content": "抱歉，查询过程中步骤过多，已自动停止。请尝试简化您的问题。",
            "stats": {
                "duration_ms": duration_ms,
                "num_turns": max_iterations,
                "tokens": token_callback.total_input_tokens + token_callback.total_output_tokens,
                "input_tokens": token_callback.total_input_tokens,
                "output_tokens": token_callback.total_output_tokens,
                "tool_timings": dict(tool_timings),
            },
        }


async def _run_agent(
    prompt: str,
    tool_schemas: list[dict[str, Any]],
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """[向后兼容] 委托给 _run_agent_deepagents。

    保留此包装器以兼容 test_cancel_integration.py 等直接导入 _run_agent 的测试。
    """
    async for event in _run_agent_deepagents(prompt, tool_schemas, cancel_event):
        yield event


# ========== 事件流处理 ==========

def _extract_sql_from_tool_result(tool_name: str, content: str) -> str:
    """从工具结果中提取 SQL"""
    if tool_name in ("query_database", "execute_sql"):
        return extract_sql_from_text(content)
    return ""


def _extract_sql_from_tool_input(tool_name: str, input_data: dict[str, Any]) -> str:
    """从工具输入参数中提取 SQL"""
    if tool_name == "execute_sql":
        sql = input_data.get("sql", "")
        if sql:
            return sql.replace("\\n", " ").replace("\\r", "").strip()
    return ""


# ========== 主入口 ==========

async def run_agent_stream(
    user_input: str,
    session_state: dict[str, Any],
    trace_name: str = "DBAgent-Chat",
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """
    流式运行 Agent，产出 SSE 事件。

    这是 Agent 层的唯一对外接口，被 API 路由调用。

    事件类型：
        ("step", {"step": "tool:xxx", "status": "running/completed"})
        ("step", {"step": "thinking", "text": "..."})
        ("sql", {"sql": "SELECT ..."})
        ("final", {"response": "...", "updated_state": {...}})

    Args:
        user_input: 用户当前输入的消息
        session_state: 会话状态字典
        trace_name: Langfuse trace 名称
        cancel_event: 取消信号事件，为 None 时行为不变（向后兼容）

    Yields:
        (event_type, data) 元组
    """
    session_id = session_state.get("session_id", "")
    t0 = time.monotonic()

    # 0. 创建 Langfuse 观测器
    observer = LangfuseObserver(
        session_id=session_id,
        user_input=user_input,
        user_id=session_state.get("user_id", ""),
        trace_name=trace_name,
    )
    observer.start_trace()

    # 1. 构建上下文
    context, ctx_tokens = build_context(session_state)
    if context:
        full_prompt = f"{context}\n\n用户问题: {user_input}"
    else:
        full_prompt = user_input

    # 1.5. 记录准备耗时（context 构建 + 上游检索耗时）
    prep_ms = (time.monotonic() - t0) * 1000

    # 2. 构建工具 schema（保留以兼容旧签名，引擎内部已绑定工具）
    tool_schemas = _build_tool_schemas()

    # 3. 收集执行信息
    tool_calls_info: list[dict[str, Any]] = []
    tool_call_counter: dict[str, int] = {}
    all_texts: list[str] = []
    t_start = time.monotonic()
    ttfb_ms: float | None = None
    ttfb_recorded = False

    # 3.5. 设置 NL2SQL 富化上下文（HDC 列描述 + SQL 历史记忆）
    # 通过 ContextVar 传递给 generate_sql()/repair_sql()，不修改工具 schema。
    enrichment_cfg = get_settings()
    enrichment = EnrichmentContext(
        hdc_ctx=session_state.get("_hdc_structured"),
        sql_memories=session_state.get("_sql_memories", []),
        hdc_column_budget=getattr(enrichment_cfg, "hdc_column_budget", 1200),
        sql_memory_budget=getattr(enrichment_cfg, "sql_memory_token_budget", 1500),
    )
    _nl2sql_enrichment.set(enrichment)

    # 4. 启动 Agent 引擎
    event_stream = _run_agent_deepagents(full_prompt, tool_schemas, cancel_event)

    final_response = ""
    final_stats: dict[str, Any] = {}

    try:
        async for event in event_stream:
            event_type = event.get("type", "")

            if event_type == "text":
                text = event.get("text", "")
                all_texts.append(text)
                # TTFB: 记录首个非 llm_call 事件的时间
                if not ttfb_recorded:
                    ttfb_ms = (time.monotonic() - t_start) * 1000
                    ttfb_recorded = True
                yield "step", {
                    "step": "thinking",
                    "status": "running",
                    "text": text,
                }
                # === Langfuse: 记录 LLM 推理 ===
                if len(all_texts) == 1:
                    observer.record_llm_call(
                        name="agent-reasoning",
                        input_data={"prompt": full_prompt[:500]},
                        output_data={"reasoning": text[:300]},
                    )
                else:
                    observer.record_llm_call(
                        name="agent-reasoning",
                        output_data={"reasoning": text[:300]},
                    )

            elif event_type == "tool_start":
                # TTFB: 记录首个非 llm_call 事件的时间
                if not ttfb_recorded:
                    ttfb_ms = (time.monotonic() - t_start) * 1000
                    ttfb_recorded = True

                tool_name = event.get("name", "unknown")
                call_index = tool_call_counter.get(tool_name, 0)
                tool_call_counter[tool_name] = call_index + 1

                tool_input = event.get("input", {})
                yield "step", {
                    "step": f"tool:{tool_name}",
                    "status": "running",
                    "call_index": call_index,
                    "input": tool_input,
                }
                sql = _extract_sql_from_tool_input(tool_name, tool_input)
                if sql:
                    yield "sql", {"sql": sql}

                tool_calls_info.append({
                    "tool": tool_name,
                    "args": tool_input,
                    "result": None,
                })

                # === Langfuse: 记录工具调用开始 ===
                observer.record_tool_call(
                    tool_name=tool_name,
                    input_data=tool_input,
                )

            elif event_type == "tool_end":
                tool_name = event.get("name", "unknown")
                content = event.get("content", "")
                elapsed_ms = event.get("elapsed_ms", 0)
                nl2sql_timings = event.get("nl2sql_timings", None)
                call_index = tool_call_counter.get(tool_name, 0) - 1
                yield "step", {
                    "step": f"tool:{tool_name}",
                    "status": "completed",
                    "call_index": max(call_index, 0),
                    "content": content,
                    "elapsed_ms": elapsed_ms,
                    "nl2sql_timings": nl2sql_timings,
                }

                sql = _extract_sql_from_tool_result(tool_name, content)
                if sql:
                    yield "sql", {"sql": sql}

                for tc in tool_calls_info:
                    if tc.get("tool") == tool_name and tc.get("result") is None:
                        tc["result"] = content
                        break

                # === Langfuse: 补充工具调用结果 ===
                row_count, col_count = extract_result_size(content)
                observer.update_tool_result(
                    tool_name=tool_name,
                    output_data=content,
                    row_count=row_count,
                    col_count=col_count,
                )

            elif event_type == "llm_call":
                # 转发 LLM 调用事件给外层 consumer（评测框架等）
                yield "llm_call", event

            elif event_type == "final":
                final_response = event.get("content", "")
                final_stats = event.get("stats", {})
                # 注入 TTFB（若首个事件前被取消，则以取消时刻为准）
                if ttfb_ms is not None:
                    final_stats["ttfb_ms"] = round(ttfb_ms, 2)
                else:
                    final_stats["ttfb_ms"] = None
                # 注入 ctx_tokens 和 prep_ms
                final_stats["ctx_tokens"] = ctx_tokens
                final_stats["prep_ms"] = round(prep_ms, 2)

    except Exception as e:
        error_msg = str(e)
        final_response = f"查询过程中发生错误：{error_msg}"
        print(f"[Agent] Error: {error_msg}")
    finally:
        response_for_trace = final_response or (all_texts[-1] if all_texts else "获取响应失败")
        flush_task = asyncio.create_task(observer.flush(response=response_for_trace))
        try:
            await asyncio.shield(flush_task)
        except asyncio.CancelledError:
            await flush_task
            raise

    # 5. 确保有最终响应
    if not final_response and all_texts:
        final_response = all_texts[-1]
    elif not final_response:
        final_response = "获取响应失败"

    # 6. 更新会话状态
    updated_state = update_session_state(
        session_state,
        user_input,
        final_response,
    )

    # 7. yield 最终事件
    yield "final", {
        "response": final_response,
        "updated_state": updated_state,
        "needs_confirmation": False,
        "pending_action": None,
        "tool_calls": tool_calls_info,
        "stats": final_stats,
    }