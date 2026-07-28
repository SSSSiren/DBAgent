"""
执行器 — 异步编排，逐个用例调用 run_agent_stream 并收集结果
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from app.agent.runner import run_agent_stream
from app.agent.context import extract_sql_from_text
from app.client.onedba import get_onedba_client
from app.config import get_settings
from app.observation import flush_langfuse

from .models import TestCase, CaseResult, RunDetail, SQLJudgeResult, EvaluationReport, DimensionScores, HdcVerificationData, RunConfig, ToolCallRecord, LLMCallRecord
from .judges.sql_judge import judge_sql_correctness
from .judges.quality_judge import judge_answer_quality
from .judges.efficiency_judge import compute_efficiency_from_stats
from .scorer import score_case


@dataclass
class _AgentRunOutput:
    """单次 Agent 执行的原始输出（不含 Judge）"""
    tool_calls: list[dict[str, Any]]
    tool_call_details: dict[str, int]
    sqls: list[str]
    final_response: str
    stats: dict[str, Any]
    error: str | None
    duration_ms: int
    hdc_context: str = ""
    llm_calls: list[dict[str, Any]] = field(default_factory=list)


async def _execute_agent_once(
    question: str,
    session_state: dict[str, Any],
    timeout: float,
    trace_name: str = "DBAgent-Chat",
    verbose: bool = False,
    log_prefix: str = "",
) -> _AgentRunOutput:
    """
    执行 Agent 一次，返回原始指标（不做 Judge）。

    这是重复执行的内层循环，每次调用都重新创建 session_state，
    确保各次运行之间完全独立。
    """
    tool_calls: list[dict[str, Any]] = []
    tool_call_details: dict[str, int] = {}
    sqls: list[str] = []
    final_response = ""
    stats: dict[str, Any] = {}
    error: str | None = None
    llm_calls: list[dict[str, Any]] = []

    start_time = time.monotonic()

    try:
        async with asyncio.timeout(timeout):
            async for event_type, data in run_agent_stream(question, session_state, trace_name=trace_name):
                if event_type == "step":
                    step = data.get("step", "")
                    status = data.get("status", "")
                    if step == "thinking" and verbose:
                        text = data.get("text", "")
                        if text:
                            print(f"{log_prefix}  [Thinking] {text[:200]}")
                    elif step.startswith("tool:"):
                        tool_name = step.replace("tool:", "")
                        if status == "running":
                            tool_calls.append({"tool": tool_name, "args": data.get("input", {}), "result": ""})
                            tool_call_details[tool_name] = tool_call_details.get(tool_name, 0) + 1
                            if verbose:
                                tool_input = data.get("input", {})
                                # 截断过长的参数
                                tool_input_short = {
                                    k: (str(v)[:120] + "..." if len(str(v)) > 120 else v)
                                    for k, v in tool_input.items()
                                }
                                print(f"{log_prefix}  [Tool] {tool_name}({tool_input_short})")
                        elif status == "completed":
                            # 回填工具输出和耗时到对应的 tool_calls 条目
                            content = data.get("content", "")
                            elapsed_ms = data.get("elapsed_ms", None)
                            nl2sql_timings = data.get("nl2sql_timings", None)
                            for tc in reversed(tool_calls):
                                if tc.get("result") == "" and tc.get("tool") == tool_name:
                                    tc["result"] = str(content)
                                    if elapsed_ms is not None:
                                        tc["elapsed_ms"] = elapsed_ms
                                    if nl2sql_timings is not None:
                                        tc["nl2sql_timings"] = nl2sql_timings
                                    break
                            if verbose:
                                content_preview = str(content)[:120].replace("\n", " ")
                                print(f"{log_prefix}          → {content_preview}{'...' if len(str(content)) > 120 else ''}")
                elif event_type == "sql":
                    sql_text = data.get("sql", "")
                    if sql_text:
                        sqls.append(sql_text)
                        if verbose:
                            print(f"{log_prefix}  [SQL] {sql_text[:200]}")
                elif event_type == "llm_call":
                    llm_calls.append(data)
                elif event_type == "final":
                    final_response = data.get("response", "")
                    stats = data.get("stats", {})
    except asyncio.TimeoutError:
        error = f"执行超时（{timeout}秒）"
    except Exception as e:
        error_msg = str(e)
        if "error result: success" in error_msg.lower():
            if not final_response:
                final_response = "(查询完成)"
        else:
            error = f"执行异常: {error_msg}"

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # 兜底提取 SQL
    if not sqls and final_response:
        extracted = extract_sql_from_text(final_response)
        if extracted:
            sqls.append(extracted)

    return _AgentRunOutput(
        tool_calls=tool_calls,
        tool_call_details=tool_call_details,
        sqls=sqls,
        final_response=final_response,
        stats=stats,
        error=error,
        duration_ms=duration_ms,
        llm_calls=llm_calls,
    )


def _make_session_state(schema_id: int, db_name: str = "dw_onedba") -> dict[str, Any]:
    """
    创建初始 session_state（每次执行独立创建）。

    注入前置条件：当前数据库已选定为指定的数据库。
    模拟真实用户场景——用户在 OneDBA 平台上点击进入某个数据库后直接提问。
    Agent 不需要调用 list_databases 或 select_database 探索数据库，
    但需要自行发现表名、列名和枚举值。
    """
    return {
        "selected_schema_id": schema_id,
        "selected_database": {"schemaId": schema_id, "schemaName": db_name},
        "chat_history": [],
        "summary": "",
    }


async def _inject_hdc_context(
    session_state: dict[str, Any],
    user_input: str,
    database_name: str,
    schema_id: int,
    user_id: str = "evaluation",
    hdc_tables: list[str] | None = None,
    hdc_namespace: str | None = None,
) -> bool:
    """
    向 session_state 注入 HDC 数据底座上下文。

    模拟生产环境 app/api/routes.py 中的 HDC 检索流程：
    1. 检查 hdc_enabled 配置
    2. 创建 OpenViking 客户端 → HDCRetriever
    3. 检索 HDC 上下文并格式化为 [_hdc_context]
    4. （可选）按 --hdc-tables 白名单过滤，模拟限定表知识库
    5. 静默降级：HDC 不可用时记录日志并返回 False

    Args:
        hdc_tables: 可选的白名单表名列表。传入时仅保留匹配的 HDC 表上下文，
                    未匹配的表对应的 ### section 会被移除。
                    用于测试 Agent 在知识库缺少某些表时的行为。

    Returns:
        True 表示 HDC 上下文注入成功，False 表示降级或跳过。
    """
    from app.config import get_settings as _cfg

    settings = _cfg()
    if not settings.hdc_enabled:
        return False

    try:
        from app.datavault.retriever import HDCRetriever
        from app.knowledge.openviking import OpenVikingClient as OVC

        ov = OVC(settings.kb_openviking_url, user_id)
        await ov.start()
        try:
            retriever = HDCRetriever(ov)
            hdc_ctx = await retriever.retrieve(
                user_input, schema_id, database_name,
                table_filter=hdc_tables,
                namespace=hdc_namespace,
            )
            if hdc_ctx:
                session_state["_hdc_context"] = retriever.format_context(hdc_ctx)
                return True
            return False
        finally:
            await ov.close()
    except Exception:
        # 静默降级：HDC 不可用不阻塞评测
        return False


def _build_run_detail(run: _AgentRunOutput) -> RunDetail:
    """从 _AgentRunOutput 构建 RunDetail"""
    stats = run.stats
    turns = stats.get("num_turns", 0)
    if isinstance(turns, dict):
        turns = turns.get("value", 0)
    tokens = stats.get("tokens", 0)
    if isinstance(tokens, dict):
        tokens = tokens.get("value", 0)
    input_tokens = stats.get("input_tokens", 0)
    if isinstance(input_tokens, dict):
        input_tokens = input_tokens.get("value", 0)
    output_tokens = stats.get("output_tokens", 0)
    if isinstance(output_tokens, dict):
        output_tokens = output_tokens.get("value", 0)
    prep_ms = stats.get("prep_ms", 0)
    ttfb_ms = stats.get("ttfb_ms", None)

    first_tool, first_table_used, called_find_table = _extract_first_tool_info(run)

    return RunDetail(
        duration_ms=run.duration_ms,
        prep_ms=float(prep_ms) if prep_ms else 0.0,
        ttfb_ms=float(ttfb_ms) if ttfb_ms else None,
        tool_call_count=len(run.tool_calls),
        tool_call_details=run.tool_call_details,
        turns=int(turns) if turns else 0,
        total_tokens=int(tokens) if tokens else 0,
        input_tokens=int(input_tokens) if input_tokens else 0,
        output_tokens=int(output_tokens) if output_tokens else 0,
        generated_sqls=run.sqls,
        error=run.error,
        first_tool=first_tool,
        first_table_used=first_table_used,
        called_find_table_before_query=called_find_table,
    )


def _extract_first_tool_info(agent_output: _AgentRunOutput) -> tuple[str, str, bool]:
    """
    从 Agent 执行的工具调用记录中提取首轮追踪信息。

    返回 (first_tool, first_table_used, called_find_table_before_query)

    - first_tool: 第一个调用的工具名称
    - first_table_used: 第一个查询类工具使用的表名
      - query_database: 从 args["table_name"] 提取
      - execute_sql: 从 args["sql"] 中用正则提取 FROM/JOIN 后的表名
    - called_find_table_before_query: 首次查询前是否调用了 find_table
    """
    tool_calls = agent_output.tool_calls
    if not tool_calls:
        return ("", "", False)

    first_tool = tool_calls[0].get("tool", "")

    # 遍历找首个查询类工具
    first_table_used = ""
    seen_find_table = False
    called_find_table_before_query = False
    found_query_tool = False

    for tc in tool_calls:
        tool_name = tc.get("tool", "")
        if tool_name == "find_table":
            if not found_query_tool:
                seen_find_table = True
            continue

        if tool_name in ("query_database", "execute_sql"):
            if not found_query_tool:
                found_query_tool = True
                called_find_table_before_query = seen_find_table

                if tool_name == "query_database":
                    first_table_used = str(tc.get("args", {}).get("table_name", ""))
                elif tool_name == "execute_sql":
                    sql = str(tc.get("args", {}).get("sql", ""))
                    # 提取 FROM 或 JOIN 后的表名
                    m = re.search(r'\bFROM\s+(\w+)', sql, re.IGNORECASE)
                    if m:
                        first_table_used = m.group(1)
                    else:
                        m = re.search(r'\bJOIN\s+(\w+)', sql, re.IGNORECASE)
                        if m:
                            first_table_used = m.group(1)

    return (first_tool, first_table_used, called_find_table_before_query)


def _verify_hdc_injection(
    hdc_context: str,
    test_case: TestCase,
    agent_output: _AgentRunOutput,
) -> HdcVerificationData:
    """
    验证 HDC 上下文是否正确注入并被 Agent 使用。

    从参考 SQL 提取表名，检查是否在 HDC 上下文中出现；
    从 Agent SQL 提取实际使用的表名，判断是否为幻觉。

    Args:
        hdc_context: 注入的 HDC 上下文字符串
        test_case: 测试用例
        agent_output: Agent 执行输出

    Returns:
        HdcVerificationData 验证结果
    """
    # 提取参考表名
    reference_tables: list[str] = []
    if test_case.reference_sql:
        reference_tables = re.findall(r'\bFROM\s+(\w+)', test_case.reference_sql, re.IGNORECASE)
        reference_tables += re.findall(r'\bJOIN\s+(\w+)', test_case.reference_sql, re.IGNORECASE)
        reference_tables = list(dict.fromkeys(reference_tables))  # 去重保序

    reference_table = reference_tables[0] if reference_tables else ""

    # 检查参考表名是否在 HDC 上下文中出现
    correct_table_in_context = False
    if reference_table and hdc_context:
        # 检查多种匹配模式：### table_name 或直接的 table_name
        correct_table_in_context = (
            f"### {reference_table}" in hdc_context
            or reference_table in hdc_context
        )

    # 从 Agent SQL 提取实际使用的表名
    agent_table_used = ""
    if agent_output.sqls:
        agent_sql = agent_output.sqls[-1]
        m = re.search(r'\bFROM\s+(\w+)', agent_sql, re.IGNORECASE)
        if m:
            agent_table_used = m.group(1)
        else:
            m = re.search(r'\bJOIN\s+(\w+)', agent_sql, re.IGNORECASE)
            if m:
                agent_table_used = m.group(1)

    # 判断 Agent 是否使用了正确的表名
    agent_used_correct_table = (
        agent_table_used.lower() == reference_table.lower()
        if agent_table_used and reference_table
        else False
    )

    # 判断幻觉：agent_table_used 既不在 HDC 上下文中也不在参考 SQL 中
    is_hallucination = False
    if agent_table_used and hdc_context:
        in_hdc = (
            f"### {agent_table_used}" in hdc_context
            or agent_table_used in hdc_context
        )
        in_reference = (
            agent_table_used.lower() in [t.lower() for t in reference_tables]
        )
        is_hallucination = not in_hdc and not in_reference

    injected = bool(hdc_context)
    context_chars = len(hdc_context)

    return HdcVerificationData(
        injected=injected,
        context_chars=context_chars,
        reference_table=reference_table,
        correct_table_in_context=correct_table_in_context,
        agent_table_used=agent_table_used,
        agent_used_correct_table=agent_used_correct_table,
        is_hallucination=is_hallucination,
    )


def _compute_std(values: list[float], mean: float) -> float:
    """计算样本标准差"""
    n = len(values)
    if n < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return round(math.sqrt(variance), 2)


def _extract_ref_table(reference_sql: str) -> str:
    """从参考 SQL 中提取第一个表名（FROM 或 JOIN 后的表名）。"""
    if not reference_sql:
        return ""
    m = re.search(r'\bFROM\s+(\w+)', reference_sql, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\bJOIN\s+(\w+)', reference_sql, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


async def _run_single_case(
    test_case: TestCase,
    schema_id: int,
    timeout: float,
    repeat: int,
    onedba_client: Any,
    llm_client: Any,
    use_llm_judge: bool,
    use_quality_judge: bool,
    enable_hdc: bool = False,
    db_name: str = "dw_onedba",
    verbose: bool = False,
    verbose_hdc: bool = False,
    judge_model: str = "deepseek-v4-flash-260425",
    hdc_tables: list[str] | None = None,
    hdc_namespace: str | None = None,
) -> CaseResult:
    """
    执行单条测试用例，支持重复执行取平均。

    流程：
    1. 重复执行 Agent N 次，收集每次的原始指标
    2. 取最后一次的回复用于 Judge（避免 N×N 的 LLM Judge 调用）
    3. 效率指标取 N 次平均
    4. 聚合为 CaseResult
    """
    started_at = datetime.now()

    # 重复执行时并行运行，但用 semaphore 限制并发数。
    # 限制为 4，避免过多 Claude Code CLI 子进程（每个 Agent 一个子进程）耗尽系统资源。
    _repeat_semaphore = asyncio.Semaphore(4)

    # HDC 检索结果缓存：同一条用例的多次 repeat 共享一次检索，
    # 避免 N 个并发 find() 请求打满 OpenViking 连接池。
    _hdc_cache: dict[str, str] = {}  # key: 缓存内容字符串
    _hdc_cache_lock = asyncio.Lock()

    async def _get_hdc_context() -> str:
        """获取 HDC 上下文（带缓存，同用例多次 run 只检索一次）。"""
        cache_key = f"{schema_id}:{db_name}:{hdc_namespace}:{test_case.question}"
        async with _hdc_cache_lock:
            if cache_key in _hdc_cache:
                return _hdc_cache[cache_key]
        # 未命中：执行检索
        session_state = _make_session_state(schema_id, db_name)
        hdc_ok = await _inject_hdc_context(
            session_state,
            test_case.question,
            session_state["selected_database"]["schemaName"],
            schema_id,
            hdc_tables=hdc_tables,
            hdc_namespace=hdc_namespace,
        )
        result = session_state.get("_hdc_context", "") if hdc_ok else ""
        async with _hdc_cache_lock:
            _hdc_cache[cache_key] = result
        return result

    async def _run_one(run_index: int) -> _AgentRunOutput:
        async with _repeat_semaphore:
            session_state = _make_session_state(schema_id, db_name)
            hdc_context = ""
            if enable_hdc:
                hdc_context = await _get_hdc_context()
                if hdc_context:
                    session_state["_hdc_context"] = hdc_context
                    if verbose_hdc:
                        chars = len(hdc_context)
                        ref_table = _extract_ref_table(test_case.reference_sql)
                        in_context = ref_table in hdc_context if ref_table else "N/A"
                        in_context_str = "yes" if in_context else "no"
                        if repeat > 1:
                            print(f"    [HDC] {test_case.case_id}#{run_index}: 已注入({chars}字符) | 正确表在上下文中={in_context_str}")
                        else:
                            print(f"    [HDC] {test_case.case_id}: 已注入({chars}字符) | 正确表在上下文中={in_context_str}")
                    elif run_index == 0 and not verbose_hdc:
                        print(f"    [HDC] 上下文已注入")
                else:
                    print(f"    [HDC] {test_case.case_id}#{run_index}: 降级 — 检索失败，Agent 将盲搜")
                    if verbose_hdc:
                        print(f"    [HDC] {test_case.case_id}#{run_index}: 注入失败，跳过")

            # ── SQL 记忆检索（参照 routes.py 逻辑）──
            from app.config import get_settings as _eval_cfg
            _eval_settings = _eval_cfg()
            if getattr(_eval_settings, "sql_memory_enabled", False):
                try:
                    from app.memory.manager import get_storage as _eval_storage
                    from app.memory.sql_memory import embed_text as _eval_embed

                    store = _eval_storage().sql_memory_store
                    if store is not None:
                        scope = getattr(_eval_settings, "sql_memory_scope", "user")
                        top_k = getattr(_eval_settings, "sql_memory_top_k", 5)
                        min_sim = getattr(_eval_settings, "sql_memory_min_similarity", 0.0)
                        db_name_selected = db_name or ""
                        user_id = "default"

                        query_embedding = await _eval_embed(test_case.question)
                        if query_embedding is not None:
                            sql_memories = await store.search_similar(
                                user_id=user_id,
                                query_embedding=query_embedding,
                                database_name=db_name_selected,
                                scope=scope,
                                limit=top_k,
                                min_similarity=min_sim,
                            )
                            if sql_memories:
                                session_state["_sql_memories"] = sql_memories
                                print(f"    [SQLMem] {test_case.case_id}#{run_index}: 注入 {len(sql_memories)} 条记忆")
                                for i, m in enumerate(sql_memories):
                                    sql_preview = (m.get("sql_truncated") or m.get("sql_text", ""))[:80]
                                    print(f"      {i+1}. sim={m.get('similarity', 0):.4f} | {m.get('question', '')[:50]} | {sql_preview}")
                            elif run_index == 0:
                                print(f"    [SQLMem] {test_case.case_id}#{run_index}: 未找到相关记忆")
                        elif run_index == 0:
                            print(f"    [SQLMem] {test_case.case_id}#{run_index}: embedding 不可用，降级")
                except Exception as e:
                    if run_index == 0:
                        print(f"    [SQLMem] {test_case.case_id}#{run_index}: 检索失败 ({type(e).__name__})")

            trace_name = f"eval/{test_case.case_id}/run-{run_index}"
            output = await _execute_agent_once(
                test_case.question, session_state, timeout, trace_name=trace_name,
                verbose=verbose,
                log_prefix=f"  [{test_case.case_id}#{run_index}]" if verbose else "",
            )
            output.hdc_context = hdc_context
            return output

    if repeat > 1:
        # 为 asyncio.gather 加整体超时保护，防止死锁导致评测永久卡住。
        # 每个单独 run 已有 timeout 秒超时，gather 超时设为 repeat * timeout * 2 留足余量。
        gather_timeout = repeat * timeout * 2
        try:
            runs = list(await asyncio.wait_for(
                asyncio.gather(*[_run_one(i) for i in range(repeat)]),
                timeout=gather_timeout,
            ))
        except asyncio.TimeoutError:
            # 超时时尽力收集已完成的结果
            print(f"    [WARN] {test_case.case_id}: asyncio.gather 超时（{gather_timeout}s），部分 run 可能未完成")
            runs = []
            for i in range(repeat):
                runs.append(_AgentRunOutput(
                    tool_calls=[], tool_call_details={}, sqls=[], final_response="",
                    stats={}, error=f"评测超时（gather {gather_timeout}s）", duration_ms=int(gather_timeout * 1000),
                ))
    else:
        runs = [await _run_one(0)]

    completed_at = datetime.now()
    total_duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    # 取最后一次运行的回复用于 Judge
    last_run = runs[-1]

    # 效率指标：取 N 次平均
    tool_counts = [len(r.tool_calls) for r in runs]
    avg_tool_count = sum(tool_counts) / len(tool_counts)

    durations = [r.duration_ms for r in runs]
    avg_duration = sum(durations) / len(durations)

    # 合并所有运行的工具调用详情（用于效率评判）
    merged_tool_details: dict[str, int] = {}
    for r in runs:
        for tool_name, count in r.tool_call_details.items():
            merged_tool_details[tool_name] = merged_tool_details.get(tool_name, 0) + count
    # 取平均
    avg_tool_details: dict[str, int] = {}
    for tool_name, total in merged_tool_details.items():
        avg_tool_details[tool_name] = round(total / repeat)

    # turns 和 tokens 取平均
    avg_turns = 0
    avg_tokens = 0
    avg_input_tokens = 0
    avg_output_tokens = 0
    turn_values: list[float] = []
    token_values: list[float] = []
    input_token_values: list[float] = []
    output_token_values: list[float] = []
    for r in runs:
        stats = r.stats
        t = stats.get("num_turns", 0)
        if isinstance(t, dict):
            t = t.get("value", 0)
        tok = stats.get("tokens", 0)
        if isinstance(tok, dict):
            tok = tok.get("value", 0)
        itok = stats.get("input_tokens", 0)
        if isinstance(itok, dict):
            itok = itok.get("value", 0)
        otok = stats.get("output_tokens", 0)
        if isinstance(otok, dict):
            otok = otok.get("value", 0)
        turn_values.append(float(t or 0))
        token_values.append(float(tok or 0))
        input_token_values.append(float(itok or 0))
        output_token_values.append(float(otok or 0))
    avg_turns = sum(turn_values) / len(turn_values) if turn_values else 0
    avg_tokens = sum(token_values) / len(token_values) if token_values else 0
    avg_input_tokens = sum(input_token_values) / len(input_token_values) if input_token_values else 0
    avg_output_tokens = sum(output_token_values) / len(output_token_values) if output_token_values else 0

    # 构建平均 stats（用于效率评判）
    avg_stats = {
        "num_turns": int(avg_turns),
        "tokens": int(avg_tokens),
        "input_tokens": int(avg_input_tokens),
        "output_tokens": int(avg_output_tokens),
        "duration_ms": int(avg_duration),
    }

    # 预构建 run_details（在 judge 循环之前，judge 循环会回填 sql_score / quality_score）
    run_details = [_build_run_detail(r) for r in runs]

    # SQL 正确性评判 & 回答质量评判：对所有运行分别评判后取平均
    # repeat=1 时行为不变
    per_run_sql_scores: list[float] = []       # 纳入均值计算的正常得分
    per_run_quality_scores: list[float] = []
    per_run_sql_judges: list = []               # 所有 judge 结果（用于取最后）
    per_run_quality_judges: list = []
    per_run_verifications: list = []             # 各次 HDC 验证结果（用于聚合）

    for i, run in enumerate(runs):
        # ── SQL 正确性评判 ──
        gen_sql = run.sqls[-1] if run.sqls else ""
        if not gen_sql and run.final_response:
            extracted = extract_sql_from_text(run.final_response)
            if extracted:
                gen_sql = extracted

        sj = None
        if gen_sql or test_case.reference_sql:
            try:
                sj = await judge_sql_correctness(
                    generated_sql=gen_sql,
                    reference_sql=test_case.reference_sql,
                    schema_id=schema_id,
                    question=test_case.question,
                    onedba_client=onedba_client,
                    llm_client=llm_client if use_llm_judge else None,
                    model=judge_model,
                )
            except Exception:
                # judge 因外部服务不可用而失败 → 标记为异常值（None），不纳入均值
                sj = None

            if sj is not None:
                per_run_sql_judges.append(sj)
                # 若 judge 本身执行成功（进入了 tier），得分正常纳入
                # tier==0 且 score==0 且无 explanation 表示 judge 失败（外部异常），不纳入
                if sj.tier > 0 or (sj.score == 0.0 and sj.llm_judge_explanation):
                    per_run_sql_scores.append(sj.score)
                elif sj.tier > 0:
                    per_run_sql_scores.append(sj.score)
                else:
                    # tier==0 且无补充说明 → 标记为异常值
                    run_details[i].sql_score = None
                    continue
            else:
                # judge 调用本身异常
                run_details[i].sql_score = None
                continue

            run_details[i].sql_score = sj.score
        else:
            run_details[i].sql_score = None

        # ── 回答质量评判 ──
        qj = None
        if use_quality_judge and llm_client and run.final_response:
            try:
                qj = await judge_answer_quality(
                    question=test_case.question,
                    agent_response=run.final_response,
                    reference_sql=test_case.reference_sql,
                    llm_client=llm_client,
                    model=judge_model,
                )
            except Exception:
                qj = None

            if qj is not None:
                per_run_quality_judges.append(qj)
                per_run_quality_scores.append(qj.score)
                run_details[i].quality_score = qj.score
            else:
                run_details[i].quality_score = None
        else:
            run_details[i].quality_score = None

        # ── HDC 验证 ──
        if enable_hdc and run.hdc_context:
            hv = _verify_hdc_injection(run.hdc_context, test_case, run)
            per_run_verifications.append(hv)

    # 取最后一次 judge 作为 CaseResult 主 judge（保持结构兼容）
    sql_judge = per_run_sql_judges[-1] if per_run_sql_judges else None
    quality_judge = per_run_quality_judges[-1] if per_run_quality_judges else None

    # repeat>1 时用平均值覆盖 score；排除异常值（None 得分）
    if repeat > 1 and per_run_sql_scores:
        avg_sql = sum(per_run_sql_scores) / len(per_run_sql_scores)
        if sql_judge:
            sql_judge.score = avg_sql
    if repeat > 1 and per_run_quality_scores:
        avg_quality = sum(per_run_quality_scores) / len(per_run_quality_scores)
        if quality_judge:
            quality_judge.score = avg_quality

    # 效率评判（基于平均指标）
    efficiency = compute_efficiency_from_stats(
        stats=avg_stats,
        tool_call_count=int(avg_tool_count),
        tool_call_details=avg_tool_details,
    )

    # 计算标准差
    std_tool = _compute_std([float(c) for c in tool_counts], avg_tool_count)
    std_tokens = _compute_std(token_values, avg_tokens)
    std_input_tokens = _compute_std(input_token_values, avg_input_tokens)
    std_output_tokens = _compute_std(output_token_values, avg_output_tokens)
    std_latency = _compute_std([float(d) for d in durations], avg_duration)
    std_turns = _compute_std(turn_values, avg_turns)

    # HDC 验证：对各次运行结果聚合
    hdc_verification = None
    if enable_hdc and per_run_verifications:
        # injected: 任意一次注入成功即为 True
        injected = any(v.injected for v in per_run_verifications)
        # correct_table_in_context: 任意一次匹配即为 True (OR)
        correct_table = any(v.correct_table_in_context for v in per_run_verifications)
        # agent_used_correct_table: 多数运行正确即为 True (majority vote)
        agent_correct_votes = sum(1 for v in per_run_verifications if v.agent_used_correct_table)
        agent_used = agent_correct_votes > len(per_run_verifications) / 2
        # is_hallucination: 任意一次出现幻觉即为 True (保守策略)
        hallucination = any(v.is_hallucination for v in per_run_verifications)
        # 取最后一次的详细数据作为模板，覆盖聚合后的布尔值
        hdc_verification = per_run_verifications[-1]
        hdc_verification.injected = injected
        hdc_verification.correct_table_in_context = correct_table
        hdc_verification.agent_used_correct_table = agent_used
        hdc_verification.is_hallucination = hallucination

    # 错误信息：取最后一次的错误
    error = last_run.error

    # 构建 ToolCallRecord 和 LLMCallRecord 列表
    tool_call_records = [
        ToolCallRecord(
            tool=tc.get("tool", ""),
            args=tc.get("args", {}),
            result=tc.get("result", ""),
            elapsed_ms=tc.get("elapsed_ms", None),
            nl2sql_timings=tc.get("nl2sql_timings", None),
        )
        for tc in last_run.tool_calls
    ]

    llm_call_records = [
        LLMCallRecord(
            iteration=lc.get("iteration", 0),
            model=lc.get("model", ""),
            input_messages=lc.get("input_messages", []),
            output_content=lc.get("output_content", ""),
            output_tool_calls=lc.get("output_tool_calls", []),
            is_final=lc.get("is_final", False),
        )
        for lc in last_run.llm_calls
    ]

    result = CaseResult(
        test_case=test_case,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=total_duration_ms,
        agent_response=last_run.final_response[:5000],
        generated_sqls=last_run.sqls,
        tool_calls=last_run.tool_calls,
        sql_judge=sql_judge,
        quality_judge=quality_judge,
        efficiency=efficiency,
        error=error,
        repeat_count=repeat,
        run_details=run_details,
        std_tool_calls=std_tool,
        std_tokens=std_tokens,
        std_input_tokens=std_input_tokens,
        std_output_tokens=std_output_tokens,
        std_latency_ms=std_latency,
        std_turns=std_turns,
        hdc_verification=hdc_verification,
        tool_call_records=tool_call_records,
        llm_call_records=llm_call_records,
    )

    return score_case(result)


def _disable_langfuse() -> None:
    """禁用 Langfuse 观测（避免评测数据污染生产 trace）"""
    os.environ["LANGFUSE_ENABLED"] = "false"
    # 清除 get_settings() 的 lru_cache，使环境变量变更生效
    from app.config import get_settings
    get_settings.cache_clear()


def _set_llm_model(model: str) -> None:
    """覆盖 LLM 模型（用于评测时切换模型）"""
    os.environ["LLM_MODEL"] = model
    from app.config import get_settings
    get_settings.cache_clear()


def _create_llm_client() -> AsyncOpenAI | None:
    """创建 LLM 客户端（用于 Tier 3 和 Quality Judge）"""
    settings = get_settings()
    if not settings.llm_api_key:
        print("[Evaluation] 警告: LLM_API_KEY 未配置，将跳过 LLM-as-judge")
        return None
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


async def run_evaluation(
    test_cases: list[TestCase],
    schema_id: int = 65938636,
    timeout: float = 120.0,
    concurrency: int = 1,
    repeat: int = 1,
    use_llm_judge: bool = True,
    use_quality_judge: bool = True,
    keep_langfuse: bool = False,
    llm_model: str | None = None,
    enable_hdc: bool = False,
    db_name: str = "dw_onedba",
    verbose: bool = False,
    verbose_hdc: bool = False,
    hdc_gen_tokens: int | None = None,
    hdc_tables: list[str] | None = None,
    hdc_namespace: str | None = None,
    cli_command: str | None = None,
    progress_callback: Any = None,
) -> EvaluationReport:
    """
    执行评测。

    Args:
        test_cases: 测试用例列表
        schema_id: OneDBA schemaId
        timeout: 单条用例超时（秒）
        concurrency: 并发数（1=顺序执行）
        repeat: 每条用例重复次数（默认 1，取平均）
        use_llm_judge: 是否启用 Tier 3 LLM 评判
        use_quality_judge: 是否启用回答质量评判
        keep_langfuse: 是否保留 Langfuse trace
        llm_model: 覆盖 .env 中的 llm_model（如 deepseek-v4-pro）
        progress_callback: 进度回调，签名 callback(case_id, index, total)

    Returns:
        EvaluationReport
    """
    if not keep_langfuse:
        _disable_langfuse()

    if llm_model:
        _set_llm_model(llm_model)

    # 记录评测开始时间
    eval_start = time.monotonic()

    onedba_client = get_onedba_client()
    llm_client = _create_llm_client() if (use_llm_judge or use_quality_judge) else None

    # 读取当前生效的 LLM 配置（用于报告）
    settings = get_settings()
    effective_llm_model = settings.llm_model
    effective_llm_base_url = settings.llm_base_url
    # judge 使用与 Agent 相同的模型（而非硬编码 "deepseek-chat"），确保在内部网关上有可用模型
    judge_model = effective_llm_model

    if concurrency <= 1:
        # 顺序执行
        case_results: list[CaseResult] = []
        total = len(test_cases)
        for i, tc in enumerate(test_cases):
            repeat_info = f" ×{repeat}" if repeat > 1 else ""
            print(f"[{i+1}/{total}] {tc.case_id} ({tc.difficulty.value}){repeat_info} — {tc.question[:60]}...")
            result = await _run_single_case(
                tc, schema_id, timeout, repeat, onedba_client, llm_client,
                use_llm_judge, use_quality_judge, enable_hdc=enable_hdc, db_name=db_name,
                verbose=verbose, verbose_hdc=verbose_hdc, judge_model=judge_model,
                hdc_tables=hdc_tables,
                hdc_namespace=hdc_namespace,
            )
            case_results.append(result)
            status = "✅" if result.passed else ("⚠️" if result.error else "❌")
            std_info = ""
            if repeat > 1:
                std_info = f"  tools={result.efficiency.tool_call_count if result.efficiency else 0}±{result.std_tool_calls:.0f}  tokens={result.efficiency.total_tokens if result.efficiency else 0}±{result.std_tokens:.0f}"
            print(f"     {status} score={result.overall_score:.2%}  latency={result.duration_ms}ms{std_info}")
            if progress_callback:
                progress_callback(tc.case_id, i, total)
    else:
        # 并发执行
        semaphore = asyncio.Semaphore(concurrency)
        total = len(test_cases)
        results_map: dict[int, CaseResult] = {}

        async def _run_with_semaphore(idx: int, tc: TestCase) -> None:
            async with semaphore:
                repeat_info = f" ×{repeat}" if repeat > 1 else ""
                print(f"[{idx+1}/{total}] {tc.case_id}{repeat_info} 开始...")
                result = await _run_single_case(
                    tc, schema_id, timeout, repeat, onedba_client, llm_client,
                    use_llm_judge, use_quality_judge, enable_hdc=enable_hdc, db_name=db_name,
                    verbose=verbose, verbose_hdc=verbose_hdc, judge_model=judge_model,
                    hdc_tables=hdc_tables,
                    hdc_namespace=hdc_namespace,
                )
                results_map[idx] = result
                status = "✅" if result.passed else ("⚠️" if result.error else "❌")
                print(f"[{idx+1}/{total}] {tc.case_id} {status} score={result.overall_score:.2%}")

        tasks = [
            _run_with_semaphore(i, tc)
            for i, tc in enumerate(test_cases)
        ]
        # 整体超时保护：每条用例 timeout * repeat * 2（留足余量），
        # 防止死锁导致整个评测永久卡住。
        overall_timeout = timeout * repeat * 2 * total
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=overall_timeout)
        except asyncio.TimeoutError:
            print(f"\n[WARN] 整体评测超时（{overall_timeout}s），强制收集已完成的结果...")
        case_results = [results_map[i] for i in range(total) if i in results_map]
        if len(case_results) < total:
            print(f"[WARN] 仅收集到 {len(case_results)}/{total} 条结果，{total - len(case_results)} 条未完成")

    if keep_langfuse:
        await asyncio.shield(flush_langfuse())

    # 汇总报告
    total = len(case_results)
    passed = sum(1 for c in case_results if c.passed)
    failed = sum(1 for c in case_results if not c.passed and c.error is None)
    error_count = sum(1 for c in case_results if c.error is not None)

    scores = [c.overall_score for c in case_results]
    avg_score = sum(scores) / total if total > 0 else 0.0

    latencies = [c.duration_ms for c in case_results]
    avg_latency = sum(latencies) / total if total > 0 else 0.0

    tools = [c.efficiency.tool_call_count if c.efficiency else 0 for c in case_results]
    avg_tools = sum(tools) / total if total > 0 else 0.0

    turns = [c.efficiency.turns if c.efficiency else 0 for c in case_results]
    avg_turns = sum(turns) / total if total > 0 else 0.0

    tokens = [c.efficiency.total_tokens if c.efficiency else 0 for c in case_results]
    avg_tokens = sum(tokens) / total if total > 0 else 0.0

    input_tokens = [c.efficiency.input_tokens if c.efficiency else 0 for c in case_results]
    avg_input_tokens = sum(input_tokens) / total if total > 0 else 0.0

    output_tokens = [c.efficiency.output_tokens if c.efficiency else 0 for c in case_results]
    avg_output_tokens = sum(output_tokens) / total if total > 0 else 0.0

    prep_values = [c.run_details[0].prep_ms for c in case_results if c.run_details and c.run_details[0].prep_ms > 0]
    avg_prep_ms = sum(prep_values) / len(prep_values) if prep_values else 0.0

    ttfb_values = [c.run_details[0].ttfb_ms for c in case_results if c.run_details and c.run_details[0].ttfb_ms is not None]
    avg_ttfb_ms = sum(ttfb_values) / len(ttfb_values) if ttfb_values else None

    # 跨用例标准差平均
    std_tools = [c.std_tool_calls for c in case_results]
    avg_std_tools = sum(std_tools) / total if total > 0 else 0.0

    std_tokens_list = [c.std_tokens for c in case_results]
    avg_std_tokens = sum(std_tokens_list) / total if total > 0 else 0.0

    std_input_tokens_list = [c.std_input_tokens for c in case_results]
    avg_std_input_tokens = sum(std_input_tokens_list) / total if total > 0 else 0.0

    std_output_tokens_list = [c.std_output_tokens for c in case_results]
    avg_std_output_tokens = sum(std_output_tokens_list) / total if total > 0 else 0.0

    std_latency_list = [c.std_latency_ms for c in case_results]
    avg_std_latency = sum(std_latency_list) / total if total > 0 else 0.0

    std_turns_list = [c.std_turns for c in case_results]
    avg_std_turns = sum(std_turns_list) / total if total > 0 else 0.0

    # 维度平均分
    dim_avg = DimensionScores()
    if total > 0:
        dim_avg = DimensionScores(
            sql_syntax=sum(c.dimensions.sql_syntax for c in case_results) / total,
            table_column=sum(c.dimensions.table_column for c in case_results) / total,
            filter_condition=sum(c.dimensions.filter_condition for c in case_results) / total,
            result_data=sum(c.dimensions.result_data for c in case_results) / total,
            sql_standard=sum(c.dimensions.sql_standard for c in case_results) / total,
        )

    # 构建 RunConfig
    run_config = RunConfig(
        repeat=repeat,
        concurrency=concurrency,
        db_name=db_name,
        hdc_enabled=enable_hdc,
        hdc_tables=hdc_tables or [],
        hdc_namespace=hdc_namespace,
        use_llm_judge=use_llm_judge,
        use_quality_judge=use_quality_judge,
        cli_command=cli_command,
    )

    return EvaluationReport(
        schema_id=schema_id,
        llm_model=effective_llm_model,
        llm_base_url=effective_llm_base_url,
        total_cases=total,
        total_duration_ms=int((time.monotonic() - eval_start) * 1000),
        run_config=run_config,
        passed_cases=passed,
        failed_cases=failed,
        error_cases=error_count,
        overall_pass_rate=passed / total if total > 0 else 0.0,
        average_score=avg_score,
        average_latency_ms=avg_latency,
        average_tool_calls=avg_tools,
        average_turns=avg_turns,
        average_tokens=avg_tokens,
        average_input_tokens=avg_input_tokens,
        average_output_tokens=avg_output_tokens,
        average_prep_ms=avg_prep_ms,
        average_ttfb_ms=avg_ttfb_ms,
        std_tool_calls=avg_std_tools,
        std_tokens=avg_std_tokens,
        std_input_tokens=avg_std_input_tokens,
        std_output_tokens=avg_std_output_tokens,
        std_latency_ms=avg_std_latency,
        std_turns=avg_std_turns,
        dimension_averages=dim_avg,
        case_results=case_results,
        hdc_generation_tokens=hdc_gen_tokens,
    )
