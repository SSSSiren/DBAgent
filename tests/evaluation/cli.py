#!/usr/bin/env python3
"""
Agent 性能评测 CLI 工具

用法:
    # 基础评测
    python -m tests.evaluation.cli run                     # 运行全部用例
    python -m tests.evaluation.cli run --ids TC-001 TC-005 # 指定用例
    python -m tests.evaluation.cli run --difficulty Hard   # 按难度筛选
    python -m tests.evaluation.cli run --baseline output/baseline.json  # 基线对比
    python -m tests.evaluation.cli list                    # 列出所有用例

    # HDC 对比
    python -m tests.evaluation.cli run --compare-hdc --ids CS-001 CS-007

    # SQL 记忆对比（纯记忆 vs 无记忆）
    python -m tests.evaluation.cli run --compare-sql-memory

    # SQL 记忆 + HDC 叠加对比
    python -m tests.evaluation.cli run --compare-sql-memory --with-hdc --verbose-hdc

    # SQL 记忆增量评测（跳过基线，复用已有测评结果）
    python -m tests.evaluation.cli run --compare-sql-memory --with-hdc \\
        --skip-seed --skip-baseline --baseline output/baseline.json \\
        --hdc-namespace recall_complete --verbose-hdc

    # CS 用例
    python -m tests.evaluation.cli run \\
        --test-file tests/docs/test_cases_onedba_cs_evaluation.md \\
        --schema-id 24223568 --db-name dw_onedba_cs \\
        --ids CS-001 CS-003 CS-005
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .loader import load_test_cases, filter_test_cases
from .runner import run_evaluation, _cleanup_sql_memory
from .reporter import generate_report, generate_hdc_comparison_report


def cmd_list(args: argparse.Namespace) -> None:
    """列出所有测试用例"""
    cases = load_test_cases(args.test_file)
    filtered = filter_test_cases(
        cases,
        difficulty=args.difficulty,
        category=args.category,
    )
    print(f"\n共 {len(filtered)} 条用例：\n")
    print(f"{'ID':<8} {'难度':<8} {'类别':<12} {'涉及表':<30} 问题")
    print("-" * 90)
    for tc in filtered:
        tables = ", ".join(tc.tables)
        print(f"{tc.case_id:<8} {tc.difficulty.value:<8} {tc.category:<12} {tables:<30} {tc.question[:50]}...")


def cmd_run(args: argparse.Namespace) -> None:
    """运行评测"""
    # 构建完整 CLI 命令（用于报告中复现）
    cli_cmd = f"python -m tests.evaluation.cli {' '.join(sys.argv[1:])}"

    # 互斥参数校验
    if args.with_hdc and args.compare_hdc:
        print("错误: --with-hdc 和 --compare-hdc 互斥，请选择其中一个")
        sys.exit(1)

    cases = load_test_cases(args.test_file)
    filtered = filter_test_cases(
        cases,
        ids=args.ids,
        difficulty=args.difficulty,
        category=args.category,
    )

    if not filtered:
        print("没有匹配的测试用例")
        return

    if args.compare_hdc:
        # ── 对比模式：跑两轮（无 HDC → 有 HDC），生成对比报告 ──
        _run_compare_hdc(args, filtered)
        return

    if args.compare_sql_memory:
        # ── SQL 记忆对比模式：baseline → 填充孪生测例 → 有记忆重跑 ──
        _run_compare_sql_memory(args, filtered)
        return

    # ── 单次评测 ──
    print(f"\n开始评测 {len(filtered)} 条用例...")
    if args.repeat > 1:
        print(f"（每条用例重复 {args.repeat} 次，取平均值）")
    if args.with_hdc:
        print("（已启用 HDC 数据底座）")
    hdc_tables: list[str] | None = None
    if args.hdc_tables:
        hdc_tables = [t.strip() for t in args.hdc_tables.split(",") if t.strip()]
        print(f"（HDC 限定表: {', '.join(hdc_tables)}）")
    hdc_namespace = args.hdc_namespace
    if hdc_namespace:
        print(f"（HDC 命名空间: {hdc_namespace}）")
    if args.no_llm_judge:
        print("（已跳过 LLM 评判 Tier 3）")
    if args.no_quality_judge:
        print("（已跳过回答质量评判）")
    if args.keep_langfuse:
        print("（保留 Langfuse trace）")
    if args.llm_model:
        print(f"（LLM 模型: {args.llm_model}）")
    if args.verbose:
        print("（详细日志模式 — 输出 Agent 中间过程）")
    if args.verbose_hdc:
        print("（详细 HDC 日志模式 — 输出每个用例的 HDC 注入状态）")
    print()

    async def _run() -> None:
        report = await run_evaluation(
            test_cases=filtered,
            schema_id=args.schema_id,
            timeout=args.timeout,
            concurrency=args.concurrency,
            repeat=args.repeat,
            use_llm_judge=not args.no_llm_judge,
            use_quality_judge=not args.no_quality_judge,
            keep_langfuse=args.keep_langfuse,
            llm_model=args.llm_model,
            enable_hdc=args.with_hdc,
            db_name=args.db_name or "dw_onedba",
            verbose=args.verbose,
            verbose_hdc=args.verbose_hdc,
            hdc_gen_tokens=args.hdc_gen_tokens,
            hdc_tables=hdc_tables,
            hdc_namespace=hdc_namespace,
            cli_command=cli_cmd,
        )

        # 生成报告
        json_path, md_path = generate_report(
            report,
            output_dir=args.output_dir,
            baseline_path=args.baseline,
        )

        _print_summary(report, json_path, md_path)

        # 关闭 SQL 记忆连接，避免 aiosqlite 后台线程阻塞进程退出
        await _cleanup_sql_memory()

    asyncio.run(_run())


def _run_compare_hdc(args: argparse.Namespace, filtered) -> None:
    """对比模式：先跑无 HDC 基线，再跑有 HDC，生成对比报告。"""
    # 构建完整 CLI 命令（用于报告中复现）
    cli_cmd = f"python -m tests.evaluation.cli {' '.join(sys.argv[1:])}"

    # ── 前置校验：hdc_enabled 必须为 True ──
    from app.config import get_settings as _cfg
    settings = _cfg()
    if not settings.hdc_enabled:
        print("错误: --compare-hdc 需要启用 HDC，但当前 HDC_ENABLED 未设置或为 false")
        print("请先运行: export HDC_ENABLED=true")
        sys.exit(1)

    # ── 预估耗时 ──
    avg_seconds_per_run = 90  # 每次 Agent 执行平均耗时（秒）
    total_runs = len(filtered) * args.repeat * 2  # 用例数 × repeat × 2 轮
    estimated_minutes = (total_runs * avg_seconds_per_run) / 60
    concurrency_note = ""
    if args.concurrency > 1:
        estimated_minutes /= args.concurrency
        concurrency_note = f"（并发度 {args.concurrency}）"
    print(f"\n预估耗时: ~{estimated_minutes:.0f} 分钟（{len(filtered)} 条用例 × 重复{args.repeat}次 × 2 轮{concurrency_note}）")

    print(f"\n{'='*60}")
    print("HDC 对比评测 — 第 1/2 轮：无 HDC（基线）")
    print(f"{'='*60}")
    print(f"共 {len(filtered)} 条用例", end="")
    if args.repeat > 1:
        print(f"，每条重复 {args.repeat} 次", end="")
    print("\n")

    # 解析 HDC 表白名单
    hdc_tables: list[str] | None = None
    if args.hdc_tables:
        hdc_tables = [t.strip() for t in args.hdc_tables.split(",") if t.strip()]
        print(f"（HDC 限定表: {', '.join(hdc_tables)}）")
    hdc_namespace = args.hdc_namespace
    if hdc_namespace:
        print(f"（HDC 命名空间: {hdc_namespace}）")

    async def _run() -> None:
        # Round 1: 无 HDC 基线
        no_hdc_report = await run_evaluation(
            test_cases=filtered,
            schema_id=args.schema_id,
            timeout=args.timeout,
            concurrency=args.concurrency,
            repeat=args.repeat,
            use_llm_judge=not args.no_llm_judge,
            use_quality_judge=not args.no_quality_judge,
            keep_langfuse=args.keep_langfuse,
            llm_model=args.llm_model,
            enable_hdc=False,
            db_name=args.db_name or "dw_onedba",
            verbose=args.verbose,
            verbose_hdc=args.verbose_hdc,
            hdc_gen_tokens=args.hdc_gen_tokens,
            cli_command=cli_cmd,
        )

        print(f"\n{'='*60}")
        print("HDC 对比评测 — 第 2/2 轮：有 HDC")
        print(f"{'='*60}\n")

        # Round 2: 有 HDC
        with_hdc_report = await run_evaluation(
            test_cases=filtered,
            schema_id=args.schema_id,
            timeout=args.timeout,
            concurrency=args.concurrency,
            repeat=args.repeat,
            use_llm_judge=not args.no_llm_judge,
            use_quality_judge=not args.no_quality_judge,
            keep_langfuse=args.keep_langfuse,
            llm_model=args.llm_model,
            enable_hdc=True,
            db_name=args.db_name or "dw_onedba",
            verbose=args.verbose,
            verbose_hdc=args.verbose_hdc,
            hdc_gen_tokens=args.hdc_gen_tokens,
            hdc_tables=hdc_tables,
            hdc_namespace=hdc_namespace,
            cli_command=cli_cmd,
        )

        # 生成对比报告
        json_path, md_path = generate_hdc_comparison_report(
            no_hdc_report,
            with_hdc_report,
            output_dir=args.output_dir,
        )

        # ── HDC 聚合摘要 ──
        _print_hdc_aggregate_summary(with_hdc_report)

        print(f"\n{'='*60}")
        print("HDC 对比评测完成")
        print(f"{'='*60}")
        print(f"\n基线（无 HDC）:")
        _print_summary(no_hdc_report, "", "")
        print(f"\nHDC 启用:")
        _print_summary(with_hdc_report, "", "")
        print(f"\nJSON 报告: {json_path}")
        print(f"Markdown 报告: {md_path}")

        # 清理
        await _cleanup_sql_memory()

    asyncio.run(_run())


def _run_compare_sql_memory(args: argparse.Namespace, filtered) -> None:
    """SQL 记忆对比模式：baseline → 填充孪生测例 → 有记忆重跑。"""
    cli_cmd = f"python -m tests.evaluation.cli {' '.join(sys.argv[1:])}"

    # ── 前置校验：sql_memory_enabled 必须为 True ──
    from app.config import get_settings as _cfg
    settings = _cfg()
    if not getattr(settings, "sql_memory_enabled", False):
        print("错误: --compare-sql-memory 需要启用 SQL 记忆，但当前 SQL_MEMORY_ENABLED 未设置或为 false")
        print("请先运行: export SQL_MEMORY_ENABLED=true")
        sys.exit(1)

    # ── 加载孪生测例 ──
    from .loader import load_test_cases as _load
    twin_cases = []
    if not args.skip_seed:
        twin_cases = _load(args.twin_cases)
        if not twin_cases:
            print(f"错误: 未找到孪生测例，请检查 --twin-cases 路径: {args.twin_cases}")
            sys.exit(1)
        print(f"已加载 {len(twin_cases)} 条孪生测例")
    else:
        print("--skip-seed: 跳过 Phase 2，使用已有 SQL 记忆记录")

    print(f"\n{'='*60}")
    if args.skip_baseline:
        print(f"SQL 记忆对比评测 — 跳过基线，直接测试增量效果")
    else:
        print("SQL 记忆对比评测 — 第 1/3 轮：无记忆（基线）")
    print(f"{'='*60}")
    if not args.skip_baseline:
        print(f"共 {len(filtered)} 条用例", end="")
        if args.repeat > 1:
            print(f"，每条重复 {args.repeat} 次", end="")
        print("\n")

    use_hdc = args.with_hdc  # 同时测试 SQL memory + HDC 时传入 --with-hdc
    hdc_tables: list[str] | None = None
    if args.hdc_tables:
        hdc_tables = [t.strip() for t in args.hdc_tables.split(",") if t.strip()]
    hdc_namespace = args.hdc_namespace
    if hdc_tables:
        print(f"（HDC 限定表: {', '.join(hdc_tables)}）")
    if hdc_namespace:
        print(f"（HDC 命名空间: {hdc_namespace}）")
    hdc_label = " + HDC" if use_hdc else ""
    no_mem_label = f"无记忆{'+HDC' if use_hdc else ''}（基线）"
    with_mem_label = f"有记忆{hdc_label}"

    async def _run() -> None:
        # Round 1: 基线（可从已有报告加载，也可跳过）
        baseline_report = None
        if args.skip_baseline:
            if not args.baseline:
                print("错误: --skip-baseline 需要配合 --baseline 指定基线 JSON 文件路径")
                sys.exit(1)
            import json as _json
            from .models import EvaluationReport as _ER
            with open(args.baseline, encoding="utf-8") as _bf:
                baseline_data = _json.load(_bf)
            baseline_report = _ER.model_validate(baseline_data)
            print(f"从基线 JSON 加载: {args.baseline}")
            print(f"  用例数: {baseline_report.total_cases}, 平均分: {baseline_report.average_score:.2%}")
        else:
            baseline_report = await run_evaluation(
                test_cases=filtered,
                schema_id=args.schema_id,
                timeout=args.timeout,
                concurrency=args.concurrency,
                repeat=args.repeat,
                use_llm_judge=not args.no_llm_judge,
                use_quality_judge=not args.no_quality_judge,
                keep_langfuse=args.keep_langfuse,
                llm_model=args.llm_model,
                enable_hdc=use_hdc,
                db_name=args.db_name or "dw_onedba",
                hdc_tables=hdc_tables,
                hdc_namespace=hdc_namespace,
                verbose=args.verbose,
                verbose_hdc=args.verbose_hdc,
                cli_command=cli_cmd,
            )

        seed_count = 0
        if not args.skip_seed and twin_cases:
            print(f"\n{'='*60}")
            print(f"SQL 记忆对比评测 — 第 2/3 轮：填充记忆库（孪生测例）")
            print(f"{'='*60}")
            print(f"共 {len(twin_cases)} 条孪生测例，直接灌入记忆库\n")

            seed_count = await _seed_sql_memory_from_twin_cases(
                twin_cases=twin_cases,
                schema_id=args.schema_id,
                db_name=args.db_name or "dw_onedba",
                user_id="default",
            )
            print(f"  SQL 记忆库已灌入 {seed_count} 条记录（使用孪生测例的参考答案 SQL）")
        else:
            # 使用已有记忆
            from app.memory.manager import get_storage
            store = get_storage().sql_memory_store
            if store is not None:
                await store.initialize()
                seed_count = len(await store.list_by_user("default", limit=100))
            print(f"\n  使用已有 SQL 记忆记录: {seed_count} 条")

        round_label = "第 3/3 轮" if (not args.skip_seed and twin_cases) else "第 2/2 轮"
        print(f"\n{'='*60}")
        print(f"SQL 记忆对比评测 — {round_label}：{with_mem_label}")
        print(f"{'='*60}\n")

        # Round 3: 有记忆（可能有 HDC）
        memory_report = await run_evaluation(
            test_cases=filtered,
            schema_id=args.schema_id,
            timeout=args.timeout,
            concurrency=args.concurrency,
            repeat=args.repeat,
            use_llm_judge=not args.no_llm_judge,
            use_quality_judge=not args.no_quality_judge,
            keep_langfuse=args.keep_langfuse,
            llm_model=args.llm_model,
            enable_hdc=use_hdc,
            db_name=args.db_name or "dw_onedba",
            hdc_tables=hdc_tables,
            hdc_namespace=hdc_namespace,
            verbose=args.verbose,
            verbose_hdc=args.verbose_hdc,
            cli_command=cli_cmd,
        )

        # ── 生成对比报告 ──
        json_path, md_path = _generate_sql_memory_comparison_report(
            baseline_report,
            memory_report,
            seed_count,
            output_dir=args.output_dir,
            hdc_enabled=use_hdc,
            cli_command=cli_cmd,
        )

        print(f"\n{'='*60}")
        print(f"SQL 记忆对比评测完成{'（含 HDC）' if use_hdc else ''}")
        print(f"{'='*60}")
        if args.skip_baseline:
            print(f"\n基线（来自 {args.baseline}）:")
        else:
            print(f"\n基线（{no_mem_label}）:")
        _print_summary(baseline_report, "", "")
        print(f"\n{with_mem_label}:")
        _print_summary(memory_report, "", "")
        print(f"\n记忆库记录数: {seed_count}")
        print(f"\nJSON 报告: {json_path}")
        print(f"Markdown 报告: {md_path}")

        # 清理
        await _cleanup_sql_memory()

    asyncio.run(_run())


async def _seed_sql_memory_from_twin_cases(
    twin_cases: list,
    schema_id: int,
    db_name: str,
    user_id: str = "default",
) -> int:
    """
    直接使用孪生测例的参考答案 SQL 灌入 SQL 记忆库，不经过 Agent 执行。

    每条孪生测例的 reference_sql 作为记忆内容写入，保证经验百分之百正确。
    """
    from app.memory.manager import get_storage
    from app.memory.sql_memory import embed_text

    store = get_storage().sql_memory_store
    if store is None:
        print("[SQLMem][WARN] SQL 记忆存储未初始化，无法灌入")
        return 0

    # 确保 store 已初始化（eval CLI 不经过 FastAPI lifespan，StorageManager.initialize() 可能未被调用）
    await store.initialize()

    count = 0
    for tc in twin_cases:
        if not tc.reference_sql or not tc.question:
            continue

        embedding = await embed_text(tc.question)

        await store.record(
            user_id=user_id,
            question=tc.question,
            sql=tc.reference_sql,
            table_names=tc.tables,
            database_name=db_name,
            schema_id=schema_id,
            execution_result={
                "row_count": tc.expected_row_count,
                "column_names": [],
                "data_preview": [],
                "execution_status": "success",
            },
            embedding=embedding,
        )
        count += 1

    # 关闭连接，避免 aiosqlite 后台线程阻塞进程退出
    await store.close()

    return count


def _generate_sql_memory_comparison_report(
    baseline_report,
    memory_report,
    seed_count: int,
    output_dir: str = "tests/evaluation/output",
    hdc_enabled: bool = False,
    cli_command: str = "",
) -> tuple[str, str]:
    """生成 SQL 记忆对比报告（JSON + Markdown），格式与 evaluation_report 对齐。"""
    import json
    import os
    from datetime import datetime

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 聚合指标计算 ──
    b = baseline_report
    m = memory_report

    metrics = [
        ("overall_pass_rate",       "通过率",         "pct",  False),
        ("average_score",           "平均分",         "pct",  False),
        ("average_latency_ms",      "平均延迟",       "ms",   True),
        ("average_prep_ms",         "平均准备耗时",   "ms",   True),
        ("average_ttfb_ms",         "平均 TTFB",      "ms",   True),
        ("average_tool_calls",      "平均工具调用",   ".1f",  True),
        ("average_turns",           "平均 Turns",      ".1f",  True),
        ("average_tokens",          "平均 Token",      ".0f",  True),
        ("average_input_tokens",    "平均输入 Token",  ".0f",  True),
        ("average_output_tokens",   "平均输出 Token",  ".0f",  True),
    ]

    def _val(report, field: str) -> float:
        v = getattr(report, field, 0)
        return float(v) if v is not None else 0

    # ── 维度对比 ──
    dim_keys = ["sql_syntax", "table_column", "filter_condition", "result_data", "sql_standard"]
    dim_labels = {"sql_syntax": "SQL 语法正确", "table_column": "表/列引用正确",
                   "filter_condition": "过滤条件正确", "result_data": "结果数据正确",
                   "sql_standard": "SQL 规范"}
    dim_weights = {"sql_syntax": "10%", "table_column": "10%", "filter_condition": "10%",
                   "result_data": "60%", "sql_standard": "10%"}

    dim_comparison: dict[str, dict] = {}
    for dk in dim_keys:
        bv = getattr(b.dimension_averages, dk, 0)
        mv = getattr(m.dimension_averages, dk, 0)
        dim_comparison[dk] = {"baseline": bv, "memory": mv, "delta": mv - bv}

    # ── 每个用例对比（含工具调用和 Token 详情）──
    case_comparison: list[dict] = []
    for bc in b.case_results:
        mc = next((c for c in m.case_results if c.test_case.case_id == bc.test_case.case_id), None)
        if mc is None:
            continue
        b_sql = bc.sql_judge.score if bc.sql_judge else 0
        m_sql = mc.sql_judge.score if mc.sql_judge else 0
        b_eff = bc.efficiency
        m_eff = mc.efficiency
        b_tools = b_eff.tool_call_count if b_eff else 0
        m_tools = m_eff.tool_call_count if m_eff else 0
        b_tokens = b_eff.total_tokens if b_eff else 0
        m_tokens = m_eff.total_tokens if m_eff else 0
        b_itoks = b_eff.input_tokens if b_eff else 0
        m_itoks = m_eff.input_tokens if m_eff else 0
        b_otoks = b_eff.output_tokens if b_eff else 0
        m_otoks = m_eff.output_tokens if m_eff else 0
        case_comparison.append({
            "case_id": bc.test_case.case_id,
            "difficulty": bc.test_case.difficulty.value,
            "category": bc.test_case.category,
            "question": bc.test_case.question[:80],
            "baseline_passed": bc.passed, "memory_passed": mc.passed,
            "baseline_sql_score": b_sql, "memory_sql_score": m_sql,
            "baseline_overall": bc.overall_score, "memory_overall": mc.overall_score,
            "overall_delta": mc.overall_score - bc.overall_score,
            "baseline_tools": b_tools, "memory_tools": m_tools,
            "tool_delta": m_tools - b_tools,
            "baseline_tokens": b_tokens, "memory_tokens": m_tokens,
            "token_delta": m_tokens - b_tokens,
            "baseline_input_tokens": b_itoks, "memory_input_tokens": m_itoks,
            "input_token_delta": m_itoks - b_itoks,
            "baseline_output_tokens": b_otoks, "memory_output_tokens": m_otoks,
            "output_token_delta": m_otoks - b_otoks,
            "baseline_latency": bc.duration_ms, "memory_latency": mc.duration_ms,
            "latency_delta": mc.duration_ms - bc.duration_ms,
        })

    improved = [c for c in case_comparison if c["overall_delta"] > 0.005]
    degraded = [c for c in case_comparison if c["overall_delta"] < -0.005]
    unchanged = [c for c in case_comparison if abs(c["overall_delta"]) <= 0.005]

    # ── JSON ──
    comparison_data = {
        "timestamp": timestamp, "seed_count": seed_count, "hdc_enabled": hdc_enabled,
        "cli_command": cli_command,
        "baseline": {"passed": b.passed_cases, "failed": b.failed_cases, "errors": b.error_cases,
                      "pass_rate": b.overall_pass_rate, "avg_score": b.average_score,
                      "avg_latency_ms": b.average_latency_ms, "avg_prep_ms": b.average_prep_ms,
                      "avg_ttfb_ms": b.average_ttfb_ms, "avg_tool_calls": b.average_tool_calls,
                      "avg_turns": b.average_turns, "avg_tokens": b.average_tokens,
                      "avg_input_tokens": b.average_input_tokens, "avg_output_tokens": b.average_output_tokens},
        "memory": {"passed": m.passed_cases, "failed": m.failed_cases, "errors": m.error_cases,
                    "pass_rate": m.overall_pass_rate, "avg_score": m.average_score,
                    "avg_latency_ms": m.average_latency_ms, "avg_prep_ms": m.average_prep_ms,
                    "avg_ttfb_ms": m.average_ttfb_ms, "avg_tool_calls": m.average_tool_calls,
                    "avg_turns": m.average_turns, "avg_tokens": m.average_tokens,
                    "avg_input_tokens": m.average_input_tokens, "avg_output_tokens": m.average_output_tokens},
        "summary": {"improved": len(improved), "degraded": len(degraded), "unchanged": len(unchanged),
                     "total": len(case_comparison)},
        "dimension_comparison": dim_comparison,
        "case_comparison": case_comparison,
    }
    json_path = os.path.join(output_dir, f"sql_memory_comparison_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, ensure_ascii=False, indent=2, default=str)

    # ── Markdown 报告 ──
    md_path = os.path.join(output_dir, f"sql_memory_comparison_{timestamp}.md")

    def _delta_str(base: float, cur: float, fmt: str) -> str:
        d = cur - base
        if fmt == "pct":
            return f"{base:.2%} → {cur:.2%} ({d:+.1%})"
        elif fmt == "ms":
            return f"{base:.0f}ms → {cur:.0f}ms ({d:+.0f}ms)"
        elif fmt == ".1f":
            return f"{base:.1f} → {cur:.1f} ({d:+.1f})"
        else:
            return f"{base:{fmt}} → {cur:{fmt}} ({d:+{fmt}})"

    def _trend(base: float, cur: float, lower_better: bool = False) -> str:
        d = cur - base
        if abs(d) < 0.001: return "➡️"
        if lower_better: return "📈" if d < 0 else "📉"
        return "📈" if d > 0 else "📉"

    with open(md_path, "w", encoding="utf-8") as fm:
        hdc_tag = "（含 HDC）" if hdc_enabled else ""
        fm.write(f"# SQL Memory 对比评测报告{hdc_tag}\n\n")
        fm.write(f"**生成时间**: {timestamp}\n")
        fm.write(f"**记忆库记录数**: {seed_count}\n")
        fm.write(f"**LLM 模型**: {b.llm_model}\n")
        fm.write(f"**LLM Base URL**: {b.llm_base_url}\n")
        if cli_command:
            fm.write(f"**CLI 命令**: `{cli_command}`\n")
        if hdc_enabled:
            fm.write(f"**HDC**: 已启用（两轮均注入 HDC 数据底座）\n")
        fm.write("\n")

        # ── 总览 ──
        fm.write("## 📊 总览\n\n")
        fm.write("| 指标 | 基线 | 有记忆 | 变化 | 趋势 |\n")
        fm.write("|------|------|--------|------|------|\n")
        for field, label, fmt, lower in metrics:
            bv = _val(b, field)
            mv = _val(m, field)
            if bv == 0 and mv == 0:
                continue
            ds = _delta_str(bv, mv, fmt)
            tr = _trend(bv, mv, lower)
            fm.write(f"| {label} | {ds} | {tr} |\n")
        fm.write("\n")

        # ── Memory Impact 汇总 ──
        fm.write("## 📈 Memory Impact 汇总\n\n")
        fm.write(f"- 改进用例: {len(improved)}\n")
        fm.write(f"- 退化用例: {len(degraded)}\n")
        fm.write(f"- 不变用例: {len(unchanged)}\n")
        total = len(case_comparison)
        fm.write(f"- 改进率: {len(improved)}/{total} ({len(improved)/total:.1%})" if total else "- 改进率: N/A")
        fm.write("\n\n")

        # ── 维度对比 ──
        fm.write("## 📐 维度平均分对比\n\n")
        fm.write("| 维度 | 权重 | 基线 | 有记忆 | 变化 | 趋势 |\n")
        fm.write("|------|------|------|--------|------|------|\n")
        for dk in dim_keys:
            dc = dim_comparison[dk]
            tr = "📈" if dc["delta"] > 0.001 else ("📉" if dc["delta"] < -0.001 else "➡️")
            fm.write(f"| {dim_labels[dk]} | {dim_weights[dk]} | {dc['baseline']:.2%} | "
                     f"{dc['memory']:.2%} | {dc['delta']:+.2%} | {tr} |\n")
        fm.write("\n")

        # ── 按难度分布对比 ──
        by_diff: dict[str, list] = {}
        for cc in case_comparison:
            by_diff.setdefault(cc["difficulty"], []).append(cc)
        fm.write("## 📋 按难度对比\n\n")
        fm.write("| 难度 | 用例数 | 基线通过率 | 有记忆通过率 | 基线平均分 | 有记忆平均分 | 分数变化 |\n")
        fm.write("|------|--------|-----------|-------------|-----------|-------------|----------|\n")
        for diff in ["Easy", "Medium", "Hard"]:
            cases = by_diff.get(diff, [])
            if not cases:
                continue
            n = len(cases)
            bp = sum(1 for c in cases if c["baseline_passed"]) / n
            mp = sum(1 for c in cases if c["memory_passed"]) / n
            bs = sum(c["baseline_overall"] for c in cases) / n
            ms = sum(c["memory_overall"] for c in cases) / n
            fm.write(f"| {diff} | {n} | {bp:.1%} | {mp:.1%} | {bs:.2%} | {ms:.2%} | {ms-bs:+.2%} |\n")
        fm.write("\n")

        # ── 逐用例详情 ──
        fm.write("## 📝 逐用例对比\n\n")
        fm.write("| 用例 | 难度 | 类别 | 基线 | 有记忆 | 分数变化 | 工具调用 | Token | 延迟 |\n")
        fm.write("|------|------|------|------|--------|----------|----------|-------|------|\n")
        for cc in case_comparison:
            bs = "✅" if cc["baseline_passed"] else "❌"
            ms = "✅" if cc["memory_passed"] else "❌"
            tool_str = f"{cc['baseline_tools']}→{cc['memory_tools']}"
            tok_str = f"{cc['baseline_tokens']}→{cc['memory_tokens']}"
            lat_str = f"{cc['baseline_latency']}→{cc['memory_latency']}ms"
            fm.write(f"| {cc['case_id']} | {cc['difficulty']} | {cc['category']} | "
                     f"{bs} {cc['baseline_overall']:.2%} | {ms} {cc['memory_overall']:.2%} | "
                     f"{cc['overall_delta']:+.2%} | {tool_str} | {tok_str} | {lat_str} |\n")
        fm.write("\n")

        # ── 改善/退化汇总 ──
        if improved:
            fm.write(f"**改善的用例 ({len(improved)} 条)**: "
                     + ", ".join(f"{c['case_id']}(+{c['overall_delta']:.1%})" for c in improved) + "\n")
        if degraded:
            fm.write(f"**退化的用例 ({len(degraded)} 条)**: "
                     + ", ".join(f"{c['case_id']}({c['overall_delta']:.1%})" for c in degraded) + "\n")
        if unchanged:
            fm.write(f"**无变化的用例 ({len(unchanged)} 条)**: "
                     + ", ".join(c["case_id"] for c in unchanged) + "\n")
        fm.write("\n")

        # ── Agent 中间过程（仅展示有记忆轮）──
        from .reporter import _render_agent_intermediate_steps
        lines_proxy: list[str] = []
        _render_agent_intermediate_steps(lines_proxy, memory_report)
        fm.write("\n".join(lines_proxy))
        fm.write("\n")

    return json_path, md_path


def _print_summary(report, json_path: str, md_path: str) -> None:
    """打印评测摘要。"""
    print(f"通过: {report.passed_cases}/{report.total_cases} ({report.overall_pass_rate:.1%})")
    print(f"平均分: {report.average_score:.2%}")
    print(f"平均延迟: {report.average_latency_ms:.0f}ms")
    print(f"平均准备耗时: {report.average_prep_ms:.0f}ms")
    if report.average_ttfb_ms is not None:
        print(f"平均 TTFB: {report.average_ttfb_ms:.0f}ms")
    print(f"平均工具调用: {report.average_tool_calls:.1f}")
    print(f"平均 Turns: {report.average_turns:.1f}")
    print(f"平均 Token: {report.average_tokens:.0f}")
    print(f"平均输入 Token: {report.average_input_tokens:.0f}")
    print(f"平均输出 Token: {report.average_output_tokens:.0f}")
    if json_path:
        print(f"\nJSON 报告: {json_path}")
    if md_path:
        print(f"Markdown 报告: {md_path}")


def _print_hdc_aggregate_summary(report) -> None:
    """打印 HDC 注入聚合摘要（遍历 case_results 汇总 hdc_verification 数据）。"""
    total = len(report.case_results)
    if total == 0:
        return

    injected_count = sum(1 for c in report.case_results if c.hdc_verification and c.hdc_verification.injected)
    correct_table_count = sum(1 for c in report.case_results if c.hdc_verification and c.hdc_verification.correct_table_in_context)
    agent_correct_table_count = sum(1 for c in report.case_results if c.hdc_verification and c.hdc_verification.agent_used_correct_table)
    hallucination_count = sum(1 for c in report.case_results if c.hdc_verification and c.hdc_verification.is_hallucination)
    total_chars = sum(c.hdc_verification.context_chars for c in report.case_results if c.hdc_verification)
    avg_chars = total_chars / injected_count if injected_count > 0 else 0

    print(f"\n{'─'*50}")
    print("HDC 注入聚合摘要")
    print(f"{'─'*50}")
    print(f"注入成功: {injected_count}/{total} ({injected_count/total:.0%})")
    print(f"正确表在上下文中: {correct_table_count}/{injected_count}" if injected_count > 0 else f"正确表在上下文中: 0/0")
    print(f"Agent 使用正确表: {agent_correct_table_count}/{injected_count}" if injected_count > 0 else f"Agent 使用正确表: 0/0")
    print(f"幻觉表名: {hallucination_count}/{injected_count}" if injected_count > 0 else f"幻觉表名: 0/0")
    print(f"平均上下文字符数: {avg_chars:.0f}")
    print(f"{'─'*50}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SDK-DBAgent Agent 性能评测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ---- run ----
    run_parser = subparsers.add_parser("run", help="运行评测")
    run_parser.add_argument(
        "--ids", nargs="*", default=None,
        help="指定用例 ID（如 TC-001 TC-005）",
    )
    run_parser.add_argument(
        "--difficulty", choices=["Easy", "Medium", "Hard"], default=None,
        help="按难度筛选",
    )
    run_parser.add_argument(
        "--category", type=str, default=None,
        help="按类别筛选",
    )
    run_parser.add_argument(
        "--schema-id", type=int, default=65938636,
        help="测试数据库 schemaId（默认 65938636 = dw_onedba）",
    )
    run_parser.add_argument(
        "--test-file", type=str, default=None,
        help="测试用例 Markdown 文件路径（默认 tests/docs/test_cases_onedba_evaluation.md）",
    )
    run_parser.add_argument(
        "--db-name", type=str, default=None,
        help="测试数据库名（默认 dw_onedba，对于 CS-* 用例应设为 dw_onedba_cs）",
    )
    run_parser.add_argument(
        "--timeout", type=float, default=120.0,
        help="单条用例超时（秒，默认 120）",
    )
    run_parser.add_argument(
        "--concurrency", type=int, default=1,
        help="并发数（默认 1=顺序执行）",
    )
    run_parser.add_argument(
        "--repeat", type=int, default=1,
        help="每条用例重复执行次数（默认 1，取平均以消除 LLM 随机性）",
    )
    run_parser.add_argument(
        "--no-llm-judge", action="store_true",
        help="跳过 Tier 3 LLM 评判（仅用结构匹配 + 结果对比）",
    )
    run_parser.add_argument(
        "--no-quality-judge", action="store_true",
        help="跳过回答质量评判",
    )
    run_parser.add_argument(
        "--keep-langfuse", action="store_true",
        help="保留 Langfuse trace（默认禁用，避免评测数据污染生产 trace）",
    )
    run_parser.add_argument(
        "--llm-model", type=str, default=None,
        help="指定评测使用的 LLM 模型（覆盖 .env 中的 llm_model，如 deepseek-v4-pro）",
    )
    run_parser.add_argument(
        "--baseline", type=str, default=None,
        help="基线 JSON 文件路径（用于对比）",
    )
    run_parser.add_argument(
        "--with-hdc", action="store_true",
        help="启用 HDC 数据底座检索（向 Agent 注入表结构知识）",
    )
    run_parser.add_argument(
        "--compare-hdc", action="store_true",
        help="HDC 对比模式：自动跑两轮（无 HDC 基线 + 有 HDC），生成对比报告。与 --with-hdc 互斥",
    )
    run_parser.add_argument(
        "--compare-sql-memory", action="store_true",
        help="SQL 记忆对比模式：baseline → 孪生测例填充记忆 → 有记忆重跑，生成对比报告",
    )
    run_parser.add_argument(
        "--twin-cases", type=str, default="tests/docs/sql_memory_twin_cases.md",
        help="孪生测例文件路径（默认 tests/docs/sql_memory_twin_cases.md）",
    )
    run_parser.add_argument(
        "--skip-seed", action="store_true",
        help="跳过 Phase 2（填充记忆库），直接使用已有的 SQL 记忆记录",
    )
    run_parser.add_argument(
        "--skip-baseline", action="store_true",
        help="跳过基线评测，直接从已有基线报告加载数据（需配合 --baseline 指定基线 JSON）",
    )
    run_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="详细日志模式：输出 Agent 中间过程（工具调用、SQL 生成、思考过程）",
    )
    run_parser.add_argument(
        "--verbose-hdc", action="store_true",
        help="详细 HDC 日志模式：输出每个用例的 HDC 注入状态（字符数、正确表是否在上下文中）",
    )
    run_parser.add_argument(
        "--hdc-gen-tokens", type=int, default=None,
        help="HDC 离线生成消耗的 token 数（用于报告中展示总成本，不传则不展示）",
    )
    run_parser.add_argument(
        "--hdc-tables", type=str, default=None,
        help="限定 HDC 知识库使用的表名白名单（逗号分隔，如 order_record,account）。仅保留匹配的表上下文，用于测试知识库缺失场景",
    )
    run_parser.add_argument(
        "--hdc-namespace", type=str, default=None,
        help="HDC 知识库命名空间，用于隔离同一 (schema_id, database_name) 下的不同 HDC 变体（如 incomplete/complete/overcomplete）",
    )
    run_parser.add_argument(
        "--output-dir", type=str, default="tests/evaluation/output",
        help="输出目录（默认 tests/evaluation/output）",
    )
    run_parser.set_defaults(func=cmd_run)

    # ---- list ----
    list_parser = subparsers.add_parser("list", help="列出所有测试用例")
    list_parser.add_argument(
        "--difficulty", choices=["Easy", "Medium", "Hard"], default=None,
        help="按难度筛选",
    )
    list_parser.add_argument(
        "--category", type=str, default=None,
        help="按类别筛选",
    )
    list_parser.add_argument(
        "--test-file", type=str, default=None,
        help="测试用例 Markdown 文件路径",
    )
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    print("SDK-DBAgent Agent 性能评测工具") 
    if (sys.executable == '/Users/admin/miniconda3/envs/DBR/bin/python'):
        main()
    else:
        print(f"当前 Python 运行环境: {sys.executable}")
        print("请使用 '/Users/admin/miniconda3/envs/DBR/bin/python' 提供的 Python 运行环境执行此脚本")
        sys.exit(1)