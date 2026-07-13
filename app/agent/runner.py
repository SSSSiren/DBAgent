"""
Agent 执行器 — 基于 OpenAI 兼容 API 的 ReAct Agent

职责：
1. 通过 ReAct 循环驱动 Agent：LLM 决策 → 工具执行 → 观察结果 → 继续
2. 将执行过程转换为 SSE 事件（step/sql/final）
3. 管理工具注册和调用
4. 收集观测指标
"""

import asyncio
import json
import time
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.context import build_context, update_session_state, extract_sql_from_text
from app.config import get_settings
from app.tools import TOOLS, get_tool_handler
from app.observation.langfuse import LangfuseObserver, extract_result_size


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


# ========== 工具适配层 ==========

def _build_tool_schemas() -> list[dict[str, Any]]:
    """将内部工具定义转换为 OpenAI function calling 格式"""
    schemas = []
    for tool in TOOLS:
        schemas.append({
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        })
    return schemas


async def _execute_tool(name: str, input_data: dict[str, Any]) -> str:
    """执行工具调用"""
    handler = get_tool_handler(name)
    if handler is None:
        return f"未知工具: {name}"

    try:
        result = await handler(**input_data)
        return str(result)
    except TypeError as e:
        return f"工具参数错误: {e}"
    except Exception as e:
        return f"工具执行异常: {e}"


# ========== Agent 引擎（ReAct 循环）==========

async def _run_agent(
    prompt: str,
    tool_schemas: list[dict[str, Any]],
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    ReAct 循环：LLM 决策 → 工具执行 → 观察结果 → 继续决策。

    产出格式统一的事件字典：
    {
        "type": "text" | "tool_start" | "tool_end" | "final",
        ...
    }

    Args:
        prompt: 用户问题（含上下文）
        tool_schemas: 工具定义列表
        cancel_event: 取消信号事件，为 None 时行为不变（向后兼容）
    """
    settings = get_settings()
    client = _get_llm_client()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # OpenAI function calling 工具格式
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_schemas
    ]

    max_iterations = 15
    start_time = time.monotonic()
    total_input_tokens = 0
    total_output_tokens = 0
    cancelled = False

    for iteration in range(max_iterations):
        # ── 取消检查：迭代边界 ──
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break

        # ── LLM 调用（竞速取消信号）──
        if cancel_event is not None:
            # 使用 asyncio.wait 竞速 LLM 调用和取消信号
            async def _llm_call():
                return await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    tools=openai_tools,
                    temperature=0.1,
                )

            async def _wait_cancel():
                await cancel_event.wait()

            llm_task = asyncio.create_task(_llm_call())
            cancel_wait_task = asyncio.create_task(_wait_cancel())

            done, pending = await asyncio.wait(
                [llm_task, cancel_wait_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()

            if llm_task in done:
                response = llm_task.result()
            else:
                # 取消信号先触发：取消 LLM task 并等待清理
                try:
                    await llm_task
                except asyncio.CancelledError:
                    pass  # 正常取消流程
                print(f"[Cancel] LLM task 已取消")
                cancelled = True
                break
        else:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=openai_tools,
                temperature=0.1,
            )

        # 累计 token 用量
        if response.usage:
            total_input_tokens += response.usage.prompt_tokens or 0
            total_output_tokens += response.usage.completion_tokens or 0

        choice = response.choices[0]
        message = choice.message

        # LLM 决定调用工具
        if message.tool_calls:
            # 添加助手消息（含工具调用）。
            # 使用 model_dump() 保留 DeepSeek 返回的 signature 等额外字段，
            # 否则下一轮 LLM 调用会报 "Missing required field: 'signature'"。
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    tc.model_dump()
                    for tc in message.tool_calls
                ],
            })

            # 先 yield 思考文本（LLM 在调用工具前的推理）
            if message.content:
                yield {
                    "type": "text",
                    "text": message.content,
                }

            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                yield {
                    "type": "tool_start",
                    "name": tool_name,
                    "input": tool_input,
                }

                # ── 工具执行（取消时加超时保护）──
                is_cancelled = cancel_event is not None and cancel_event.is_set()
                if is_cancelled:
                    try:
                        result = await asyncio.wait_for(
                            _execute_tool(tool_name, tool_input),
                            timeout=30,
                        )
                    except asyncio.TimeoutError:
                        print(f"[Cancel] 工具超时(30s): tool={tool_name}")
                        result = f"工具执行超时: {tool_name}"
                else:
                    result = await _execute_tool(tool_name, tool_input)

                yield {
                    "type": "tool_end",
                    "name": tool_name,
                    "content": result,
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # 工具执行后再次检查取消
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
        else:
            # 最终响应
            final_content = message.content or ""
            messages.append({
                "role": "assistant",
                "content": final_content,
            })
            duration_ms = int((time.monotonic() - start_time) * 1000)
            yield {
                "type": "final",
                "subtype": "completed",
                "content": final_content,
                "stats": {
                    "duration_ms": duration_ms,
                    "num_turns": iteration + 1,
                    "tokens": total_input_tokens + total_output_tokens,
                },
            }
            return

    # 被取消 / 达到最大迭代次数
    duration_ms = int((time.monotonic() - start_time) * 1000)
    if cancelled:
        yield {
            "type": "final",
            "subtype": "cancelled",
            "content": "",
            "stats": {
                "duration_ms": duration_ms,
                "num_turns": iteration + 1,
                "tokens": total_input_tokens + total_output_tokens,
            },
        }
    else:
        yield {
            "type": "final",
            "subtype": "max_iterations",
            "content": "抱歉，查询过程中步骤过多，已自动停止。请尝试简化您的问题。",
            "stats": {
                "duration_ms": duration_ms,
                "num_turns": max_iterations,
                "tokens": total_input_tokens + total_output_tokens,
            },
        }


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

    # 0. 创建 Langfuse 观测器
    observer = LangfuseObserver(
        session_id=session_id,
        user_input=user_input,
        user_id=session_state.get("user_id", ""),
        trace_name=trace_name,
    )
    observer.start_trace()

    # 1. 构建上下文
    context = build_context(session_state)
    if context:
        full_prompt = f"{context}\n\n用户问题: {user_input}"
    else:
        full_prompt = user_input

    # 2. 构建工具 schema
    tool_schemas = _build_tool_schemas()

    # 3. 收集执行信息
    tool_calls_info: list[dict[str, Any]] = []
    tool_call_counter: dict[str, int] = {}
    all_texts: list[str] = []

    # 4. 启动 Agent 引擎
    event_stream = _run_agent(full_prompt, tool_schemas, cancel_event)

    final_response = ""
    final_stats: dict[str, Any] = {}

    try:
        async for event in event_stream:
            event_type = event.get("type", "")

            if event_type == "text":
                text = event.get("text", "")
                all_texts.append(text)
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
                tool_name = event.get("name", "unknown")
                call_index = tool_call_counter.get(tool_name, 0)
                tool_call_counter[tool_name] = call_index + 1
                yield "step", {
                    "step": f"tool:{tool_name}",
                    "status": "running",
                    "call_index": call_index,
                }

                tool_input = event.get("input", {})
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
                call_index = tool_call_counter.get(tool_name, 0) - 1
                yield "step", {
                    "step": f"tool:{tool_name}",
                    "status": "completed",
                    "call_index": max(call_index, 0),
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

            elif event_type == "final":
                final_response = event.get("content", "")
                final_stats = event.get("stats", {})

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
