"""
执行器 — 异步编排，逐个用例调用 run_agent_stream 并收集结果
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from app.agent.runner import run_agent_stream
from app.agent.context import extract_sql_from_text
from app.client.onedba import get_onedba_client
from app.config import get_settings
from app.observation import flush_langfuse

from .models import TestCase, CaseResult, RunDetail, SQLJudgeResult, EvaluationReport, DimensionScores
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


async def _execute_agent_once(
    question: str,
    session_state: dict[str, Any],
    timeout: float,
    trace_name: str = "SDK-DBAgent-Chat",
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

    start_time = time.monotonic()

    try:
        async with asyncio.timeout(timeout):
            async for event_type, data in run_agent_stream(question, session_state, trace_name=trace_name):
                if event_type == "step":
                    step = data.get("step", "")
                    status = data.get("status", "")
                    if step.startswith("tool:"):
                        tool_name = step.replace("tool:", "")
                        if status == "running":
                            tool_calls.append({"tool": tool_name, "args": data.get("input", {})})
                            tool_call_details[tool_name] = tool_call_details.get(tool_name, 0) + 1
                elif event_type == "sql":
                    sql_text = data.get("sql", "")
                    if sql_text:
                        sqls.append(sql_text)
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
    )


def _make_session_state(schema_id: int) -> dict[str, Any]:
    """
    创建初始 session_state（每次执行独立创建）。

    注入前置条件：当前数据库已选定为 dw_onedba (schema_id=65938636)。
    模拟真实用户场景——用户在 OneDBA 平台上点击进入某个数据库后直接提问。
    Agent 不需要调用 list_databases 或 select_database 探索数据库，
    但需要自行发现表名、列名和枚举值。
    """
    return {
        "selected_schema_id": schema_id,
        "selected_database": {"schemaName": "dw_onedba"},
        "chat_history": [],
        "summary": "",
    }


def _build_run_detail(run: _AgentRunOutput) -> RunDetail:
    """从 _AgentRunOutput 构建 RunDetail"""
    stats = run.stats
    turns = stats.get("num_turns", 0)
    if isinstance(turns, dict):
        turns = turns.get("value", 0)
    tokens = stats.get("tokens", 0)
    if isinstance(tokens, dict):
        tokens = tokens.get("value", 0)

    return RunDetail(
        duration_ms=run.duration_ms,
        tool_call_count=len(run.tool_calls),
        tool_call_details=run.tool_call_details,
        turns=int(turns) if turns else 0,
        total_tokens=int(tokens) if tokens else 0,
        generated_sqls=run.sqls,
        error=run.error,
    )


def _compute_std(values: list[float], mean: float) -> float:
    """计算样本标准差"""
    n = len(values)
    if n < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return round(math.sqrt(variance), 2)


async def _run_single_case(
    test_case: TestCase,
    schema_id: int,
    timeout: float,
    repeat: int,
    onedba_client: Any,
    llm_client: Any,
    use_llm_judge: bool,
    use_quality_judge: bool,
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

    async def _run_one(run_index: int) -> _AgentRunOutput:
        async with _repeat_semaphore:
            session_state = _make_session_state(schema_id)
            trace_name = f"eval/{test_case.case_id}/run-{run_index}"
            return await _execute_agent_once(
                test_case.question, session_state, timeout, trace_name=trace_name
            )

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
    turn_values: list[float] = []
    token_values: list[float] = []
    for r in runs:
        stats = r.stats
        t = stats.get("num_turns", 0)
        if isinstance(t, dict):
            t = t.get("value", 0)
        tok = stats.get("tokens", 0)
        if isinstance(tok, dict):
            tok = tok.get("value", 0)
        turn_values.append(float(t or 0))
        token_values.append(float(tok or 0))
    avg_turns = sum(turn_values) / len(turn_values) if turn_values else 0
    avg_tokens = sum(token_values) / len(token_values) if token_values else 0

    # 构建平均 stats（用于效率评判）
    avg_stats = {
        "num_turns": int(avg_turns),
        "tokens": int(avg_tokens),
        "duration_ms": int(avg_duration),
    }

    # SQL 正确性评判（仅对最后一次运行的 SQL）
    generated_sql = last_run.sqls[-1] if last_run.sqls else ""
    if not generated_sql and last_run.final_response:
        extracted = extract_sql_from_text(last_run.final_response)
        if extracted:
            generated_sql = extracted

    sql_judge = None
    if generated_sql or test_case.reference_sql:
        sql_judge = await judge_sql_correctness(
            generated_sql=generated_sql,
            reference_sql=test_case.reference_sql,
            schema_id=schema_id,
            question=test_case.question,
            onedba_client=onedba_client,
            llm_client=llm_client if use_llm_judge else None,
        )

    # 回答质量评判（仅对最后一次运行的回复）
    quality_judge = None
    if use_quality_judge and llm_client and last_run.final_response:
        quality_judge = await judge_answer_quality(
            question=test_case.question,
            agent_response=last_run.final_response,
            reference_sql=test_case.reference_sql,
            llm_client=llm_client,
        )

    # 效率评判（基于平均指标）
    efficiency = compute_efficiency_from_stats(
        stats=avg_stats,
        tool_call_count=int(avg_tool_count),
        tool_call_details=avg_tool_details,
    )

    # 计算标准差
    std_tool = _compute_std([float(c) for c in tool_counts], avg_tool_count)
    std_tokens = _compute_std(token_values, avg_tokens)
    std_latency = _compute_std([float(d) for d in durations], avg_duration)
    std_turns = _compute_std(turn_values, avg_turns)

    # 构建 run_details
    run_details = [_build_run_detail(r) for r in runs]

    # 错误信息：取最后一次的错误
    error = last_run.error

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
        std_latency_ms=std_latency,
        std_turns=std_turns,
    )

    return score_case(result)


def _disable_langfuse() -> None:
    """禁用 Langfuse 观测（避免评测数据污染生产 trace）"""
    os.environ["LANGFUSE_ENABLED"] = "false"
    # 清除 get_settings() 的 lru_cache，使环境变量变更生效
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
        progress_callback: 进度回调，签名 callback(case_id, index, total)

    Returns:
        EvaluationReport
    """
    if not keep_langfuse:
        _disable_langfuse()

    onedba_client = get_onedba_client()
    llm_client = _create_llm_client() if (use_llm_judge or use_quality_judge) else None

    if concurrency <= 1:
        # 顺序执行
        case_results: list[CaseResult] = []
        total = len(test_cases)
        for i, tc in enumerate(test_cases):
            repeat_info = f" ×{repeat}" if repeat > 1 else ""
            print(f"[{i+1}/{total}] {tc.case_id} ({tc.difficulty.value}){repeat_info} — {tc.question[:60]}...")
            result = await _run_single_case(
                tc, schema_id, timeout, repeat, onedba_client, llm_client,
                use_llm_judge, use_quality_judge,
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
                    use_llm_judge, use_quality_judge,
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

    # 跨用例标准差平均
    std_tools = [c.std_tool_calls for c in case_results]
    avg_std_tools = sum(std_tools) / total if total > 0 else 0.0

    std_tokens_list = [c.std_tokens for c in case_results]
    avg_std_tokens = sum(std_tokens_list) / total if total > 0 else 0.0

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

    return EvaluationReport(
        schema_id=schema_id,
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        error_cases=error_count,
        overall_pass_rate=passed / total if total > 0 else 0.0,
        average_score=avg_score,
        average_latency_ms=avg_latency,
        average_tool_calls=avg_tools,
        average_turns=avg_turns,
        average_tokens=avg_tokens,
        std_tool_calls=avg_std_tools,
        std_tokens=avg_std_tokens,
        std_latency_ms=avg_std_latency,
        std_turns=avg_std_turns,
        dimension_averages=dim_avg,
        case_results=case_results,
    )
