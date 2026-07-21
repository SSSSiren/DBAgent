#!/usr/bin/env python3
"""
HDC Prompt 诊断脚本

对每条测试用例，分别构建"无 HDC"和"有 HDC"两种 session_state，
调用 build_context() 生成 Agent 实际收到的完整 prompt，并输出差异。

用法:
    python tests/evaluation/debug_hdc_prompt.py              # 全部用例
    python tests/evaluation/debug_hdc_prompt.py --ids TC-001 # 指定用例
    python tests/evaluation/debug_hdc_prompt.py --difficulty Hard
    python tests/evaluation/debug_hdc_prompt.py --output /tmp/hdc_debug  # 输出目录
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.evaluation.loader import load_test_cases, filter_test_cases
from app.agent.context import build_context


# ── 创建 session_state ──

def _make_session_state(schema_id: int = 65938636) -> dict:
    return {
        "selected_schema_id": schema_id,
        "selected_database": {"schemaName": "dw_onedba"},
        "chat_history": [],
        "summary": "",
    }


# ── HDC 检索 ──

async def _retrieve_hdc(user_input: str, database_name: str, schema_id: int, user_id: str = "debug") -> str:
    """调用 HDC 检索并返回格式化的上下文文本，失败返回空字符串。"""
    from app.config import get_settings as _cfg
    from app.datavault.retriever import HDCRetriever
    from app.knowledge.openviking import OpenVikingClient as OVC

    settings = _cfg()
    if not settings.hdc_enabled:
        return "[HDC 未启用 — hdc_enabled=False]"

    try:
        ov = OVC(settings.kb_openviking_url, user_id)
        await ov.start()
        try:
            retriever = HDCRetriever(ov)
            hdc_ctx = await retriever.retrieve(user_input, schema_id, database_name)
            if hdc_ctx:
                return retriever.format_context(hdc_ctx)
            return "[HDC 检索完成 — 无匹配结果]"
        finally:
            await ov.close()
    except Exception as e:
        return f"[HDC 检索异常: {type(e).__name__}: {e}]"


# ── 主流程 ──

async def debug_one(
    tc,
    schema_id: int,
    db_name: str,
    output_dir: Path,
) -> dict:
    """对一条用例诊断 HDC vs 无 HDC 的 prompt 差异。"""
    case_id = tc.case_id
    question = tc.question

    # ── 无 HDC ──
    state_no_hdc = _make_session_state(schema_id)
    context_no_hdc = build_context(state_no_hdc)
    full_prompt_no_hdc = f"{context_no_hdc}\n\n用户问题: {question}" if context_no_hdc else question

    # ── 有 HDC ──
    state_with_hdc = _make_session_state(schema_id)
    hdc_text = await _retrieve_hdc(question, db_name, schema_id)
    if hdc_text and not hdc_text.startswith("[HDC"):
        state_with_hdc["_hdc_context"] = hdc_text
    context_with_hdc = build_context(state_with_hdc)
    full_prompt_with_hdc = f"{context_with_hdc}\n\n用户问题: {question}" if context_with_hdc else question

    # ── 差异分析 ──
    hdc_only = ""
    if hdc_text and not hdc_text.startswith("[HDC"):
        # HDC 成功注入了内容
        hdc_only = hdc_text
        hdc_chars = len(hdc_text)
        hdc_lines = hdc_text.count("\n") + 1
    else:
        hdc_chars = 0
        hdc_lines = 0

    no_hdc_len = len(full_prompt_no_hdc)
    with_hdc_len = len(full_prompt_with_hdc)
    delta = with_hdc_len - no_hdc_len

    # ── 写入文件 ──
    case_dir = output_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "prompt_no_hdc.txt").write_text(full_prompt_no_hdc, encoding="utf-8")
    (case_dir / "prompt_with_hdc.txt").write_text(full_prompt_with_hdc, encoding="utf-8")
    if hdc_only:
        (case_dir / "hdc_context_only.txt").write_text(hdc_only, encoding="utf-8")

    return {
        "case_id": case_id,
        "question": question,
        "no_hdc_chars": no_hdc_len,
        "with_hdc_chars": with_hdc_len,
        "delta_chars": delta,
        "hdc_chars": hdc_chars,
        "hdc_lines": hdc_lines,
        "hdc_ok": hdc_chars > 0,
    }


async def main():
    parser = argparse.ArgumentParser(description="HDC Prompt 诊断工具")
    parser.add_argument("--ids", nargs="*", default=None, help="指定用例 ID")
    parser.add_argument("--difficulty", choices=["Easy", "Medium", "Hard"], default=None)
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--schema-id", type=int, default=65938636)
    parser.add_argument("--output", type=str, default="tests/evaluation/output/hdc_prompt_debug",
                        help="输出目录")
    parser.add_argument("--db-name", type=str, default="dw_onedba")
    args = parser.parse_args()

    cases = load_test_cases()
    filtered = filter_test_cases(cases, ids=args.ids, difficulty=args.difficulty, category=args.category)

    if not filtered:
        print("没有匹配的测试用例")
        return

    output_dir = Path(args.output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"HDC Prompt 诊断 — {len(filtered)} 条用例")
    print(f"{'='*60}")
    print(f"输出目录: {output_dir}")
    print()

    summary_header = f"{'ID':<8} {'无HDC(字符)':>12} {'有HDC(字符)':>12} {'Delta':>8} {'HDC内容':>10} {'状态':<20}"
    print(summary_header)
    print("-" * len(summary_header))

    results = []
    for tc in filtered:
        r = await debug_one(tc, args.schema_id, args.db_name, output_dir)
        results.append(r)

        status = "✅ HDC 已注入" if r["hdc_ok"] else "⚠️ HDC 空/异常"
        hdc_info = f"{r['hdc_chars']}字符/{r['hdc_lines']}行" if r["hdc_ok"] else "—"
        print(f"{r['case_id']:<8} {r['no_hdc_chars']:>12,} {r['with_hdc_chars']:>12,} "
              f"{r['delta_chars']:>+8,} {hdc_info:>10} {status:<20}")

    # 汇总
    hdc_ok = sum(1 for r in results if r["hdc_ok"])
    total_delta = sum(r["delta_chars"] for r in results)
    avg_delta = total_delta / len(results) if results else 0
    avg_hdc = sum(r["hdc_chars"] for r in results) / len(results) if results else 0

    print(f"\n{'='*60}")
    print(f"汇总")
    print(f"{'='*60}")
    print(f"HDC 成功注入: {hdc_ok}/{len(results)} 条")
    print(f"HDC 内容平均: {avg_hdc:,.0f} 字符")
    print(f"Prompt 增量平均: {avg_delta:,.0f} 字符")

    # 写入汇总文件
    summary_path = output_dir / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"HDC Prompt 诊断报告\n")
        f.write(f"{'='*60}\n")
        f.write(f"时间: {datetime.now().isoformat()}\n")
        f.write(f"用例数: {len(results)}\n")
        f.write(f"HDC 成功注入: {hdc_ok}/{len(results)}\n\n")
        for r in results:
            f.write(f"{r['case_id']}: 无HDC={r['no_hdc_chars']:,}字符, "
                    f"有HDC={r['with_hdc_chars']:,}字符, Delta={r['delta_chars']:+,}\n")

    print(f"\n详细文件: {output_dir}")
    print(f"  每个用例目录下有:")
    print(f"    prompt_no_hdc.txt    — 无 HDC 时 LLM 收到的完整 prompt")
    print(f"    prompt_with_hdc.txt  — 有 HDC 时 LLM 收到的完整 prompt")
    print(f"    hdc_context_only.txt — 仅 HDC 注入的内容（若有）")


if __name__ == "__main__":
    asyncio.run(main())
