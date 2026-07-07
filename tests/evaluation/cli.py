#!/usr/bin/env python3
"""
Agent 性能评测 CLI 工具

用法:
    python -m tests.evaluation.cli run                     # 运行全部用例
    python -m tests.evaluation.cli run --ids TC-001 TC-005 # 指定用例
    python -m tests.evaluation.cli run --difficulty Hard   # 按难度筛选
    python -m tests.evaluation.cli run --baseline output/baseline.json  # 基线对比
    python -m tests.evaluation.cli list                    # 列出所有用例
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .loader import load_test_cases, filter_test_cases
from .runner import run_evaluation
from .reporter import generate_report


def cmd_list(args: argparse.Namespace) -> None:
    """列出所有测试用例"""
    cases = load_test_cases()
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
    cases = load_test_cases()
    filtered = filter_test_cases(
        cases,
        ids=args.ids,
        difficulty=args.difficulty,
        category=args.category,
    )

    if not filtered:
        print("没有匹配的测试用例")
        return

    print(f"\n开始评测 {len(filtered)} 条用例...")
    if args.repeat > 1:
        print(f"（每条用例重复 {args.repeat} 次，取平均值）")
    if args.no_llm_judge:
        print("（已跳过 LLM 评判 Tier 3）")
    if args.no_quality_judge:
        print("（已跳过回答质量评判）")
    if args.keep_langfuse:
        print("（保留 Langfuse trace）")
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
        )

        # 生成报告
        json_path, md_path = generate_report(
            report,
            output_dir=args.output_dir,
            baseline_path=args.baseline,
        )

        print(f"\n{'='*60}")
        print(f"评测完成")
        print(f"{'='*60}")
        print(f"通过: {report.passed_cases}/{report.total_cases} ({report.overall_pass_rate:.1%})")
        print(f"平均分: {report.average_score:.2%}")
        print(f"平均延迟: {report.average_latency_ms:.0f}ms")
        print(f"平均工具调用: {report.average_tool_calls:.1f}")
        print(f"平均 Token: {report.average_tokens:.0f}")
        print(f"\nJSON 报告: {json_path}")
        print(f"Markdown 报告: {md_path}")

    asyncio.run(_run())


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
        help="测试数据库 schemaId（默认 65938636）",
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
        "--baseline", type=str, default=None,
        help="基线 JSON 文件路径（用于对比）",
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