"""
报告生成器 — JSON 和 Markdown 格式
"""

from __future__ import annotations

import json
import re
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
    b_avg_input_tokens = baseline.get("average_input_tokens", 0.0)
    b_avg_output_tokens = baseline.get("average_output_tokens", 0.0)

    diff_pass_rate = current.overall_pass_rate - b_pass_rate
    diff_avg_score = current.average_score - b_avg_score
    diff_latency = current.average_latency_ms - b_avg_latency
    diff_tools = current.average_tool_calls - b_avg_tools
    diff_turns = current.average_turns - b_avg_turns
    diff_tokens = current.average_tokens - b_avg_tokens
    diff_input_tokens = current.average_input_tokens - b_avg_input_tokens
    diff_output_tokens = current.average_output_tokens - b_avg_output_tokens

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
            "avg_input_tokens": b_avg_input_tokens,
            "avg_output_tokens": b_avg_output_tokens,
        },
        "diff": {
            "pass_rate": round(diff_pass_rate, 4),
            "avg_score": round(diff_avg_score, 4),
            "avg_latency_ms": round(diff_latency, 1),
            "avg_tool_calls": round(diff_tools, 2),
            "avg_turns": round(diff_turns, 2),
            "avg_tokens": round(diff_tokens, 1),
            "avg_input_tokens": round(diff_input_tokens, 1),
            "avg_output_tokens": round(diff_output_tokens, 1),
        },
    }


