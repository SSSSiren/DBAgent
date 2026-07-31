#!/usr/bin/env python3
"""
收敛性分析 — 从前缀样本看评估结论是否稳定

读取两份 repeat=N 的 JSON 报告，按前缀 r=[1,3,5,7,10] 取子样本，
用 bootstrap 计算 95% CI，生成收敛性报告+图表。

用法:
    python tools/convergence_analysis.py baseline.json fullstack.json
    python tools/convergence_analysis.py baseline.json fullstack.json -o report.md --png chart.png
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

# ── 配色 ──
BLUE = "#2196F3"
ORANGE = "#FF9800"
BLUE_LIGHT = "#BBDEFB"
ORANGE_LIGHT = "#FFE0B2"
GRAY = "#9E9E9E"
GRAY_LIGHT = "#F5F5F5"
BG = "#FAFAFA"
GREEN = "#4CAF50"
RED = "#F44336"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["PingFang SC", "Heiti SC", "Hiragino Sans GB", "Arial", "DejaVu Sans"],
    "axes.facecolor": BG,
    "figure.facecolor": "white",
    "grid.alpha": 0.3,
    "axes.grid": True,
    "axes.unicode_minus": False,
})

PREFIXES = [1, 4, 8, 12, 16]


# ──────────────────────────────────────────────
# 数据加载
# ──────────────────────────────────────────────

def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def extract_run_metrics(data: dict) -> dict[str, list[dict]]:
    """从 EvaluationReport JSON 提取 per-case per-run 指标。
    返回 {case_id: [{sql_score, duration_ms, total_tokens, tool_call_count, ...}, ...]}
    """
    result: dict[str, list[dict]] = {}
    for cr in data.get("case_results", []):
        cid = cr["test_case"]["case_id"]
        runs = []
        for rd in cr.get("run_details", []):
            runs.append({
                "sql_score": rd.get("sql_score") or 0,
                "quality_score": rd.get("quality_score") or 0,
                "duration_ms": rd.get("duration_ms", 0),
                "total_tokens": rd.get("total_tokens", 0),
                "input_tokens": rd.get("input_tokens", 0),
                "output_tokens": rd.get("output_tokens", 0),
                "tool_call_count": rd.get("tool_call_count", 0),
                "turns": rd.get("turns", 0),
                "ttfb_ms": rd.get("ttfb_ms", 0),
            })
        result[cid] = runs
    return result


# ──────────────────────────────────────────────
# 前缀分析
# ──────────────────────────────────────────────

def prefix_metrics(
    case_runs: dict[str, list[dict]],
    r: int,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """对每个 case 取前 r 个 run，计算聚合指标（含 bootstrap CI）。"""
    rng = np.random.RandomState(seed)

    metrics = {
        "sql_score": {"mean": 0, "ci_low": 0, "ci_high": 0},
        "duration_ms": {"mean": 0, "ci_low": 0, "ci_high": 0, "p95": 0},
        "total_tokens": {"mean": 0, "ci_low": 0, "ci_high": 0},
        "tool_call_count": {"mean": 0, "ci_low": 0, "ci_high": 0},
        "turns": {"mean": 0, "ci_low": 0, "ci_high": 0},
        "pass_rate": {"mean": 0, "ci_low": 0, "ci_high": 0},
    }

    # 构建每个 case 的聚合值（取前 r 个 run 的均值）
    case_means: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for cid, runs in case_runs.items():
        prefix = runs[:r]
        if not prefix:
            continue
        for key in ["sql_score", "duration_ms", "total_tokens", "tool_call_count", "turns"]:
            vals = [run[key] for run in prefix]
            case_means[cid][key] = vals

    # 按 case 聚合（先 per-case 平均，再跨 case 平均）
    def _per_case_avg(key: str) -> list[float]:
        return [np.mean(case_means[cid][key]) for cid in sorted(case_means) if case_means[cid][key]]

    def _bootstrap(values: list[float], n: int = n_bootstrap) -> tuple[float, float, float]:
        mean = np.mean(values)
        if len(values) <= 1:
            return mean, mean, mean
        boots = []
        for _ in range(n):
            sample = rng.choice(values, size=len(values), replace=True)
            boots.append(np.mean(sample))
        boots.sort()
        ci_low = boots[int(n * 0.025)]
        ci_high = boots[int(n * 0.975)]
        return mean, ci_low, ci_high

    for key in ["sql_score", "duration_ms", "total_tokens", "tool_call_count", "turns"]:
        vals = _per_case_avg(key)
        if vals:
            m, lo, hi = _bootstrap(vals)
            metrics[key]["mean"] = m
            metrics[key]["ci_low"] = lo
            metrics[key]["ci_high"] = hi
            if key == "duration_ms":
                # P95：所有 case 内所有 run 的 P95
                all_durs = []
                for cid in sorted(case_means):
                    all_durs.extend(case_means[cid][key])
                metrics[key]["p95"] = float(np.percentile(all_durs, 95)) if all_durs else 0

    # pass_rate：sql_score >= 0.8 视为通过
    sql_vals = _per_case_avg("sql_score")
    if sql_vals:
        passed = [1 if s >= 0.8 else 0 for s in sql_vals]
        m, lo, hi = _bootstrap(passed)
        metrics["pass_rate"]["mean"] = m
        metrics["pass_rate"]["ci_low"] = lo
        metrics["pass_rate"]["ci_high"] = hi

    return metrics


# ──────────────────────────────────────────────
# 报告生成
# ──────────────────────────────────────────────

def generate_report(
    b_prefixes: dict[int, dict],
    f_prefixes: dict[int, dict],
    output_path: str,
) -> None:
    """生成 Markdown 收敛性报告。"""
    lines: list[str] = []
    lines.append("# 收敛性分析报告\n")
    lines.append(f"**生成时间**: {Path(output_path).stat().st_mtime if Path(output_path).exists() else 'N/A'}\n")
    lines.append(f"**前缀点**: r = {', '.join(str(p) for p in PREFIXES)}\n")
    lines.append("**方法**: 对每个 case 取前 r 个 run 的均值，跨 case 聚合，bootstrap 1000 次计算 95% CI\n")

    # ── 收敛判定 ──
    lines.append("## 收敛判定\n")

    # 取最后两个前缀点做收敛判定
    r_last = PREFIXES[-1]
    r_prev = PREFIXES[-2] if len(PREFIXES) >= 2 else r_last

    lines.append(f"| 指标 | r={r_prev} vs r={r_last} 变化 | 变化率 | 判定 |")
    lines.append("|------|-------------------|--------|------|")

    def _check_convergence(key: str, label: str, threshold: float, is_pct: bool = True):
        bp = b_prefixes[r_prev][key]["mean"]
        bl = b_prefixes[r_last][key]["mean"]
        fp = f_prefixes[r_prev][key]["mean"]
        fl = f_prefixes[r_last][key]["mean"]
        delta_prev = fp - bp
        delta_last = fl - bl
        change = abs(delta_last - delta_prev)
        if is_pct:
            if abs(delta_last) > 0.001:
                rate = change / abs(delta_last) * 100
            else:
                rate = 0
            verdict = "✅ 收敛" if rate < threshold else ("⚠️ 边界" if rate < threshold * 2 else "❌ 未收敛")
            lines.append(f"| {label} delta | {delta_prev:+.1%} → {delta_last:+.1%} | {rate:.1f}% | {verdict} |")
        else:
            if abs(delta_last) > 1:
                rate = change / abs(delta_last) * 100
            else:
                rate = 0
            verdict = "✅ 收敛" if rate < threshold else ("⚠️ 边界" if rate < threshold * 2 else "❌ 未收敛")
            lines.append(f"| {label} delta | {delta_prev:+.0f} → {delta_last:+.0f}ms | {rate:.1f}% | {verdict} |")

    _check_convergence("sql_score", "分数", 1, is_pct=True)   # 1pp
    _check_convergence("duration_ms", "延迟", 5, is_pct=False)  # 5%
    _check_convergence("total_tokens", "Token", 5, is_pct=False)  # 5%

    # 通过率稳定性
    b_pass_prev = b_prefixes[r_prev]["pass_rate"]["mean"]
    b_pass_last = b_prefixes[r_last]["pass_rate"]["mean"]
    f_pass_prev = f_prefixes[r_prev]["pass_rate"]["mean"]
    f_pass_last = f_prefixes[r_last]["pass_rate"]["mean"]
    pass_delta_prev = f_pass_prev - b_pass_prev
    pass_delta_last = f_pass_last - b_pass_last
    lines.append(f"| 通过率 delta | {pass_delta_prev:+.1%} → {pass_delta_last:+.1%} | — | {'✅ 稳定' if abs(pass_delta_last - pass_delta_prev) < 0.05 else '⚠️ 波动'} |")

    lines.append("")

    # ── 详细数据表 ──
    lines.append("## 前缀聚合数据\n")

    header_cols = " | ".join(f"r={r}" for r in PREFIXES)
    sep_cols = "|".join(["------"] + ["-----"] * len(PREFIXES))

    for label, data, color in [("基线", b_prefixes, BLUE), ("HDC-SM", f_prefixes, ORANGE)]:
        lines.append(f"### {label}\n")
        lines.append(f"| 指标 | {header_cols} |")
        lines.append(f"|------|{sep_cols}|")

        for key, name, fmt in [
            ("sql_score", "平均 SQL 分", ".1%"),
            ("pass_rate", "通过率", ".1%"),
            ("duration_ms", "平均延迟", ".0f"),
            ("total_tokens", "平均 Token", ".0f"),
            ("tool_call_count", "平均工具调用", ".1f"),
            ("turns", "平均 Turns", ".1f"),
        ]:
            vals = []
            for r in PREFIXES:
                m = data[r][key]["mean"]
                vals.append(f"{m:{fmt}}")
            lines.append(f"| {name} | {' | '.join(vals)} |")
        lines.append("")

    # ── Delta 表 ──
    lines.append("## Delta（HDC-SM - 基线）\n")
    lines.append(f"| 指标 | {header_cols} | 趋势 |")
    lines.append(f"|------|{sep_cols}|------|")

    for key, name, fmt in [
        ("sql_score", "分数 delta", ".1%"),
        ("pass_rate", "通过率 delta", ".1%"),
        ("duration_ms", "延迟 delta", ".0f"),
        ("total_tokens", "Token delta", ".0f"),
        ("tool_call_count", "工具调用 delta", ".1f"),
        ("turns", "Turns delta", ".1f"),
    ]:
        deltas = []
        for r in PREFIXES:
            d = f_prefixes[r][key]["mean"] - b_prefixes[r][key]["mean"]
            deltas.append(d)
        # 趋势判断
        if len(deltas) >= 3:
            early = np.mean(deltas[:2])
            late = np.mean(deltas[-2:])
            if abs(late - early) < abs(early) * 0.05:
                trend = "➡️ 稳定"
            elif abs(late) < abs(early):
                trend = "↘ 收敛中"
            else:
                trend = "↗ 发散"
        else:
            trend = "—"
        vals_str = " | ".join(f"{d:{fmt}}" for d in deltas)
        lines.append(f"| {name} | {vals_str} | {trend} |")

    lines.append("")

    # ── 结论 ──
    lines.append("## 结论\n")
    lines.append("### 收敛状态\n")
    lines.append(f"- 前缀点: r = {', '.join(str(p) for p in PREFIXES)}")
    lines.append(f"- 判定标准: 最后两个前缀点 ({r_prev}→{r_last}) 间 delta 变化 < 1pp（分数）且 < 5%（延迟/Token）")
    lines.append("")

    # 写入
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ──────────────────────────────────────────────
# 图表生成
# ──────────────────────────────────────────────

def draw_convergence_chart(
    b_prefixes: dict[int, dict],
    f_prefixes: dict[int, dict],
    output_path: str,
    dpi: int = 150,
) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("收敛性分析 — 前缀样本稳定性", fontsize=14, fontweight="bold", y=0.98)

    x = np.array(PREFIXES, dtype=float)

    def _fill_between(ax, x, means, ci_lows, ci_highs, color, label):
        ax.plot(x, means, "o-", color=color, linewidth=2, markersize=6, label=label)
        ax.fill_between(x, ci_lows, ci_highs, alpha=0.15, color=color)

    def _draw_metric(ax, key: str, title: str, ylabel: str, fmt: str = ".1f", is_pct: bool = False):
        b_means = [b_prefixes[r][key]["mean"] * (100 if is_pct else 1) for r in PREFIXES]
        b_lo = [b_prefixes[r][key]["ci_low"] * (100 if is_pct else 1) for r in PREFIXES]
        b_hi = [b_prefixes[r][key]["ci_high"] * (100 if is_pct else 1) for r in PREFIXES]
        f_means = [f_prefixes[r][key]["mean"] * (100 if is_pct else 1) for r in PREFIXES]
        f_lo = [f_prefixes[r][key]["ci_low"] * (100 if is_pct else 1) for r in PREFIXES]
        f_hi = [f_prefixes[r][key]["ci_high"] * (100 if is_pct else 1) for r in PREFIXES]

        _fill_between(ax, x, b_means, b_lo, b_hi, BLUE, "基线")
        _fill_between(ax, x, f_means, f_lo, f_hi, ORANGE, "HDC-SM")

        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("Repeat 前缀数", fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_xticks(PREFIXES)
        ax.legend(fontsize=8, loc="best")
        ax.set_xlim(PREFIXES[0] - 0.3, PREFIXES[-1] + 0.3)

    def _draw_delta(ax, key: str, title: str, ylabel: str, is_pct: bool = False):
        d_means = []
        d_los = []
        d_his = []
        for r in PREFIXES:
            bm = b_prefixes[r][key]["mean"]
            fm = f_prefixes[r][key]["mean"]
            # Delta: use bootstrap of differences
            # Simplify: delta mean = fm - bm, CI = sqrt(ci_b^2 + ci_f^2) approximation
            d_means.append((fm - bm) * (100 if is_pct else 1))
            b_ci = (b_prefixes[r][key]["ci_high"] - b_prefixes[r][key]["ci_low"]) / 2
            f_ci = (f_prefixes[r][key]["ci_high"] - f_prefixes[r][key]["ci_low"]) / 2
            ci = math.sqrt(b_ci**2 + f_ci**2) * (100 if is_pct else 1)
            d_los.append(d_means[-1] - ci)
            d_his.append(d_means[-1] + ci)

        color = GREEN if d_means[-1] >= 0 else RED
        ax.plot(x, d_means, "o-", color=color, linewidth=2, markersize=6)
        ax.fill_between(x, d_los, d_his, alpha=0.15, color=color)
        ax.axhline(y=0, color=GRAY, linewidth=0.8, linestyle="--")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("Repeat 前缀数", fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_xticks(PREFIXES)
        ax.set_xlim(PREFIXES[0] - 0.3, PREFIXES[-1] + 0.3)

    # (0,0): average_score
    _draw_metric(axes[0, 0], "sql_score", "SQL 分数收敛", "SQL 分数 (%)", is_pct=True)

    # (0,1): score delta
    _draw_delta(axes[0, 1], "sql_score", "分数 Delta 收敛", "Delta (pp)", is_pct=True)

    # (0,2): pass_rate
    _draw_metric(axes[0, 2], "pass_rate", "通过率收敛", "通过率 (%)", is_pct=True)

    # (1,0): latency
    b_means = [b_prefixes[r]["duration_ms"]["mean"] / 1000 for r in PREFIXES]
    b_lo = [b_prefixes[r]["duration_ms"]["ci_low"] / 1000 for r in PREFIXES]
    b_hi = [b_prefixes[r]["duration_ms"]["ci_high"] / 1000 for r in PREFIXES]
    f_means = [f_prefixes[r]["duration_ms"]["mean"] / 1000 for r in PREFIXES]
    f_lo = [f_prefixes[r]["duration_ms"]["ci_low"] / 1000 for r in PREFIXES]
    f_hi = [f_prefixes[r]["duration_ms"]["ci_high"] / 1000 for r in PREFIXES]
    b_p95 = [b_prefixes[r]["duration_ms"]["p95"] / 1000 for r in PREFIXES]
    f_p95 = [f_prefixes[r]["duration_ms"]["p95"] / 1000 for r in PREFIXES]

    _fill_between(axes[1, 0], x, b_means, b_lo, b_hi, BLUE, "基线")
    _fill_between(axes[1, 0], x, f_means, f_lo, f_hi, ORANGE, "HDC-SM")
    axes[1, 0].plot(x, b_p95, "--", color=BLUE, linewidth=1, alpha=0.5, label="基线 P95")
    axes[1, 0].plot(x, f_p95, "--", color=ORANGE, linewidth=1, alpha=0.5, label="HDC-SM P95")
    axes[1, 0].set_title("延迟收敛 (±P95)", fontsize=11, fontweight="bold")
    axes[1, 0].set_xlabel("Repeat 前缀数", fontsize=8)
    axes[1, 0].set_ylabel("延迟 (s)", fontsize=8)
    axes[1, 0].set_xticks(PREFIXES)
    axes[1, 0].legend(fontsize=7, loc="best")
    axes[1, 0].set_xlim(PREFIXES[0] - 0.3, PREFIXES[-1] + 0.3)

    # (1,1): latency delta
    _draw_delta(axes[1, 1], "duration_ms", "延迟 Delta 收敛", "Delta (ms)")

    # (1,2): tokens
    _draw_metric(axes[1, 2], "total_tokens", "Token 收敛", "Token 数")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"📊 收敛性图表: {output_path}")


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="收敛性分析 — 前缀样本稳定性")
    parser.add_argument("baseline", help="基线 JSON 报告路径")
    parser.add_argument("fullstack", help="HDC-SM JSON 报告路径")
    parser.add_argument("-o", "--output", default=None, help="Markdown 报告输出路径")
    parser.add_argument("--png", default=None, help="PNG 图表输出路径")
    parser.add_argument("--prefixes", type=str, default="1,3,5,7,10",
                        help="前缀点，逗号分隔（默认 1,3,5,7,10）")
    parser.add_argument("--dpi", type=int, default=150, help="PNG DPI")
    args = parser.parse_args()

    global PREFIXES
    PREFIXES = [int(x.strip()) for x in args.prefixes.split(",")]

    if not Path(args.baseline).exists():
        print(f"❌ 基线 JSON 不存在: {args.baseline}")
        sys.exit(1)
    if not Path(args.fullstack).exists():
        print(f"❌ HDC-SM JSON 不存在: {args.fullstack}")
        sys.exit(1)

    b_data = load_json(args.baseline)
    f_data = load_json(args.fullstack)

    b_runs = extract_run_metrics(b_data)
    f_runs = extract_run_metrics(f_data)

    # 检查 run_details 是否有足够数据
    b_cases = list(b_runs.keys())
    f_cases = list(f_runs.keys())
    if not b_cases:
        print("❌ 基线 JSON 中没有 run_details 数据（需要 EvaluationReport 格式）")
        sys.exit(1)
    if not f_cases:
        print("❌ HDC-SM JSON 中没有 run_details 数据")
        sys.exit(1)

    max_r = max(PREFIXES)
    b_min_runs = min(len(runs) for runs in b_runs.values())
    f_min_runs = min(len(runs) for runs in f_runs.values())
    if b_min_runs < max_r or f_min_runs < max_r:
        print(f"⚠️  最大前缀 r={max_r}，但最小 run 数: 基线={b_min_runs}, HDC-SM={f_min_runs}")
        print(f"   将使用实际可用 run 数。建议用 repeat >= {max_r} 重新跑。")

    # 计算各前缀指标
    print(f"分析前缀: r = {PREFIXES}")
    print(f"用例数: {len(b_cases)}")
    print(f"Bootstrap: 1000 次\n")

    b_prefixes: dict[int, dict] = {}
    f_prefixes: dict[int, dict] = {}
    for r in PREFIXES:
        actual_r = min(r, b_min_runs, f_min_runs)
        b_prefixes[r] = prefix_metrics(b_runs, actual_r)
        f_prefixes[r] = prefix_metrics(f_runs, actual_r)
        print(f"  r={r}: 基线 sql_score={b_prefixes[r]['sql_score']['mean']:.1%}  "
              f"HDC-SM sql_score={f_prefixes[r]['sql_score']['mean']:.1%}  "
              f"delta={(f_prefixes[r]['sql_score']['mean'] - b_prefixes[r]['sql_score']['mean']):+.1%}")

    # 输出
    output_md = args.output
    if output_md is None:
        output_md = str(Path(args.baseline).with_suffix("")) + "_convergence.md"

    generate_report(b_prefixes, f_prefixes, output_md)
    print(f"\n✅ 报告: {output_md}")

    png_path = args.png
    if png_path is None:
        png_path = str(Path(args.baseline).with_suffix("")) + "_convergence.png"

    draw_convergence_chart(b_prefixes, f_prefixes, png_path, dpi=args.dpi)


if __name__ == "__main__":
    main()