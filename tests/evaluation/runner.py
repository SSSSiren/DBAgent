"""
执行器 — 异步编排，逐个用例调用 run_agent_stream 并收集结果
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from app.agent.runner import run_agent_stream
from app.agent.context import extract_sql_from_text
from app.client.onedba import get_onedba_client
from app.config import get_settings

from .models import TestCase, CaseResult, SQLJudgeResult, EvaluationReport, DimensionScores
from .judges.sql_judge import judge_sql_correctness
from .judges.quality_judge import judge_answer_quality
from .judges.efficiency_judge import compute_efficiency_from_stats
from .scorer import score_case


async def _run_single_case(
    test_case: TestCase,
    schema_id: int,
    timeout: float,
    onedba_client: Any,
    llm_client: Any,
    use_llm_judge: bool,
    use_quality_judge: bool,
) -> CaseResult:
    """
    执行单条测试用例。

    流程：
    1. 构造 session_state（预选 schema，跳过数据库选择步骤）
    2. 调用 run_agent_stream 收集事件
    3. 提取 SQL、工具调用、stats、最终回复
    4. 调用各 Judge 评分
    5. 聚合为 CaseResult
    """
    session_state: dict[str, Any] = {
        "selected_schema_id": schema_id,
        "selected_database": {"schemaName": "dw_onedba"},
        "chat_history": [],
        "summary": "",
    }

    tool_calls: list[dict[str, Any]] = []
    tool_call_details: dict[str, int] = {}
    sqls: list[str] = []
    final_response = ""
    stats: dict[str, Any] = {}
    error: str | None = None

    started_at = datetime.now()
    start_time = time.monotonic()

    try:
        async with asyncio.timeout(timeout):
            async for event_type, data in run_agent_stream(
                test_case.question, session_state
            ):
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
        # SDK bug workaround: "error result: success" 表示正常完成
        if "error result: success" in error_msg.lower():
            if not final_response:
                final_response = "(查询完成)"
        else:
            error = f"执行异常: {error_msg}"

    completed_at = datetime.now()
    duration_ms = int((time.monotonic() - start_time) * 1000)

    # 兜底提取 SQL：从最终回复中提取
    if not sqls and final_response:
        extracted = extract_sql_from_text(final_response)
        if extracted:
            sqls.append(extracted)

    generated_sql = sqls[-1] if sqls else ""

    # SQL 正确性评判
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

    # 回答质量评判
    quality_judge = None
    if use_quality_judge and llm_client and final_response:
        quality_judge = await judge_answer_quality(
            question=test_case.question,
            agent_response=final_response,
            reference_sql=test_case.reference_sql,
            llm_client=llm_client,
        )

    # 效率评判
    efficiency = compute_efficiency_from_stats(
        stats=stats,
        tool_call_count=len(tool_calls),
        tool_call_details=tool_call_details,
    )

    result = CaseResult(
        test_case=test_case,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        agent_response=final_response[:5000],  # 截断过长回复
        generated_sqls=sqls,
        tool_calls=tool_calls,
        sql_judge=sql_judge,
        quality_judge=quality_judge,
        efficiency=efficiency,
        error=error,
    )

    return score_case(result)


def _disable_langfuse() -> None:
    """禁用 Langfuse 观测（避免评测数据污染生产 trace）"""
    os.environ["LANGFUSE_ENABLED"] = "false"
    # 清除 get_settings() 的 lru_cache，使环境变量变更生效
    from app.config import get_settings
    get_settings.cache_clear()
    # 重置 Langfuse 客户端单例，确保用新配置重新初始化
    import app.observation.langfuse as lf
    lf._langfuse_client = None


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
        use_llm_judge: 是否启用 Tier 3 LLM 评判
        use_quality_judge: 是否启用回答质量评判
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
            print(f"[{i+1}/{total}] {tc.case_id} ({tc.difficulty.value}) — {tc.question[:60]}...")
            result = await _run_single_case(
                tc, schema_id, timeout, onedba_client, llm_client,
                use_llm_judge, use_quality_judge,
            )
            case_results.append(result)
            status = "✅" if result.passed else ("⚠️" if result.error else "❌")
            print(f"     {status} score={result.overall_score:.2%}  latency={result.duration_ms}ms  tools={result.efficiency.tool_call_count if result.efficiency else 0}")
            if progress_callback:
                progress_callback(tc.case_id, i, total)
    else:
        # 并发执行
        semaphore = asyncio.Semaphore(concurrency)
        total = len(test_cases)
        results_map: dict[int, CaseResult] = {}

        async def _run_with_semaphore(idx: int, tc: TestCase) -> None:
            async with semaphore:
                print(f"[{idx+1}/{total}] {tc.case_id} 开始...")
                result = await _run_single_case(
                    tc, schema_id, timeout, onedba_client, llm_client,
                    use_llm_judge, use_quality_judge,
                )
                results_map[idx] = result
                status = "✅" if result.passed else ("⚠️" if result.error else "❌")
                print(f"[{idx+1}/{total}] {tc.case_id} {status} score={result.overall_score:.2%}")

        tasks = [
            _run_with_semaphore(i, tc)
            for i, tc in enumerate(test_cases)
        ]
        await asyncio.gather(*tasks)
        case_results = [results_map[i] for i in range(total)]

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
        dimension_averages=dim_avg,
        case_results=case_results,
    )