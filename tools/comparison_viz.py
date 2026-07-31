#!/usr/bin/env python3
"""
对比实验可视化工具

读取两份 JSON 报告，生成一张以结论为中心的对比图 PNG。

用法:
    python tools/comparison_viz.py baseline.json fullstack.json
    python tools/comparison_viz.py baseline.json fullstack.json -o output.png --dpi 200

支持两种 JSON 格式:
    - EvaluationReport (evaluation_report_*.json)
    - SQL 记忆对比报告 (sql_memory_comparison_*.json)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

matplotlib.use("Agg")

BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"
AMBER = "#CC79A7"
INK = "#222222"
MUTED = "#666666"
GRID = "#DDDDDD"
PANEL = "#F7F7F7"
WHITE = "#FFFFFF"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["PingFang SC", "Heiti SC", "Hiragino Sans GB", "Arial", "Helvetica", "DejaVu Sans"],
    "axes.facecolor": WHITE,
    "figure.facecolor": WHITE,
    "axes.edgecolor": "#BDBDBD",
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "grid.color": GRID,
    "grid.alpha": 0.75,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "axes.unicode_minus": False,
    "savefig.dpi": 300,
})


def _detect_format(data: dict) -> str:
    if "baseline" in data and "memory" in data and "case_comparison" in data:
        return "sql_memory_comparison"
    if "case_results" in data and "dimension_averages" in data:
        return "evaluation_report"
    raise ValueError("无法识别的 JSON 格式，需要 EvaluationReport 或 SQL 记忆对比报告")


def load_data(baseline_path: str, fullstack_path: str) -> dict:
    with open(baseline_path) as f:
        b_raw = json.load(f)
    with open(fullstack_path) as f:
        f_raw = json.load(f)

    fmt_b = _detect_format(b_raw)
    fmt_f = _detect_format(f_raw)

    b = _from_sql_memory(b_raw, "baseline") if fmt_b == "sql_memory_comparison" else _from_eval_report(b_raw)
    f = _from_sql_memory(f_raw, "memory") if fmt_f == "sql_memory_comparison" else _from_eval_report(f_raw)

    b["run_details"] = _extract_run_details(b_raw) if fmt_b == "evaluation_report" else []
    f["run_details"] = _extract_run_details(f_raw) if fmt_f == "evaluation_report" else []

    return {"baseline": b, "fullstack": f}


def _from_eval_report(d: dict) -> dict:
    return {
        "pass_rate": d.get("overall_pass_rate", 0),
        "passed": f"{d.get('passed_cases', 0)}/{d.get('total_cases', 0)}",
        "avg_score": d.get("average_score", 0),
        "avg_latency_ms": d.get("average_latency_ms", 0),
        "avg_ttfb_ms": d.get("average_ttfb_ms") or 0,
        "avg_prep_ms": d.get("average_prep_ms", 0),
        "avg_tool_calls": d.get("average_tool_calls", 0),
        "avg_turns": d.get("average_turns", 0),
        "avg_tokens": d.get("average_tokens", 0),
        "avg_input_tokens": d.get("average_input_tokens", 0),
        "avg_output_tokens": d.get("average_output_tokens", 0),
        "std_latency_ms": d.get("std_latency_ms", 0),
        "std_tokens": d.get("std_tokens", 0),
        "dimensions": d.get("dimension_averages") or {},
        "cases": [
            {
                "case_id": c["test_case"]["case_id"],
                "difficulty": c["test_case"].get("difficulty", ""),
                "category": c["test_case"].get("category", ""),
                "passed": c.get("passed", False),
                "overall_score": c.get("overall_score", 0),
                "duration_ms": c.get("duration_ms", 0),
                "efficiency": c.get("efficiency") or {},
            }
            for c in (d.get("case_results") or [])
        ],
    }


def _from_sql_memory(d: dict, key: str) -> dict:
    s = d[key]
    prefix = "baseline" if key == "baseline" else "memory"
    dims = {}
    for dim_key, values in (d.get("dimension_comparison") or {}).items():
        if isinstance(values, dict):
            dims[dim_key] = values.get(prefix, values.get(key, 0))

    cases = []
    for c in d.get("case_comparison") or []:
        cases.append({
            "case_id": c.get("case_id", ""),
            "difficulty": c.get("difficulty", ""),
            "category": c.get("category", ""),
            "passed": c.get(f"{prefix}_passed", False),
            "overall_score": c.get(f"{prefix}_overall", c.get(f"{prefix}_sql_score", 0)),
            "duration_ms": c.get(f"{prefix}_latency", 0),
            "efficiency": {
                "tool_call_count": c.get(f"{prefix}_tools", 0),
                "total_tokens": c.get(f"{prefix}_tokens", 0),
                "input_tokens": c.get(f"{prefix}_input_tokens", 0),
                "output_tokens": c.get(f"{prefix}_output_tokens", 0),
            },
        })

    return {
        "pass_rate": s.get("pass_rate", 0),
        "passed": f"{s.get('passed', 0)}/{s.get('total', s.get('passed', 0) + s.get('failed', 0))}",
        "avg_score": s.get("avg_score", 0),
        "avg_latency_ms": s.get("avg_latency_ms", 0),
        "avg_ttfb_ms": s.get("avg_ttfb_ms") or 0,
        "avg_prep_ms": s.get("avg_prep_ms", 0),
        "avg_tool_calls": s.get("avg_tool_calls", 0),
        "avg_turns": s.get("avg_turns", 0),
        "avg_tokens": s.get("avg_tokens", 0),
        "avg_input_tokens": s.get("avg_input_tokens", 0),
        "avg_output_tokens": s.get("avg_output_tokens", 0),
        "std_latency_ms": s.get("std_latency_ms", 0),
        "std_tokens": s.get("std_tokens", 0),
        "dimensions": dims,
        "cases": cases,
    }


def _extract_run_details(d: dict) -> list[dict]:
    result = []
    for c in (d.get("case_results") or []):
        for i, rd in enumerate(c.get("run_details") or []):
            result.append({
                "case_id": c["test_case"]["case_id"],
                "duration_ms": rd.get("duration_ms", 0),
                "run_index": rd.get("run_index", i),
            })
    return result


def _sort_case_id(case_id: str) -> tuple[int, str]:
    try:
        return int(case_id.split("-")[1]), case_id
    except Exception:
        return 9999, case_id


def _pct_delta(new: float, old: float) -> float:
    return (new - old) / old * 100 if old else 0


def _fmt_num(value: float, unit: str = "", digits: int = 1) -> str:
    if unit == "%":
        return f"{value * 100:.{digits}f}%"
    if unit == "s":
        return f"{value / 1000:.{digits}f}s"
    if abs(value) >= 1000:
        return f"{value:,.0f}{unit}"
    return f"{value:.{digits}f}{unit}"


def _improved(metric: str, delta: float) -> bool:
    return delta >= 0 if metric in {"pass_rate", "avg_score"} else delta <= 0


def _style_panel(ax, title: str):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=16)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#BDBDBD")
    ax.spines["bottom"].set_color("#BDBDBD")
    ax.tick_params(labelsize=10, length=3.5, width=0.8, pad=6)
    ax.grid(axis="x", linestyle="-", linewidth=0.7)
    ax.grid(axis="y", visible=False)


def _no_data(ax, title: str, message: str):
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=12)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=10, color=MUTED, transform=ax.transAxes)


def draw_kpi_cards(ax, b: dict, f: dict):
    ax.set_axis_off()
    metrics = [
        ("通过率", "pass_rate", "%", True),
        ("平均分", "avg_score", "%", True),
        ("平均延迟", "avg_latency_ms", "s", False),
        ("Token", "avg_tokens", "", False),
        ("首字延迟", "avg_ttfb_ms", "s", False),
    ]

    score_delta = (f.get("avg_score", 0) - b.get("avg_score", 0)) * 100
    latency_delta = _pct_delta(f.get("avg_latency_ms", 0), b.get("avg_latency_ms", 0))
    token_delta = _pct_delta(f.get("avg_tokens", 0), b.get("avg_tokens", 0))
    ttfb_delta = _pct_delta(f.get("avg_ttfb_ms", 0), b.get("avg_ttfb_ms", 0))
    verdict = (
        f"HDC-SM方案通过率 {b.get('passed', '-')} -> {f.get('passed', '-')}，"
        f"平均分 {score_delta:+.1f}pp，平均延迟 {latency_delta:+.1f}%，Token {token_delta:+.1f}%。"
    )

    ax.text(0.01, 0.96, "实验结论", fontsize=17, fontweight="bold", color=INK, va="top", transform=ax.transAxes)
    ax.text(0.01, 0.78, verdict, fontsize=13.5, color=INK, va="top", transform=ax.transAxes)
    # if ttfb_delta > 0:
    #     ax.text(0.01, 0.64, f"注意：首字延迟上升 {ttfb_delta:+.1f}%，需要单独确认是否来自 HDC/SQL memory 前置准备。",
    #             fontsize=11.5, color=RED, va="top", transform=ax.transAxes)

    card_w = 0.176
    gap = 0.022
    for i, (label, key, unit, higher_better) in enumerate(metrics):
        x = 0.01 + i * (card_w + gap)
        bv = b.get(key, 0)
        fv = f.get(key, 0)
        delta = fv - bv
        good = _improved(key, delta)
        color = GREEN if good else RED
        pct = _pct_delta(fv, bv)
        delta_unit = "pp" if unit == "%" else unit
        delta_value = delta * 100 if unit == "%" else (delta / 1000 if unit == "s" else delta)
        delta_text = f"{delta_value:+.1f}{delta_unit}" if delta_unit else f"{delta_value:+.1f}"

        card = FancyBboxPatch((x, 0.05), card_w, 0.42, boxstyle="round,pad=0.010,rounding_size=0.006",
                              linewidth=0.8, edgecolor="#D0D0D0", facecolor=PANEL, transform=ax.transAxes)
        ax.add_patch(card)
        ax.text(x + 0.014, 0.38, label, fontsize=10.5, color=MUTED, transform=ax.transAxes)
        ax.text(x + 0.014, 0.22, _fmt_num(fv, unit, 1), fontsize=16, fontweight="bold",
                color=INK, transform=ax.transAxes)
        ax.text(x + card_w - 0.014, 0.37, "高为优" if higher_better else "低为优",
                fontsize=8.2, color=MUTED, ha="right", transform=ax.transAxes)
        ax.text(x + 0.014, 0.095, f"基线 {_fmt_num(bv, unit, 1)}", fontsize=8.8,
                color=MUTED, transform=ax.transAxes)
        ax.text(x + card_w - 0.014, 0.095, f"{delta_text} ({pct:+.1f}%)",
                fontsize=9.2, fontweight="bold", ha="right",
                color=color, transform=ax.transAxes)


def draw_quality_slope(ax, b: dict, f: dict):
    _style_panel(ax, "质量维度：从基线到HDC-SM")
    dim_keys = ["sql_syntax", "table_column", "filter_condition", "result_data", "sql_standard"]
    dim_labels = ["SQL 语法", "表/列引用", "过滤条件", "结果数据", "SQL 规范"]
    b_dims = b.get("dimensions", {})
    f_dims = f.get("dimensions", {})

    y = np.arange(len(dim_keys))[::-1]
    for yi, key, label in zip(y, dim_keys, dim_labels):
        bv = b_dims.get(key, 0) * 100
        fv = f_dims.get(key, 0) * 100
        color = GREEN if fv >= bv else RED
        ax.plot([bv, fv], [yi, yi], color=color, linewidth=2.4, alpha=0.72)
        ax.scatter([bv], [yi], color=BLUE, s=42, zorder=3)
        ax.scatter([fv], [yi], color=ORANGE, s=42, zorder=3)
        ax.text(101.2, yi, f"{fv - bv:+.1f}pp", color=color, fontsize=10, va="center", fontweight="bold")

    ax.set_xlim(60, 107)
    ax.set_yticks(y)
    ax.set_yticklabels(dim_labels, fontsize=10)
    ax.set_xlabel("评分 (%)", fontsize=10, labelpad=10)
    ax.text(0.02, 0.04, "蓝点=基线    橙点=HDC-SM", fontsize=9, color=MUTED, transform=ax.transAxes)


def draw_cost_changes(ax, b: dict, f: dict):
    _style_panel(ax, "核心指标变化")
    metrics = [
        ("通过率", "pass_rate", "higher"),
        ("平均分", "avg_score", "higher"),
        ("平均延迟", "avg_latency_ms"),
        ("首字延迟", "avg_ttfb_ms"),
        ("工具调用", "avg_tool_calls"),
        ("Turns", "avg_turns"),
        ("Token", "avg_tokens"),
    ]
    labels = [m[0] for m in metrics]
    values = []
    colors = []
    for item in metrics:
        label, key = item[0], item[1]
        value = (f.get(key, 0) - b.get(key, 0)) * 100 if key in {"pass_rate", "avg_score"} else _pct_delta(f.get(key, 0), b.get(key, 0))
        values.append(value)
        good = value >= 0 if key in {"pass_rate", "avg_score"} else value <= 0
        colors.append(GREEN if good else RED)
    y = np.arange(len(labels))[::-1]

    ax.barh(y, values, color=colors, alpha=0.82, height=0.48)
    ax.axvline(0, color=INK, linewidth=0.8)
    for yi, v, item in zip(y, values, metrics):
        suffix = "pp" if item[1] in {"pass_rate", "avg_score"} else "%"
        ha = "left" if v >= 0 else "right"
        offset = 1.1 if v >= 0 else -1.1
        ax.text(v + offset, yi, f"{v:+.1f}{suffix}", va="center", ha=ha, fontsize=10.5, color=INK)

    span = max(10, max(abs(v) for v in values) * 1.25)
    ax.set_xlim(-span, span)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("质量指标用 pp；成本指标用相对变化 %", fontsize=10, labelpad=10)


def draw_case_matrix(ax, b: dict, f: dict):
    b_cases = {c["case_id"]: c for c in b.get("cases", [])}
    f_cases = {c["case_id"]: c for c in f.get("cases", [])}
    cids = sorted(set(b_cases) & set(f_cases), key=_sort_case_id)
    if not cids:
        _no_data(ax, "逐用例影响矩阵", "无逐用例数据")
        return

    _style_panel(ax, "逐用例影响矩阵")
    score_deltas = []
    latency_deltas = []
    colors = []
    for cid in cids:
        bc = b_cases[cid]
        fc = f_cases[cid]
        sd = (fc.get("overall_score", 0) - bc.get("overall_score", 0)) * 100
        ld = (fc.get("duration_ms", 0) - bc.get("duration_ms", 0)) / 1000
        score_deltas.append(sd)
        latency_deltas.append(ld)
        colors.append(GREEN if sd >= 0 and ld <= 0 else (AMBER if sd >= 0 else RED))

    x_min = min(score_deltas + [0]) - 4
    x_max = max(score_deltas + [0]) + 5
    y_min = min(latency_deltas + [0]) - 4
    y_max = max(latency_deltas + [0]) + 4
    ax.axhspan(y_min, 0, xmin=0.5, xmax=1.0, color=GREEN, alpha=0.07, linewidth=0)
    ax.axhspan(0, y_max, xmin=0.5, xmax=1.0, color=AMBER, alpha=0.07, linewidth=0)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.scatter(score_deltas, latency_deltas, s=72, color=colors, alpha=0.86, edgecolor=WHITE, linewidth=0.8)
    for cid, sd, ld in zip(cids, score_deltas, latency_deltas):
        ax.text(sd + 0.65, ld + 0.75, cid, fontsize=9, color=INK)

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.text(0.98, 0.06, "质量提升 + 更快", ha="right", va="bottom", fontsize=9, color=GREEN, transform=ax.transAxes)
    ax.text(0.98, 0.96, "质量提升 + 更慢", ha="right", va="top", fontsize=9, color=AMBER, transform=ax.transAxes)
    ax.text(0.02, 0.06, "质量下降", ha="left", va="bottom", fontsize=9, color=RED, transform=ax.transAxes)
    ax.set_xlabel("总分变化 (pp)，越右越好", fontsize=10, labelpad=10)
    ax.set_ylabel("延迟变化 (s)，越下越好", fontsize=10, labelpad=10)


def draw_latency_distribution(ax, b: dict, f: dict):
    b_runs = [r["duration_ms"] / 1000 for r in b.get("run_details", [])]
    f_runs = [r["duration_ms"] / 1000 for r in f.get("run_details", [])]
    if not b_runs or not f_runs:
        _no_data(ax, "Run 延迟分布", "无 run_details 数据")
        return

    _style_panel(ax, "Run 延迟分布")
    rng = np.random.default_rng(20260729)
    bp = ax.boxplot([b_runs, f_runs], patch_artist=True, widths=0.42, showfliers=False,
                    medianprops={"color": INK, "linewidth": 1.5})
    bp["boxes"][0].set_facecolor("#DCECF7")
    bp["boxes"][1].set_facecolor("#F8E4B8")
    for i, durs in enumerate([b_runs, f_runs], start=1):
        jitter = rng.normal(0, 0.045, size=len(durs))
        ax.scatter(np.full(len(durs), i) + jitter, durs, s=16, alpha=0.42,
                   color=BLUE if i == 1 else ORANGE, edgecolors="none")
        ax.text(i, max(durs) * 1.02, f"n={len(durs)}\n均值 {np.mean(durs):.1f}s",
                ha="center", va="bottom", fontsize=9, color=MUTED)

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["基线", "HDC−SM"], fontsize=10)
    ax.set_ylabel("延迟 (s)", fontsize=10, labelpad=10)


def draw_case_changes(ax, b: dict, f: dict):
    b_cases = {c["case_id"]: c for c in b.get("cases", [])}
    f_cases = {c["case_id"]: c for c in f.get("cases", [])}
    cids = sorted(set(b_cases) & set(f_cases), key=_sort_case_id)
    if not cids:
        _no_data(ax, "逐用例质量变化", "无逐用例数据")
        return

    _style_panel(ax, "逐用例质量变化（右侧标注延迟变化）")
    rows = []
    for cid in cids:
        bc = b_cases[cid]
        fc = f_cases[cid]
        score_delta = (fc.get("overall_score", 0) - bc.get("overall_score", 0)) * 100
        latency_delta = (fc.get("duration_ms", 0) - bc.get("duration_ms", 0)) / 1000
        rows.append((cid, score_delta, latency_delta, bc.get("passed"), fc.get("passed")))
    rows.sort(key=lambda x: x[1])

    labels = [r[0] for r in rows]
    score_values = [r[1] for r in rows]
    y = np.arange(len(rows))
    colors = [GREEN if v >= 0 else RED for v in score_values]
    ax.barh(y, score_values, color=colors, alpha=0.9, height=0.6)
    ax.axvline(0, color=INK, linewidth=0.8)

    x_span = max(5, max(abs(v) for v in score_values) * 1.25)
    ax.set_xlim(-x_span, x_span + 11)
    for yi, (cid, sd, ld, b_passed, f_passed) in zip(y, rows):
        status = "修复" if (not b_passed and f_passed) else ("回退" if b_passed and not f_passed else "")
        color = GREEN if ld <= 0 else RED
        ax.text(x_span + 1.0, yi, f"延迟 {ld:+.1f}s {status}", va="center", fontsize=8.5, color=color)
        ax.text(sd + (0.5 if sd >= 0 else -0.5), yi, f"{sd:+.1f}pp",
                va="center", ha="left" if sd >= 0 else "right", fontsize=8, color=INK)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("总分变化 (pp)", fontsize=9)


def draw_difficulty_summary(ax, b: dict, f: dict):
    b_cases = b.get("cases", [])
    f_cases = f.get("cases", [])
    if not b_cases or not f_cases:
        _no_data(ax, "按难度汇总", "无逐用例数据")
        return

    _style_panel(ax, "按难度汇总")
    diffs = ["Easy", "Medium", "Hard"]

    def avg(cases: list[dict], diff: str, key: str) -> float:
        vals = [c.get(key, 0) for c in cases if c.get("difficulty") == diff]
        return float(np.mean(vals)) if vals else 0

    score_delta = [(avg(f_cases, d, "overall_score") - avg(b_cases, d, "overall_score")) * 100 for d in diffs]
    latency_delta = [(avg(f_cases, d, "duration_ms") - avg(b_cases, d, "duration_ms")) / 1000 for d in diffs]
    y = np.arange(len(diffs))[::-1]

    ax.barh(y + 0.18, score_delta, height=0.32, color=[GREEN if v >= 0 else RED for v in score_delta],
            label="分数变化(pp)")
    ax.barh(y - 0.18, latency_delta, height=0.32, color=[GREEN if v <= 0 else RED for v in latency_delta],
            alpha=0.45, label="延迟变化(s)")
    ax.axvline(0, color=INK, linewidth=0.8)
    for yi, sd, ld in zip(y, score_delta, latency_delta):
        ax.text(sd + (0.4 if sd >= 0 else -0.4), yi + 0.18, f"{sd:+.1f}", va="center",
                ha="left" if sd >= 0 else "right", fontsize=8)
        ax.text(ld + (0.4 if ld >= 0 else -0.4), yi - 0.18, f"{ld:+.1f}", va="center",
                ha="left" if ld >= 0 else "right", fontsize=8)

    span = max(5, max([abs(v) for v in score_delta + latency_delta] or [1]) * 1.35)
    ax.set_xlim(-span, span)
    ax.set_yticks(y)
    ax.set_yticklabels(diffs, fontsize=9)
    ax.legend(loc="lower right", fontsize=8, frameon=False)


def draw_repeat_stability(ax, b: dict, f: dict):
    b_runs = b.get("run_details", [])
    f_runs = f.get("run_details", [])
    if not b_runs or not f_runs:
        _no_data(ax, "Repeat 稳定性", "无 run_details 数据")
        return

    _style_panel(ax, "Repeat 稳定性：均值和离散度")

    def grouped(runs: list[dict]) -> dict[int, list[float]]:
        result = {}
        for r in runs:
            result.setdefault(r.get("run_index", 0), []).append(r["duration_ms"] / 1000)
        return result

    b_group = grouped(b_runs)
    f_group = grouped(f_runs)
    idxs = sorted(set(b_group) | set(f_group))
    b_mean = [np.mean(b_group.get(i, [np.nan])) for i in idxs]
    f_mean = [np.mean(f_group.get(i, [np.nan])) for i in idxs]
    b_std = [np.std(b_group.get(i, [0])) for i in idxs]
    f_std = [np.std(f_group.get(i, [0])) for i in idxs]

    ax.plot(idxs, b_mean, "o-", color=BLUE, linewidth=2, label="基线均值")
    ax.plot(idxs, f_mean, "o-", color=ORANGE, linewidth=2, label="HDC-SM均值")
    ax.fill_between(idxs, np.array(b_mean) - np.array(b_std), np.array(b_mean) + np.array(b_std),
                    color=BLUE, alpha=0.12, linewidth=0)
    ax.fill_between(idxs, np.array(f_mean) - np.array(f_std), np.array(f_mean) + np.array(f_std),
                    color=ORANGE, alpha=0.14, linewidth=0)
    ax.set_xticks(idxs)
    ax.set_xlabel("Run 序号", fontsize=9)
    ax.set_ylabel("延迟 (s)", fontsize=9)
    ax.legend(loc="upper right", fontsize=8, frameon=False)


def main():
    parser = argparse.ArgumentParser(description="对比实验可视化")
    parser.add_argument("baseline", help="基线 JSON 报告路径")
    parser.add_argument("fullstack", help="HDC-SM JSON 报告路径")
    parser.add_argument("-o", "--output", default=None, help="输出 PNG 路径（默认与基线 JSON 同目录）")
    parser.add_argument("--dpi", type=int, default=150, help="DPI (默认 150)")
    args = parser.parse_args()

    if not Path(args.baseline).exists():
        print(f"基线 JSON 不存在: {args.baseline}")
        sys.exit(1)
    if not Path(args.fullstack).exists():
        print(f"HDC-SM JSON 不存在: {args.fullstack}")
        sys.exit(1)

    data = load_data(args.baseline, args.fullstack)
    b = data["baseline"]
    f = data["fullstack"]

    fig = plt.figure(figsize=(17.2, 12.2), constrained_layout=False)
    gs = GridSpec(3, 2, figure=fig, height_ratios=[1.35, 2.35, 2.35], hspace=0.72, wspace=0.30)
    fig.suptitle("基线 vs HDC-SM 对比实验", fontsize=18, fontweight="bold", color=INK, y=0.975)

    ax_kpi = fig.add_subplot(gs[0, :])
    ax_cost = fig.add_subplot(gs[1, 0])
    ax_cases = fig.add_subplot(gs[1, 1])
    ax_quality = fig.add_subplot(gs[2, 0])
    ax_latency = fig.add_subplot(gs[2, 1])

    draw_kpi_cards(ax_kpi, b, f)
    draw_cost_changes(ax_cost, b, f)
    draw_case_matrix(ax_cases, b, f)
    draw_quality_slope(ax_quality, b, f)
    draw_latency_distribution(ax_latency, b, f)

    fig.subplots_adjust(left=0.065, right=0.985, top=0.90, bottom=0.075)

    output = args.output
    if output is None:
        output = str(Path(args.baseline).with_suffix("")) + "_viz.png"

    fig.savefig(output, dpi=args.dpi, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    print(f"可视化已保存: {output}")


if __name__ == "__main__":
    main()