def _render_markdown(report: EvaluationReport) -> str:
    """生成 Markdown 报告"""
    lines: list[str] = []

    lines.append("# Agent 性能评测报告")
    lines.append("")
    lines.append(f"**生成时间**: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**LLM 模型**: {report.llm_model}")
    lines.append(f"**LLM Base URL**: {report.llm_base_url}")
    if report.total_duration_ms > 0:
        total_sec = report.total_duration_ms / 1000
        if total_sec >= 60:
            lines.append(f"**评测总耗时**: {total_sec/60:.1f} 分钟 ({report.total_duration_ms:,}ms)")
        else:
            lines.append(f"**评测总耗时**: {total_sec:.1f} 秒 ({report.total_duration_ms:,}ms)")
    lines.append("")

    # ── 运行配置 ──
    if report.run_config:
        rc = report.run_config
        lines.append("## ⚙️ 运行配置")
        lines.append("")
        lines.append("| 参数 | 值 |")
        lines.append("|------|----|")
        lines.append(f"| 数据库 | `{rc.db_name}` (schemaId={report.schema_id}) |")
        lines.append(f"| 重复次数 | {rc.repeat} |")
        lines.append(f"| 并发数 | {rc.concurrency} |")
        lines.append(f"| HDC 数据底座 | {'启用' if rc.hdc_enabled else '禁用'} |")
        if rc.hdc_enabled:
            if rc.hdc_tables:
                lines.append(f"| HDC 限定表 | `{', '.join(rc.hdc_tables)}` |")
            if rc.hdc_namespace:
                lines.append(f"| HDC 命名空间 | `{rc.hdc_namespace}` |")
        lines.append(f"| LLM 评判 | {'启用' if rc.use_llm_judge else '禁用'} |")
        lines.append(f"| 回答质量评判 | {'启用' if rc.use_quality_judge else '禁用'} |")
        if rc.cli_command:
            lines.append(f"| CLI 命令 | `{rc.cli_command}` |")
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
    lines.append(f"| 平均准备耗时 (prep) | {report.average_prep_ms:.0f}ms |")
    if report.average_ttfb_ms is not None:
        lines.append(f"| 平均 TTFB | {report.average_ttfb_ms:.0f}ms |")
    lines.append(f"| 平均工具调用 | {report.average_tool_calls:.1f} |")
    lines.append(f"| 平均 Turns | {report.average_turns:.1f} |")
    lines.append(f"| 平均 Token | {report.average_tokens:.0f} |")
    lines.append(f"| 平均输入 Token | {report.average_input_tokens:.0f} |")
    lines.append(f"| 平均输出 Token | {report.average_output_tokens:.0f} |")
    if report.std_tool_calls > 0 or report.std_tokens > 0:
        lines.append(f"| 工具调用波动 (σ) | ±{report.std_tool_calls:.1f} |")
        lines.append(f"| Token 波动 (σ) | ±{report.std_tokens:.0f} |")
        lines.append(f"| 输入 Token 波动 (σ) | ±{report.std_input_tokens:.0f} |")
        lines.append(f"| 输出 Token 波动 (σ) | ±{report.std_output_tokens:.0f} |")
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
            f"| 用例 | 难度 | 类别 | 通过 | 总分 | SQL | 工具调用 | Token(总) | 输入Token | 输出Token | 延迟 |"
        )
        lines.append(
            f"|------|------|------|------|------|-----|----------|----------|----------|---------|------|"
        )
    else:
        lines.append(
            f"| 用例 | 难度 | 类别 | 通过 | 总分 | SQL | 质量 | 效率 | 延迟 | 工具调用 | 输入/输出Token |"
        )
        lines.append(
            f"|------|------|------|------|------|-----|------|------|------|---------|----------------|"
        )
    for cr in report.case_results:
        sql_score = cr.sql_judge.score if cr.sql_judge else 0.0
        quality_score = cr.quality_judge.score if cr.quality_judge else 0.0
        eff_score = cr.efficiency.score if cr.efficiency else 0.0
        eff_tools = cr.efficiency.tool_call_count if cr.efficiency else 0
        eff_tokens = cr.efficiency.total_tokens if cr.efficiency else 0
        eff_input_tokens = cr.efficiency.input_tokens if cr.efficiency else 0
        eff_output_tokens = cr.efficiency.output_tokens if cr.efficiency else 0
        status = "✅" if cr.passed else ("❌" if cr.error is None else "⚠️")
        if has_repeat:
            tools_str = f"{eff_tools}±{cr.std_tool_calls:.0f}" if cr.repeat_count > 1 else str(eff_tools)
            tokens_str = f"{eff_tokens}±{cr.std_tokens:.0f}" if cr.repeat_count > 1 else str(eff_tokens)
            input_tokens_str = f"{eff_input_tokens}±{cr.std_input_tokens:.0f}" if cr.repeat_count > 1 else str(eff_input_tokens)
            output_tokens_str = f"{eff_output_tokens}±{cr.std_output_tokens:.0f}" if cr.repeat_count > 1 else str(eff_output_tokens)
            latency_str = f"{cr.duration_ms}±{cr.std_latency_ms:.0f}ms" if cr.repeat_count > 1 else f"{cr.duration_ms}ms"
            lines.append(
                f"| {cr.test_case.case_id} | {cr.test_case.difficulty.value} | "
                f"{cr.test_case.category} | {status} | {cr.overall_score:.2%} | "
                f"{sql_score:.2%} | {tools_str} | {tokens_str} | "
                f"{input_tokens_str} | {output_tokens_str} | {latency_str} |"
            )
        else:
            input_output_str = f"{eff_input_tokens}/{eff_output_tokens}"
            lines.append(
                f"| {cr.test_case.case_id} | {cr.test_case.difficulty.value} | "
                f"{cr.test_case.category} | {status} | {cr.overall_score:.2%} | "
                f"{sql_score:.2%} | {quality_score:.2%} | {eff_score:.2%} | "
                f"{cr.duration_ms}ms | {eff_tools} | {input_output_str} |"
            )
    lines.append("")

    # ── Agent 中间过程（每次 LLM 调用 + 工具调用详情）──
    _render_agent_intermediate_steps(lines, report)

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
        lines.append(f"| 用例 | 工具调用 (σ) | Token (σ) | 输入Token (σ) | 输出Token (σ) | 延迟 (σ) | Turns (σ) | 各次工具调用 |")
        lines.append(f"|------|-------------|-----------|--------------|--------------|----------|-----------|-------------|")
        for cr in report.case_results:
            if cr.repeat_count <= 1:
                continue
            per_run_tools = " → ".join(
                str(r.tool_call_count) for r in cr.run_details
            )
            lines.append(
                f"| {cr.test_case.case_id} | ±{cr.std_tool_calls:.1f} | "
                f"±{cr.std_tokens:.0f} | ±{cr.std_input_tokens:.0f} | "
                f"±{cr.std_output_tokens:.0f} | ±{cr.std_latency_ms:.0f}ms | "
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
        lines.append(f"| 平均输入 Token | {baseline.get('avg_input_tokens', 0):.0f} | {report.average_input_tokens:.0f} | {diff.get('avg_input_tokens', 0):+.0f} |")
        lines.append(f"| 平均输出 Token | {baseline.get('avg_output_tokens', 0):.0f} | {report.average_output_tokens:.0f} | {diff.get('avg_output_tokens', 0):+.0f} |")
        lines.append("")

    return "\n".join(lines)


def _render_agent_intermediate_steps(lines: list[str], report: EvaluationReport) -> None:
    """渲染 Agent 中间过程：每个用例的 LLM 调用记录和工具调用详情（折叠区块）。"""
    lines.append("## 🤖 Agent 中间过程")
    lines.append("")

    for cr in report.case_results:
        has_llm = bool(cr.llm_call_records)
        has_tools = bool(cr.tool_call_records)
        if not has_llm and not has_tools:
            continue

        status = "✅" if cr.passed else ("⚠️" if cr.error else "❌")
        lines.append(f"### {cr.test_case.case_id} {status} — {cr.test_case.question[:60]}")
        lines.append("")

        # ── LLM 调用记录 ──
        if has_llm:
            lines.append("<details>")
            lines.append(f"<summary>🧠 LLM 调用记录 ({len(cr.llm_call_records)} 轮)</summary>")
            lines.append("")
            for lc in cr.llm_call_records:
                lines.append(f"**第 {lc.iteration + 1} 轮** [{lc.model}]")
                # 完整 input messages
                if lc.input_messages:
                    lines.append("")
                    lines.append("**输入 Messages**:")
                    for msg in lc.input_messages:
                        role = msg.get("role", "?")
                        content = str(msg.get("content", ""))
                        lines.append(f"- **{role}**: {content}")
                # 完整 output
                if lc.output_content:
                    lines.append("")
                    lines.append(f"**输出**:")
                    lines.append(f"```\n{lc.output_content}\n```")
                if lc.output_tool_calls:
                    tc_names = ", ".join(tc.get("name", "?") for tc in lc.output_tool_calls)
                    lines.append(f"- **请求工具**: {tc_names}")
                lines.append(f"- **最终响应**: {'是' if lc.is_final else '否'}")
                lines.append("")
            lines.append("</details>")
            lines.append("")

        # ── 工具调用详情 ──
        if has_tools:
            lines.append("<details>")
            lines.append(f"<summary>🔧 工具调用详情 ({len(cr.tool_call_records)} 次)</summary>")
            lines.append("")
            for i, tcr in enumerate(cr.tool_call_records):
                lines.append(f"**{i+1}. {tcr.tool}**")
                if tcr.args:
                    args_str = json.dumps(tcr.args, ensure_ascii=False, indent=2)
                    lines.append(f"**输入**:")
                    lines.append(f"```json\n{args_str}\n```")
                if tcr.result:
                    lines.append(f"**输出**: {tcr.result}")
                lines.append("")
            lines.append("</details>")
            lines.append("")


# ═══════════════════════════════════════════════════════════════
# HDC 对比报告
# ═══════════════════════════════════════════════════════════════


def generate_hdc_comparison_report(
    no_hdc: EvaluationReport,
    with_hdc: EvaluationReport,
    output_dir: str = "tests/evaluation/output",
) -> tuple[str, str]:
    """生成 HDC 对比报告（无 HDC vs 有 HDC）。

    Args:
        no_hdc: 无 HDC 基线的评测报告
        with_hdc: 有 HDC 的评测报告
        output_dir: 输出目录

    Returns:
        (json_path, markdown_path)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = str(output_path / f"hdc_comparison_{timestamp}.json")
    md_path = str(output_path / f"hdc_comparison_{timestamp}.md")

    # 计算逐维度差异
    diff = _compute_hdc_diff(no_hdc, with_hdc)

    # 写入 JSON
    comparison_data = {
        "generated_at": timestamp,
        "no_hdc": no_hdc.model_dump(mode="json"),
        "with_hdc": with_hdc.model_dump(mode="json"),
        "diff": diff,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, ensure_ascii=False, indent=2, default=str)

    # 写入 Markdown
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_hdc_comparison_md(no_hdc, with_hdc, diff))

    return json_path, md_path


def _compute_hdc_diff(
    no_hdc: EvaluationReport,
    with_hdc: EvaluationReport,
) -> dict:
    """计算两轮评测之间的逐维度差异。"""
    # 全局指标差异
    global_diff = {
        "pass_rate": round(with_hdc.overall_pass_rate - no_hdc.overall_pass_rate, 4),
        "avg_score": round(with_hdc.average_score - no_hdc.average_score, 4),
        "avg_latency_ms": round(with_hdc.average_latency_ms - no_hdc.average_latency_ms, 1),
        "avg_prep_ms": round(with_hdc.average_prep_ms - no_hdc.average_prep_ms, 1),
        "avg_ttfb_ms": round((with_hdc.average_ttfb_ms or 0) - (no_hdc.average_ttfb_ms or 0), 1) if with_hdc.average_ttfb_ms is not None and no_hdc.average_ttfb_ms is not None else None,
        "avg_tool_calls": round(with_hdc.average_tool_calls - no_hdc.average_tool_calls, 2),
        "avg_turns": round(with_hdc.average_turns - no_hdc.average_turns, 2),
        "avg_tokens": round(with_hdc.average_tokens - no_hdc.average_tokens, 1),
        "avg_input_tokens": round(with_hdc.average_input_tokens - no_hdc.average_input_tokens, 1),
        "avg_output_tokens": round(with_hdc.average_output_tokens - no_hdc.average_output_tokens, 1),
        "passed_cases": with_hdc.passed_cases - no_hdc.passed_cases,
        "total_duration_ms": with_hdc.total_duration_ms - no_hdc.total_duration_ms,  # 总耗时变化
    }

    # 维度评分差异
    dim_diff = {}
    dim_labels = ["sql_syntax", "table_column", "filter_condition", "result_data", "sql_standard"]
    for label in dim_labels:
        no_val = getattr(no_hdc.dimension_averages, label, 0.0)
        with_val = getattr(with_hdc.dimension_averages, label, 0.0)
        dim_diff[label] = round(with_val - no_val, 4)

    # 按难度分组差异
    by_difficulty: dict[str, dict] = {}
    for diff_level in ["Easy", "Medium", "Hard"]:
        no_cases = [c for c in no_hdc.case_results if c.test_case.difficulty.value == diff_level]
        with_cases = [c for c in with_hdc.case_results if c.test_case.difficulty.value == diff_level]
        if no_cases and with_cases:
            no_pass = sum(1 for c in no_cases if c.passed)
            with_pass = sum(1 for c in with_cases if c.passed)
            no_scores = [c.overall_score for c in no_cases]
            with_scores = [c.overall_score for c in with_cases]
            no_avg = sum(no_scores) / len(no_scores) if no_scores else 0
            with_avg = sum(with_scores) / len(with_scores) if with_scores else 0
            by_difficulty[diff_level] = {
                "pass_rate_diff": round(with_pass / len(with_cases) - no_pass / len(no_cases), 4),
                "avg_score_diff": round(with_avg - no_avg, 4),
                "case_count": len(no_cases),
            }

    # 每条用例的差异
    per_case_diff: list[dict] = []
    no_by_id = {c.test_case.case_id: c for c in no_hdc.case_results}
    with_by_id = {c.test_case.case_id: c for c in with_hdc.case_results}

    for case_id in sorted(no_by_id.keys()):
        no_c = no_by_id[case_id]
        with_c = with_by_id.get(case_id)
        if not with_c:
            continue

        no_tools = no_c.efficiency.tool_call_count if no_c.efficiency else 0
        with_tools = with_c.efficiency.tool_call_count if with_c.efficiency else 0
        no_tokens = no_c.efficiency.total_tokens if no_c.efficiency else 0
        with_tokens = with_c.efficiency.total_tokens if with_c.efficiency else 0
        no_input_tokens = no_c.efficiency.input_tokens if no_c.efficiency else 0
        with_input_tokens = with_c.efficiency.input_tokens if with_c.efficiency else 0
        no_output_tokens = no_c.efficiency.output_tokens if no_c.efficiency else 0
        with_output_tokens = with_c.efficiency.output_tokens if with_c.efficiency else 0

        per_case_diff.append({
            "case_id": case_id,
            "difficulty": no_c.test_case.difficulty.value,
            "category": no_c.test_case.category,
            "no_hdc_passed": no_c.passed,
            "with_hdc_passed": with_c.passed,
            "no_hdc_score": no_c.overall_score,
            "with_hdc_score": with_c.overall_score,
            "score_diff": round(with_c.overall_score - no_c.overall_score, 4),
            "tool_call_diff": with_tools - no_tools,
            "token_diff": with_tokens - no_tokens,
            "input_token_diff": with_input_tokens - no_input_tokens,
            "output_token_diff": with_output_tokens - no_output_tokens,
            "latency_diff_ms": with_c.duration_ms - no_c.duration_ms,
        })

    return {
        "global": global_diff,
        "dimensions": dim_diff,
        "by_difficulty": by_difficulty,
        "per_case": per_case_diff,
        # HDC 聚合指标：首表命中率和幻觉率（由 _compute_hdc_diff 计算，确保 JSON 与 Markdown 一致）
        "first_table_hit_rate": _compute_hdc_aggregates(with_hdc)["first_table_hit_rate"],
        "hallucination_rate": _compute_hdc_aggregates(with_hdc)["hallucination_rate"],
    }


def _compute_hdc_aggregates(report: EvaluationReport) -> dict[str, float | None]:
    """计算 HDC 聚合指标：首表命中率和幻觉率。

    由 _compute_hdc_diff() 调用，计算后存入 diff 字典；
    _render_hdc_audit() 从 diff 字典读取，确保 JSON 和 Markdown 报告中指标数值严格一致。
    """
    first_table_hits = 0
    first_table_total = 0
    hallucination_count = 0
    hallucination_total = 0

    with_by_id = {c.test_case.case_id: c for c in report.case_results}

    for case_id in sorted(with_by_id.keys()):
        cr = with_by_id[case_id]
        if not cr.run_details:
            continue

        # 首表命中率：所有 run 都必须命中才算命中 (strict match across all runs)
        ref_table = _extract_table_from_sql(cr.test_case.reference_sql)
        if ref_table:
            all_runs_hit = True
            any_run_has_table = False
            for rd in cr.run_details:
                if rd.first_table_used:
                    any_run_has_table = True
                    if rd.first_table_used.lower() != ref_table.lower():
                        all_runs_hit = False
                        break
            if any_run_has_table:
                first_table_total += 1
                if all_runs_hit:
                    first_table_hits += 1

        # 幻觉率：基于聚合后的 HdcVerificationData（已由 runner 做 OR/多数/保守 聚合）
        if cr.hdc_verification:
            hv = cr.hdc_verification
            hallucination_total += 1
            if hv.is_hallucination:
                hallucination_count += 1

    first_table_hit_rate = first_table_hits / first_table_total if first_table_total > 0 else None
    hallucination_rate = hallucination_count / hallucination_total if hallucination_total > 0 else None

    return {
        "first_table_hit_rate": first_table_hit_rate,
        "hallucination_rate": hallucination_rate,
    }

def _extract_table_from_sql(sql: str) -> str:
    """Extract the first table name from a SQL FROM clause."""
    if not sql:
        return ""
    # Match FROM table_name (possibly with backticks or schema prefix)
    match = re.search(r'\bFROM\s+`?(\w+)`?', sql, re.IGNORECASE)
    if match:
        return match.group(1)
    # Try JOIN pattern
    match = re.search(r'\bJOIN\s+`?(\w+)`?', sql, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _compute_first_table_correct(
    case_id: str,
    no_case: CaseResult | None,
    with_case: CaseResult | None,
) -> str:
    """Determine if the first table used was correct for both baseline and HDC runs."""
    # Extract reference table from reference_sql
    ref_table = ""
    if with_case and with_case.test_case.reference_sql:
        ref_table = _extract_table_from_sql(with_case.test_case.reference_sql)
    elif no_case and no_case.test_case.reference_sql:
        ref_table = _extract_table_from_sql(no_case.test_case.reference_sql)

    if not ref_table:
        return "N/A"

    parts = []
    # No-HDC first table correctness
    if no_case and no_case.run_details:
        first_table = no_case.run_details[0].first_table_used
        if first_table:
            ok = first_table.lower() == ref_table.lower()
            parts.append("\u2705" if ok else "\u274c")
        else:
            parts.append("N/A")
    else:
        parts.append("N/A")

    # With-HDC first table correctness
    if with_case and with_case.run_details:
        first_table = with_case.run_details[0].first_table_used
        if first_table:
            ok = first_table.lower() == ref_table.lower()
            parts.append("\u2705" if ok else "\u274c")
        else:
            parts.append("N/A")
    else:
        parts.append("N/A")

    if len(parts) == 2:
        return f"{parts[0]} \u2192 {parts[1]}"
    return " / ".join(parts)


def _render_hdc_comparison_md(
    no_hdc: EvaluationReport,
    with_hdc: EvaluationReport,
    diff: dict,
) -> str:
    """渲染 HDC 对比 Markdown 报告。"""
    lines: list[str] = []

    lines.append("# HDC 数据底座对比评测报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**LLM 模型**: {no_hdc.llm_model}")
    lines.append(f"**用例数**: {no_hdc.total_cases}")
    # 总耗时展示
    if no_hdc.total_duration_ms > 0 or with_hdc.total_duration_ms > 0:
        no_dur = f"{no_hdc.total_duration_ms/1000:.0f}s" if no_hdc.total_duration_ms > 0 else "N/A"
        with_dur = f"{with_hdc.total_duration_ms/1000:.0f}s" if with_hdc.total_duration_ms > 0 else "N/A"
        lines.append(f"**评测总耗时**: 基线 {no_dur} | HDC {with_dur}")
    lines.append("")

    # ── 运行配置（从基线报告读取，两轮共用）──
    if no_hdc.run_config:
        rc = no_hdc.run_config
        lines.append("## ⚙️ 运行配置")
        lines.append("")
        lines.append("| 参数 | 值 |")
        lines.append("|------|----|")
        lines.append(f"| 数据库 | `{rc.db_name}` (schemaId={no_hdc.schema_id}) |")
        lines.append(f"| 重复次数 | {rc.repeat} |")
        lines.append(f"| 并发数 | {rc.concurrency} |")
        lines.append(f"| LLM 评判 | {'启用' if rc.use_llm_judge else '禁用'} |")
        lines.append(f"| 回答质量评判 | {'启用' if rc.use_quality_judge else '禁用'} |")
        if rc.hdc_tables:
            lines.append(f"| HDC 限定表 | `{', '.join(rc.hdc_tables)}` |")
        if rc.hdc_namespace:
            lines.append(f"| HDC 命名空间 | `{rc.hdc_namespace}` |")
        lines.append("")

    # 全局对比
    g = diff["global"]
    lines.append("## 📊 全局对比")
    lines.append("")
    lines.append("| 指标 | 无 HDC（基线） | 有 HDC | 变化 | 趋势 |")
    lines.append("|------|---------------|--------|------|------|")

    _add_metric_row(lines, "通过率", no_hdc.overall_pass_rate, with_hdc.overall_pass_rate, g["pass_rate"])
    _add_metric_row(lines, "平均分", no_hdc.average_score, with_hdc.average_score, g["avg_score"], is_pct=True)
    _add_metric_row(lines, "通过用例", no_hdc.passed_cases, with_hdc.passed_cases, g["passed_cases"], is_int=True)
    _add_metric_row(lines, "平均延迟", no_hdc.average_latency_ms, with_hdc.average_latency_ms, g["avg_latency_ms"], unit="ms", lower_is_better=True)
    _add_metric_row(lines, "评测总耗时", no_hdc.total_duration_ms, with_hdc.total_duration_ms, g["total_duration_ms"], unit="ms", lower_is_better=True)
    _add_metric_row(lines, "平均工具调用", no_hdc.average_tool_calls, with_hdc.average_tool_calls, g["avg_tool_calls"], lower_is_better=True)
    _add_metric_row(lines, "平均 Turns", no_hdc.average_turns, with_hdc.average_turns, g["avg_turns"], lower_is_better=True)
    _add_metric_row(lines, "平均 Token（运行时）", no_hdc.average_tokens, with_hdc.average_tokens, g["avg_tokens"], lower_is_better=True)
    _add_metric_row(lines, "平均输入 Token", no_hdc.average_input_tokens, with_hdc.average_input_tokens, g.get("avg_input_tokens", 0), lower_is_better=True)
    _add_metric_row(lines, "平均输出 Token", no_hdc.average_output_tokens, with_hdc.average_output_tokens, g.get("avg_output_tokens", 0), lower_is_better=True)
    # 如果传入了 HDC 离线生成 token 数，展示一行
    if with_hdc.hdc_generation_tokens is not None:
        gen_tokens = with_hdc.hdc_generation_tokens
        lines.append(f"| HDC 离线生成 Token | — | {gen_tokens:,} | —（一次性成本） | — |")
    lines.append("")

    # 维度对比
    d = diff["dimensions"]
    dim_weights = {"sql_syntax": "10%", "table_column": "10%", "filter_condition": "10%", "result_data": "60%", "sql_standard": "10%"}
    dim_labels_cn = {"sql_syntax": "SQL 语法正确", "table_column": "表/列引用正确", "filter_condition": "过滤条件正确", "result_data": "结果数据正确", "sql_standard": "SQL 规范"}

    lines.append("## 📐 维度评分对比")
    lines.append("")
    lines.append("| 维度 | 权重 | 无 HDC | 有 HDC | 变化 | 趋势 |")
    lines.append("|------|------|--------|--------|------|------|")

    for key in ["sql_syntax", "table_column", "filter_condition", "result_data", "sql_standard"]:
        no_val = getattr(no_hdc.dimension_averages, key, 0.0)
        with_val = getattr(with_hdc.dimension_averages, key, 0.0)
        change = d.get(key, 0.0)
        _add_metric_row(lines, dim_labels_cn[key], no_val, with_val, change, is_pct=True, weight=dim_weights[key])
    lines.append("")

    # 按难度对比
    bd = diff.get("by_difficulty", {})
    if bd:
        lines.append("## 📋 按难度对比")
        lines.append("")
        lines.append("| 难度 | 用例数 | 无 HDC 通过率 | 有 HDC 通过率 | 通过率变化 | 平均分变化 |")
        lines.append("|------|--------|-------------|-------------|-----------|-----------|")

        for diff_level in ["Easy", "Medium", "Hard"]:
            d_info = bd.get(diff_level)
            if not d_info:
                continue
            no_cases = [c for c in no_hdc.case_results if c.test_case.difficulty.value == diff_level]
            with_cases = [c for c in with_hdc.case_results if c.test_case.difficulty.value == diff_level]
            no_pass = sum(1 for c in no_cases if c.passed)
            with_pass = sum(1 for c in with_cases if c.passed)
            no_rate = no_pass / len(no_cases) if no_cases else 0
            with_rate = with_pass / len(with_cases) if with_cases else 0
            lines.append(
                f"| {diff_level} | {d_info['case_count']} | {no_rate:.1%} | {with_rate:.1%} | "
                f"{d_info['pass_rate_diff']:+.1%} | {d_info['avg_score_diff']:+.2%} |"
            )
        lines.append("")

    # 每条用例对比
    per_case = diff.get("per_case", [])
    if per_case:
        lines.append("## 📝 逐用例对比")
        lines.append("")
        lines.append("| 用例 | 难度 | 类别 | 无 HDC | 有 HDC | 分数变化 | 工具调用变化 | Token变化 | 输入Token变化 | 输出Token变化 | 首轮正确 |")
        lines.append("|------|------|------|--------|--------|----------|-------------|----------|-------------|-------------|---------|")

        for pc in per_case:
            no_status = "✅" if pc["no_hdc_passed"] else "❌"
            with_status = "✅" if pc["with_hdc_passed"] else "❌"
            tool_arrow = f"{pc['tool_call_diff']:+d}" if pc["tool_call_diff"] != 0 else "0"
            token_arrow = f"{pc['token_diff']:+d}" if pc["token_diff"] != 0 else "0"
            input_token_arrow = f"{pc.get('input_token_diff', 0):+d}" if pc.get("input_token_diff", 0) != 0 else "0"
            output_token_arrow = f"{pc.get('output_token_diff', 0):+d}" if pc.get("output_token_diff", 0) != 0 else "0"
            no_cr = no_by_id.get(pc['case_id'])
            with_cr = with_by_id.get(pc['case_id'])
            first_correct = _compute_first_table_correct(pc['case_id'], no_cr, with_cr)
            lines.append(
                f"| {pc['case_id']} | {pc['difficulty']} | {pc['category']} | "
                f"{no_status} {pc['no_hdc_score']:.2%} | {with_status} {pc['with_hdc_score']:.2%} | "
                f"{pc['score_diff']:+.2%} | {tool_arrow} | {token_arrow} | "
                f"{input_token_arrow} | {output_token_arrow} | {first_correct} |"
            )
        lines.append("")

        # 改善/退化的用例
        improved = [pc for pc in per_case if pc["score_diff"] > 0]
        degraded = [pc for pc in per_case if pc["score_diff"] < 0]
        unchanged = [pc for pc in per_case if pc["score_diff"] == 0]

        if improved:
            lines.append(f"**HDC 改善的用例 ({len(improved)} 条)**: " + ", ".join(f"{pc['case_id']}(+{pc['score_diff']:.0%})" for pc in improved))
        if degraded:
            lines.append(f"**HDC 退化的用例 ({len(degraded)} 条)**: " + ", ".join(f"{pc['case_id']}({pc['score_diff']:.0%})" for pc in degraded))
        if unchanged:
            lines.append(f"**无变化的用例 ({len(unchanged)} 条)**: " + ", ".join(pc["case_id"] for pc in unchanged))
        lines.append("")

    # 逐工具效率对比
    _render_per_tool_breakdown(lines, no_hdc, with_hdc)

    # HDC 正确性审计（传入 diff 以读取聚合指标，确保 JSON 和 Markdown 一致）
    _render_hdc_audit(lines, with_hdc, diff=diff)

    # 结论
    lines.append("## 🏁 结论")
    lines.append("")

    # 判断 HDC 的净效果
    score_delta = g["avg_score"]
    pass_delta = g["pass_rate"]
    latency_delta = g["avg_latency_ms"]
    tools_delta = g["avg_tool_calls"]

    conclusions: list[str] = []

    if score_delta > 0.01:
        conclusions.append(f"- **分数提升**: 平均分 +{score_delta:.2%}，HDC 有效提升了 SQL 生成质量")
    elif score_delta < -0.01:
        conclusions.append(f"- **分数下降**: 平均分 {score_delta:.2%}，HDC 可能引入了误导信息")
    else:
        conclusions.append(f"- **分数持平**: 平均分变化 {score_delta:+.2%}，HDC 对 SQL 质量影响不显著")

    if pass_delta > 0:
        conclusions.append(f"- **通过率提升**: +{pass_delta:.1%}（{g['passed_cases']:+d} 条用例）")
    elif pass_delta < 0:
        conclusions.append(f"- **通过率下降**: {pass_delta:.1%}（{g['passed_cases']:+d} 条用例）")

    if tools_delta < -0.5:
        conclusions.append(f"- **效率提升**: 平均工具调用减少 {abs(tools_delta):.1f} 次，HDC 帮助 Agent 更快定位目标表")
    elif tools_delta > 0.5:
        conclusions.append(f"- **效率下降**: 平均工具调用增加 +{tools_delta:.1f} 次")

    if abs(latency_delta) > 100:
        direction = "减少" if latency_delta < 0 else "增加"
        conclusions.append(f"- **延迟{direction}**: {abs(latency_delta):.0f}ms")

    for c in conclusions:
        lines.append(c)

    lines.append("")
    lines.append("> 💡 **解读**: HDC 数据底座通过向 Agent 注入数据库 Schema 知识（表名、字段含义、业务实体），")
    lines.append("> 减少了对 `list_tables` / `describe_table` 等探索性工具调用的依赖。")
    lines.append("> 正收益体现在更快定位目标表和更准确的列引用；负收益可能来自过时或错误的 HDC 知识。")
    if with_hdc.hdc_generation_tokens is not None:
        lines.append("> ")
        lines.append(f"> 💰 **成本说明**: HDC 离线生成消耗 {with_hdc.hdc_generation_tokens:,} tokens，属于一次性成本。")
        lines.append("> 随着查询次数增加，单次查询的 HDC 摊薄成本趋近于零。评估 HDC 净收益时需将运行时 token 节省与生成成本综合考量。")

    return "\n".join(lines)

def _render_per_tool_breakdown(
    lines: list[str],
    no_hdc: EvaluationReport,
    with_hdc: EvaluationReport,
) -> None:
    """Render per-tool efficiency comparison table (find_table, describe_table, query_database)."""
    tools = ["find_table", "describe_table", "query_database"]
    tool_labels = {
        "find_table": "find_table",
        "describe_table": "describe_table",
        "query_database": "query_database",
    }

    lines.append("## \U0001f527 工具调用效率对比")
    lines.append("")

    # Build a mapping by case_id for both reports
    no_by_id = {c.test_case.case_id: c for c in no_hdc.case_results}
    with_by_id = {c.test_case.case_id: c for c in with_hdc.case_results}

    # Per-case table
    lines.append("| 用例 | 工具 | 基线（无 HDC） | 有 HDC | 变化 | 趋势 |")
    lines.append("|------|------|---------------|--------|------|------|")

    tool_totals: dict[str, dict[str, float]] = {t: {"no": 0.0, "with": 0.0} for t in tools}
    case_count = 0

    for case_id in sorted(no_by_id.keys()):
        no_c = no_by_id[case_id]
        with_c = with_by_id.get(case_id)
        if not with_c:
            continue
        case_count += 1

        no_details = no_c.efficiency.tool_call_details if no_c.efficiency else {}
        with_details = with_c.efficiency.tool_call_details if with_c.efficiency else {}

        for tool in tools:
            no_val = no_details.get(tool, 0)
            with_val = with_details.get(tool, 0)
            change = with_val - no_val
            tool_totals[tool]["no"] += no_val
            tool_totals[tool]["with"] += with_val

            if change < 0:
                trend = "\U0001f4c8 改善"
            elif change > 0:
                trend = "\U0001f4c9 退化"
            else:
                trend = "\u27a1\ufe0f"

            lines.append(
                f"| {case_id} | {tool} | {no_val} | {with_val} | "
                f"{change:+d} | {trend} |"
            )

    # Summary row
    if case_count > 0:
        lines.append(f"| **平均** | **汇总** | | | | |")
        for tool in tools:
            no_avg = tool_totals[tool]["no"] / case_count
            with_avg = tool_totals[tool]["with"] / case_count
            avg_change = with_avg - no_avg
            if avg_change < 0:
                trend = "\U0001f4c8 改善"
            elif avg_change > 0:
                trend = "\U0001f4c9 退化"
            else:
                trend = "\u27a1\ufe0f"
            lines.append(
                f"| **平均** | {tool} | {no_avg:.1f} | {with_avg:.1f} | "
                f"{avg_change:+.1f} | {trend} |"
            )

    lines.append("")

    # First-round find_table call rate
    no_find_first = 0
    with_find_first = 0
    no_total = 0
    with_total = 0

    for case_id in sorted(no_by_id.keys()):
        no_c = no_by_id[case_id]
        with_c = with_by_id.get(case_id)
        if not with_c:
            continue

        if no_c.run_details:
            no_total += 1
            if any(rd.called_find_table_before_query for rd in no_c.run_details):
                no_find_first += 1

        if with_c.run_details:
            with_total += 1
            if any(rd.called_find_table_before_query for rd in with_c.run_details):
                with_find_first += 1

    if no_total > 0 or with_total > 0:
        no_rate = no_find_first / no_total if no_total > 0 else 0.0
        with_rate = with_find_first / with_total if with_total > 0 else 0.0
        lines.append(f"**首轮 find_table 调用率**: 基线 {no_rate:.1%} ({no_find_first}/{no_total}) "
                     f"\u2192 HDC {with_rate:.1%} ({with_find_first}/{with_total})")
        if with_rate < no_rate:
            lines.append("  \U0001f4c8 HDC 减少了首轮 find_table 调用")
        elif with_rate > no_rate:
            lines.append("  \U0001f4c9 HDC 增加了首轮 find_table 调用")
        else:
            lines.append("  \u27a1\ufe0f 首轮 find_table 调用率无变化")
        lines.append("")

def _render_hdc_audit(
    lines: list[str],
    with_hdc: EvaluationReport,
    diff: dict | None = None,
) -> None:
    """Render HDC correctness audit table."""
    lines.append("## \U0001f50d HDC 正确性审计")
    lines.append("")

    if not with_hdc.case_results:
        lines.append("_无 HDC 验证数据_")
        lines.append("")
        return

    lines.append("| 用例 | HDC 含正确表 | Agent 用正确表 | 幻觉 |")
    lines.append("|------|-------------|---------------|------|")

    total_cases = 0
    correct_in_context = 0
    agent_used_correct = 0
    hallucination_count = 0

    for cr in with_hdc.case_results:
        hv = cr.hdc_verification
        if hv is None:
            lines.append(f"| {cr.test_case.case_id} | N/A | N/A | N/A |")
            continue

        total_cases += 1
        ctx_ok = "\u2705" if hv.correct_table_in_context else "\u274c"
        agent_ok = "\u2705" if hv.agent_used_correct_table else "\u274c"
        hall = "\u26a0\ufe0f **是**" if hv.is_hallucination else "\u2705"

        if hv.correct_table_in_context:
            correct_in_context += 1
        if hv.agent_used_correct_table:
            agent_used_correct += 1
        if hv.is_hallucination:
            hallucination_count += 1

        lines.append(
            f"| {cr.test_case.case_id} | {ctx_ok} | {agent_ok} | {hall} |"
        )

    lines.append("")

    # Aggregate stats
    if total_cases > 0:
        lines.append(f"**聚合统计**:")
        lines.append(f"- HDC 上下文含正确表: {correct_in_context}/{total_cases} ({correct_in_context/total_cases:.1%})")
        lines.append(f"- Agent 采纳正确表: {agent_used_correct}/{total_cases} ({agent_used_correct/total_cases:.1%})")
        lines.append(f"- Agent 幻觉: {hallucination_count}/{total_cases} ({hallucination_count/total_cases:.1%})")
        lines.append("")

        # 从 diff 字典读取首表命中率和幻觉率聚合指标（确保 JSON 和 Markdown 一致）
        # diff 由调用方传入，此处仅渲染
        first_table_hit_rate = diff.get("first_table_hit_rate") if diff else None
        hallucination_rate = diff.get("hallucination_rate") if diff else None

        if first_table_hit_rate is not None:
            lines.append(f"- **首表命中率**: {first_table_hit_rate:.1%}")
        else:
            lines.append(f"- **首表命中率**: N/A")

        if hallucination_rate is not None:
            lines.append(f"- **幻觉率**: {hallucination_rate:.1%}")
        else:
            lines.append(f"- **幻觉率**: N/A")
        lines.append("")


def _add_metric_row(
    lines: list[str],
    label: str,
    baseline: float,
    current: float,
    change: float,
    is_pct: bool = False,
    is_int: bool = False,
    unit: str = "",
    lower_is_better: bool = False,
    weight: str = "",
) -> None:
    """向 Markdown 表格添加一行指标对比。"""
    if is_int:
        base_str = str(int(baseline))
        curr_str = str(int(current))
        change_str = f"{int(change):+d}"
    elif is_pct:
        base_str = f"{baseline:.2%}"
        curr_str = f"{current:.2%}"
        change_str = f"{change:+.2%}"
    else:
        base_str = f"{baseline:.1f}{unit}"
        curr_str = f"{current:.1f}{unit}"
        change_str = f"{change:+.1f}{unit}"

    # 趋势判断
    if abs(change) < 0.001:
        trend = "➡️"
    elif lower_is_better:
        trend = "📈 改善" if change < 0 else "📉 退化"
    else:
        trend = "📈 改善" if change > 0 else "📉 退化"

    if is_int and abs(change) < 0.5:
        trend = "➡️"
    if not is_int and not is_pct and abs(change) < 0.05:
        trend = "➡️"

    w = f" ({weight})" if weight else ""
    lines.append(f"| {label}{w} | {base_str} | {curr_str} | {change_str} | {trend} |")