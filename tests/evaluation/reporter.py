"""
报告生成器 — JSON 和 Markdown 格式
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

from .models import EvaluationReport, CaseResult


def generate_report(
    report: EvaluationReport,
    output_dir: str = "tests/evaluation/output",
    baseline_path: str | None = None,
) -> tuple[str, str]:
    """
    生成 JSON 和 Markdown 报告。

    Args:
        report: 评测报告
        output_dir: 输出目录
        baseline_path: 基线 JSON 路径（用于对比）

    Returns:
        (json_path, markdown_path)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = str(output_path / f"evaluation_report_{timestamp}.json")
    md_path = str(output_path / f"evaluation_report_{timestamp}.md")

    # 基线对比
    if baseline_path:
        baseline = _load_baseline(baseline_path)
        if baseline:
            report.baseline_comparison = _compute_baseline_diff(report, baseline)

    # 写入 JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, ensure_ascii=False, indent=2, default=str)

    # 写入 Markdown
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_markdown(report))

    return json_path, md_path


def _load_baseline(path: str) -> dict[str, Any] | None:
    """加载基线报告"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _compute_baseline_diff(
    current: EvaluationReport,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """计算与基线的差异"""
    b_total = baseline.get("total_cases", 0)
    b_passed = baseline.get("passed_cases", 0)
    b_pass_rate = baseline.get("overall_pass_rate", 0.0)
    b_avg_score = baseline.get("average_score", 0.0)
    b_avg_latency = baseline.get("average_latency_ms", 0.0)
    b_avg_tools = baseline.get("average_tool_calls", 0.0)
    b_avg_turns = baseline.get("average_turns", 0.0)
    b_avg_tokens = baseline.get("average_tokens", 0.0)

    diff_pass_rate = current.overall_pass_rate - b_pass_rate
    diff_avg_score = current.average_score - b_avg_score
    diff_latency = current.average_latency_ms - b_avg_latency
    diff_tools = current.average_tool_calls - b_avg_tools
    diff_turns = current.average_turns - b_avg_turns
    diff_tokens = current.average_tokens - b_avg_tokens

    return {
        "baseline": {
            "total_cases": b_total,
            "passed_cases": b_passed,
            "pass_rate": b_pass_rate,
            "avg_score": b_avg_score,
            "avg_latency_ms": b_avg_latency,
            "avg_tool_calls": b_avg_tools,
            "avg_turns": b_avg_turns,
            "avg_tokens": b_avg_tokens,
        },
        "diff": {
            "pass_rate": round(diff_pass_rate, 4),
            "avg_score": round(diff_avg_score, 4),
            "avg_latency_ms": round(diff_latency, 1),
            "avg_tool_calls": round(diff_tools, 2),
            "avg_turns": round(diff_turns, 2),
            "avg_tokens": round(diff_tokens, 1),
        },
    }


def _render_markdown(report: EvaluationReport) -> str:
    """生成 Markdown 报告"""
    lines: list[str] = []

    lines.append("# Agent 性能评测报告")
    lines.append("")
    lines.append(f"**生成时间**: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**测试数据库**: schemaId={report.schema_id}")
    lines.append(f"**LLM 模型**: {report.llm_model}")
    lines.append(f"**LLM Base URL**: {report.llm_base_url}")
    lines.append("")

    # 总览
    lines.append("## 📊 总览")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 总用例数 | {report.total_cases} |")
    lines.append(f"| 通过 | {report.passed_cases} |")
    lines.append(f"| 失败 | {report.failed_cases} |")
    lines.append(f"| 错误 | {report.error_cases} |")
    lines.append(f"| 通过率 | {report.overall_pass_rate:.1%} |")
    lines.append(f"| 平均分 | {report.average_score:.2%} |")
    lines.append(f"| 平均延迟 | {report.average_latency_ms:.0f}ms |")
    lines.append(f"| 平均工具调用 | {report.average_tool_calls:.1f} |")
    lines.append(f"| 平均 Turns | {report.average_turns:.1f} |")
    lines.append(f"| 平均 Token | {report.average_tokens:.0f} |")
    if report.std_tool_calls > 0 or report.std_tokens > 0:
        lines.append(f"| 工具调用波动 (σ) | ±{report.std_tool_calls:.1f} |")
        lines.append(f"| Token 波动 (σ) | ±{report.std_tokens:.0f} |")
        lines.append(f"| 延迟波动 (σ) | ±{report.std_latency_ms:.0f}ms |")
        lines.append(f"| Turns 波动 (σ) | ±{report.std_turns:.1f} |")
    lines.append("")

    # 维度平均分
    lines.append("## 📐 维度平均分")
    lines.append("")
    dims = report.dimension_averages
    lines.append(f"| 维度 | 权重 | 平均分 |")
    lines.append(f"|------|------|--------|")
    lines.append(f"| SQL 语法正确 | 10% | {dims.sql_syntax:.2%} |")
    lines.append(f"| 表/列引用正确 | 10% | {dims.table_column:.2%} |")
    lines.append(f"| 过滤条件正确 | 10% | {dims.filter_condition:.2%} |")
    lines.append(f"| 结果数据正确 | 60% | {dims.result_data:.2%} |")
    lines.append(f"| SQL 规范 | 10% | {dims.sql_standard:.2%} |")
    lines.append("")

    # 按难度分布
    lines.append("## 📋 按难度分布")
    lines.append("")
    by_difficulty: dict[str, list[CaseResult]] = {}
    for cr in report.case_results:
        diff = cr.test_case.difficulty.value
        by_difficulty.setdefault(diff, []).append(cr)

    lines.append(f"| 难度 | 用例数 | 通过 | 失败 | 通过率 | 平均分 | 平均延迟 | 平均工具调用 |")
    lines.append(f"|------|--------|------|------|--------|--------|----------|-------------|")
    for diff in ["Easy", "Medium", "Hard"]:
        cases = by_difficulty.get(diff, [])
        if not cases:
            continue
        passed = sum(1 for c in cases if c.passed)
        failed = len(cases) - passed
        pass_rate = passed / len(cases) if cases else 0
        avg_score = sum(c.overall_score for c in cases) / len(cases) if cases else 0
        avg_latency = sum(c.duration_ms for c in cases) / len(cases) if cases else 0
        avg_tools = sum(
            c.efficiency.tool_call_count if c.efficiency else 0 for c in cases
        ) / len(cases) if cases else 0
        lines.append(
            f"| {diff} | {len(cases)} | {passed} | {failed} | "
            f"{pass_rate:.1%} | {avg_score:.2%} | {avg_latency:.0f}ms | {avg_tools:.1f} |"
        )
    lines.append("")

    # 用例详情
    lines.append("## 📝 用例详情")
    lines.append("")
    # 如果有重复执行，显示 std
    has_repeat = any(cr.repeat_count > 1 for cr in report.case_results)
    if has_repeat:
        lines.append(
            f"| 用例 | 难度 | 类别 | 通过 | 总分 | SQL | 工具调用 | Token | 延迟 |"
        )
        lines.append(
            f"|------|------|------|------|------|-----|----------|-------|------|"
        )
    else:
        lines.append(
            f"| 用例 | 难度 | 类别 | 通过 | 总分 | SQL | 质量 | 效率 | 延迟 | 工具调用 |"
        )
        lines.append(
            f"|------|------|------|------|------|-----|------|------|------|---------|"
        )
    for cr in report.case_results:
        sql_score = cr.sql_judge.score if cr.sql_judge else 0.0
        quality_score = cr.quality_judge.score if cr.quality_judge else 0.0
        eff_score = cr.efficiency.score if cr.efficiency else 0.0
        eff_tools = cr.efficiency.tool_call_count if cr.efficiency else 0
        eff_tokens = cr.efficiency.total_tokens if cr.efficiency else 0
        status = "✅" if cr.passed else ("❌" if cr.error is None else "⚠️")
        if has_repeat:
            tools_str = f"{eff_tools}±{cr.std_tool_calls:.0f}" if cr.repeat_count > 1 else str(eff_tools)
            tokens_str = f"{eff_tokens}±{cr.std_tokens:.0f}" if cr.repeat_count > 1 else str(eff_tokens)
            latency_str = f"{cr.duration_ms}±{cr.std_latency_ms:.0f}ms" if cr.repeat_count > 1 else f"{cr.duration_ms}ms"
            lines.append(
                f"| {cr.test_case.case_id} | {cr.test_case.difficulty.value} | "
                f"{cr.test_case.category} | {status} | {cr.overall_score:.2%} | "
                f"{sql_score:.2%} | {tools_str} | {tokens_str} | {latency_str} |"
            )
        else:
            lines.append(
                f"| {cr.test_case.case_id} | {cr.test_case.difficulty.value} | "
                f"{cr.test_case.category} | {status} | {cr.overall_score:.2%} | "
                f"{sql_score:.2%} | {quality_score:.2%} | {eff_score:.2%} | "
                f"{cr.duration_ms}ms | {eff_tools} |"
            )
    lines.append("")

    # 失败/错误用例详情
    failed = [c for c in report.case_results if not c.passed]
    if failed:
        lines.append("## ❌ 失败/错误用例详情")
        lines.append("")
        for cr in failed:
            lines.append(f"### {cr.test_case.case_id} — {cr.test_case.question[:50]}...")
            lines.append("")
            if cr.error:
                lines.append(f"**错误**: {cr.error}")
                lines.append("")
            else:
                lines.append(f"**总分**: {cr.overall_score:.2%}")
                lines.append(f"**SQL 评分**: {cr.sql_judge.score:.2%}" if cr.sql_judge else "")
                lines.append(f"**差异**: {cr.sql_judge.diff_summary}" if cr.sql_judge and cr.sql_judge.diff_summary else "")
                if cr.sql_judge and cr.sql_judge.generated_sql:
                    lines.append(f"**生成 SQL**: `{cr.sql_judge.generated_sql}`")
                if cr.sql_judge and cr.sql_judge.reference_sql:
                    lines.append(f"**参考 SQL**: `{cr.sql_judge.reference_sql}`")
                if cr.sql_judge and cr.sql_judge.llm_judge_explanation:
                    lines.append(f"**LLM 评判**: {cr.sql_judge.llm_judge_explanation}")
                lines.append("")

    # 稳定性分析（重复执行时）
    if has_repeat:
        lines.append("## 🔬 稳定性分析")
        lines.append("")
        lines.append("标准差越小表示 Agent 对该用例的回答越稳定。")
        lines.append("")
        lines.append(f"| 用例 | 工具调用 (σ) | Token (σ) | 延迟 (σ) | Turns (σ) | 各次工具调用 |")
        lines.append(f"|------|-------------|-----------|----------|-----------|-------------|")
        for cr in report.case_results:
            if cr.repeat_count <= 1:
                continue
            per_run_tools = " → ".join(
                str(r.tool_call_count) for r in cr.run_details
            )
            lines.append(
                f"| {cr.test_case.case_id} | ±{cr.std_tool_calls:.1f} | "
                f"±{cr.std_tokens:.0f} | ±{cr.std_latency_ms:.0f}ms | "
                f"±{cr.std_turns:.1f} | {per_run_tools} |"
            )
        lines.append("")

        # 找出最不稳定的用例
        most_unstable = max(
            [cr for cr in report.case_results if cr.repeat_count > 1],
            key=lambda c: c.std_tool_calls,
            default=None,
        )
        if most_unstable:
            lines.append(f"**最不稳定用例**: {most_unstable.test_case.case_id} "
                         f"(工具调用 σ=±{most_unstable.std_tool_calls:.1f})")
            lines.append(f"> {most_unstable.test_case.question}")
            lines.append("")

    # 基线对比
    if report.baseline_comparison:
        lines.append("## 📈 基线对比")
        lines.append("")
        bc = report.baseline_comparison
        baseline = bc.get("baseline", {})
        diff = bc.get("diff", {})

        lines.append(f"| 指标 | 基线 | 当前 | 变化 |")
        lines.append(f"|------|------|------|------|")
        lines.append(f"| 通过率 | {baseline.get('pass_rate', 0):.1%} | {report.overall_pass_rate:.1%} | {diff.get('pass_rate', 0):+.1%} |")
        lines.append(f"| 平均分 | {baseline.get('avg_score', 0):.2%} | {report.average_score:.2%} | {diff.get('avg_score', 0):+.2%} |")
        lines.append(f"| 平均延迟 | {baseline.get('avg_latency_ms', 0):.0f}ms | {report.average_latency_ms:.0f}ms | {diff.get('avg_latency_ms', 0):+.0f}ms |")
        lines.append(f"| 平均工具调用 | {baseline.get('avg_tool_calls', 0):.1f} | {report.average_tool_calls:.1f} | {diff.get('avg_tool_calls', 0):+.1f} |")
        lines.append(f"| 平均 Turns | {baseline.get('avg_turns', 0):.1f} | {report.average_turns:.1f} | {diff.get('avg_turns', 0):+.1f} |")
        lines.append(f"| 平均 Token | {baseline.get('avg_tokens', 0):.0f} | {report.average_tokens:.0f} | {diff.get('avg_tokens', 0):+.0f} |")
        lines.append("")

    return "\n".join(lines)