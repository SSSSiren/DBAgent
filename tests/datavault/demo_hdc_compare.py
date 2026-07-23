#!/usr/bin/env python3
"""
HDC 对比实验（依赖 HDC 知识库已就绪）
======================================

对比同一 NL2SQL 问题，有 HDC 知识库 vs 无 HDC 基线的 Agent 表现差异。

前置条件：
  - HDC 知识库已通过 demo_hdc_generate.py 生成并验证通过
  - OpenViking Server 运行在 localhost:1933
  - OneDBA 可访问
  - LLM 可访问

运行方式：
  cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
  python tests/datavault/demo_hdc_compare.py [schema_id] [database_name]
"""

import asyncio
import os
import sys
import time
import uuid
from typing import Any

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.config import get_settings

# ═══════════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════════

OV_BASE_URL = "http://localhost:1933"
TEST_USER = "hdc-compare"
TEST_SESSION_PREFIX = f"hdc-cmp-{uuid.uuid4().hex[:8]}"

SETTINGS = get_settings()
TARGET_SCHEMA_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 25800743
TARGET_DB_NAME = sys.argv[2] if len(sys.argv) > 2 else "dw_onedba"

HDC_RESOURCE_BASE = f"viking://user/hdc-system/memories/hdc/{TARGET_SCHEMA_ID}/{TARGET_DB_NAME}"

OV_HEADERS = {
    "Content-Type": "application/json",
    "X-OpenViking-Account": "default",
    "X-OpenViking-User": TEST_USER,
}


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_sub(title: str):
    print(f"\n--- {title} ---")


# ═══════════════════════════════════════════════════════════════
#  HDC 检索
# ═══════════════════════════════════════════════════════════════

async def hdc_retrieve(question: str) -> dict[str, Any]:
    """从 HDC 知识库检索与问题相关的表和列信息。"""
    from app.datavault.retriever import HDCRetriever
    from app.knowledge.openviking import OpenVikingClient

    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    retriever = HDCRetriever(ov)
    hdc_ctx = await retriever.retrieve(question, TARGET_SCHEMA_ID, TARGET_DB_NAME)
    await ov.close()

    if not hdc_ctx:
        return {"matched_tables": [], "context_text": ""}

    matched = []
    for t in hdc_ctx.matched_tables:
        matched.append({
            "table_name": t.table_name,
            "main_entity": t.main_entity,
            "table_type": t.table_type,
            "relevant_columns": t.relevant_columns,
        })

    return {
        "matched_tables": matched,
        "context_text": retriever.format_context(hdc_ctx),
        "table_count": len(matched),
    }


# ═══════════════════════════════════════════════════════════════
#  Agent 执行
# ═══════════════════════════════════════════════════════════════

async def run_agent_round(
    question: str,
    with_hdc: bool,
    round_label: str,
) -> dict[str, Any]:
    """执行一轮 Agent 对话，收集全部指标。"""
    from app.agent.runner import run_agent_stream

    session_state = {
        "session_id": f"{TEST_SESSION_PREFIX}-{round_label}",
        "user_id": TEST_USER,
        "chat_history": [],
        "summary": "",
        "kb_session_id": "",
        "kb_turn_count": 0,
        "selected_database": {"schemaName": TARGET_DB_NAME},
        "selected_schema_id": TARGET_SCHEMA_ID,
    }

    # ── HDC 检索 ──
    if with_hdc:
        hdc_info = await hdc_retrieve(question)
        if hdc_info["context_text"]:
            session_state["_hdc_context"] = hdc_info["context_text"]
            print(f"    [HDC] ✅ 检索到 {hdc_info['table_count']} 张匹配表")
            for t in hdc_info["matched_tables"][:5]:
                print(f"          {t['table_name']} ({t['main_entity']}) [{t['table_type']}]")
        else:
            print(f"    [HDC] ❌ 未检索到匹配表")
            hdc_info = None
    else:
        hdc_info = None

    # ── 执行 Agent ──
    tool_call_names: list[str] = []
    sqls: list[str] = []
    thinking_texts: list[str] = []
    final_response = ""
    stats: dict[str, Any] = {}
    error: str | None = None

    start_time = time.monotonic()

    try:
        async with asyncio.timeout(120):
            async for event_type, data in run_agent_stream(
                question, session_state,
                trace_name=f"HDC-CMP-{round_label}",
            ):
                if event_type == "step":
                    step = data.get("step", "")
                    status = data.get("status", "")
                    if step == "thinking" and status == "running":
                        text = data.get("text", "")
                        if text:
                            thinking_texts.append(text)
                    elif step.startswith("tool:") and status == "running":
                        tool_name = step.replace("tool:", "")
                        tool_call_names.append(tool_name)
                        print(f"    [Tool] {tool_name}")
                elif event_type == "sql":
                    sql_text = data.get("sql", "")
                    if sql_text:
                        sqls.append(sql_text)
                        print(f"    [SQL] {sql_text[:120]}...")
                elif event_type == "final":
                    final_response = data.get("response", "")
                    stats = data.get("stats", {})
    except asyncio.TimeoutError:
        error = "执行超时 (120s)"
    except TimeoutError:
        error = "执行超时 (120s)"
    except Exception as e:
        error = f"执行异常: {type(e).__name__}: {e}"

    duration_ms = int((time.monotonic() - start_time) * 1000)

    return {
        "response": final_response,
        "tool_call_names": tool_call_names,
        "sqls": sqls,
        "thinking_texts": thinking_texts,
        "stats": stats,
        "duration_ms": duration_ms,
        "error": error,
        "hdc_info": hdc_info,
    }


# ═══════════════════════════════════════════════════════════════
#  测试问题
# ═══════════════════════════════════════════════════════════════

TEST_QUESTIONS = [
    {
        "id": "Q1",
        "question": "帮我查一下这个数据库里有哪些表",
        "expected_tools": ["find_table", "list_databases"],
        "hdc_benefit": "HDC 数据库摘要直接告诉 Agent 表数量、核心实体和业务域",
    },
    {
        "id": "Q2",
        "question": "统计一下最近创建的表的数据量",
        "expected_tools": ["execute_sql", "query_database"],
        "hdc_benefit": "HDC 表描述包含 row_count_estimate",
    },
    {
        "id": "Q3",
        "question": "帮我看看数据库里有没有和告警相关的表，如果有的话描述一下结构",
        "expected_tools": ["find_table", "describe_table"],
        "hdc_benefit": "HDC main_entity 含同义词 '告警/报警/监控告警'，Agent 直接定位",
    },
]


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 70)
    print("  HDC 对比实验")
    print("=" * 70)
    print(f"  目标: {TARGET_DB_NAME} (schemaId={TARGET_SCHEMA_ID})")
    print(f"  OpenViking: {OV_BASE_URL}")
    print(f"  LLM: {SETTINGS.llm_model}")
    print(f"  测试问题: {len(TEST_QUESTIONS)}")
    print(f"  方式: 每问题两轮 — 基线（无 HDC） vs 实验（有 HDC）")
    print()

    results = []

    for i, tc in enumerate(TEST_QUESTIONS):
        qid = tc["id"]
        print_section(f"问题 {i+1}/{len(TEST_QUESTIONS)}: {qid} — {tc['question']}")

        # ── 基线（无 HDC）──
        print_sub(f"{qid} 基线（无 HDC）")
        print(f"  预期: Agent 自行发现表结构")
        base = await run_agent_round(tc["question"], with_hdc=False, round_label=f"{qid}-base")

        print_sub(f"{qid} 基线结果")
        print(f"  工具调用 ({len(base['tool_call_names'])} 轮): {' → '.join(base['tool_call_names']) if base['tool_call_names'] else '(无)'}")
        print(f"  耗时: {base['duration_ms']}ms | Token: {base['stats'].get('tokens', 0):,}")
        if base["error"]:
            print(f"  ❌ {base['error']}")

        # ── 实验（有 HDC）──
        print_sub(f"{qid} 实验（有 HDC）")
        print(f"  预期: {tc['hdc_benefit']}")
        exp = await run_agent_round(tc["question"], with_hdc=True, round_label=f"{qid}-exp")

        print_sub(f"{qid} 实验结果")
        print(f"  工具调用 ({len(exp['tool_call_names'])} 轮): {' → '.join(exp['tool_call_names']) if exp['tool_call_names'] else '(无)'}")
        print(f"  耗时: {exp['duration_ms']}ms | Token: {exp['stats'].get('tokens', 0):,}")
        if exp["error"]:
            print(f"  ❌ {exp['error']}")

        # ── 对比 ──
        delta_rounds = len(base["tool_call_names"]) - len(exp["tool_call_names"])
        delta_ms = base["duration_ms"] - exp["duration_ms"]
        improved = delta_rounds > 0 or delta_ms > 0

        print_sub(f"{qid} 对比")
        if improved:
            print(f"  ✅ HDC 更优: 减少 {delta_rounds} 轮调用, 节省 {delta_ms}ms")
        elif delta_rounds == 0:
            print(f"  ➖ 持平")
        else:
            print(f"  ❌ HDC 未产生正向收益")

        results.append({
            "test_case": tc,
            "base": base,
            "exp": exp,
            "delta_rounds": delta_rounds,
            "delta_ms": delta_ms,
            "improved": improved,
        })

    # ── 汇总报告 ──
    print_section("对比报告")

    total_base_rounds = sum(len(r["base"]["tool_call_names"]) for r in results)
    total_hdc_rounds = sum(len(r["exp"]["tool_call_names"]) for r in results)
    total_base_ms = sum(r["base"]["duration_ms"] for r in results)
    total_hdc_ms = sum(r["exp"]["duration_ms"] for r in results)
    total_base_tokens = sum(r["base"]["stats"].get("tokens", 0) or 0 for r in results)
    total_hdc_tokens = sum(r["exp"]["stats"].get("tokens", 0) or 0 for r in results)

    print(f"\n  {'问题':<6} {'基线轮次':>8} {'HDC轮次':>8} {'轮次差':>8} "
          f"{'基线耗时':>10} {'HDC耗时':>10} {'耗时差':>10} {'评估':>6}")
    print(f"  {'-'*72}")
    for r in results:
        tc = r["test_case"]
        icon = "✅" if r["improved"] else ("➖" if r["delta_rounds"] == 0 else "❌")
        print(f"  {tc['id']:<6} {len(r['base']['tool_call_names']):>4} 轮    "
              f"{len(r['exp']['tool_call_names']):>4} 轮    "
              f"{r['delta_rounds']:>+5} 轮    "
              f"{r['base']['duration_ms']:>6}ms   {r['exp']['duration_ms']:>6}ms   "
              f"{r['delta_ms']:>+7}ms   {icon:>6}")
    print(f"  {'-'*72}")
    print(f"  {'合计':<6} {total_base_rounds:>4} 轮    {total_hdc_rounds:>4} 轮    "
          f"{total_hdc_rounds - total_base_rounds:>+5} 轮    "
          f"{total_base_ms:>6}ms   {total_hdc_ms:>6}ms   "
          f"{total_hdc_ms - total_base_ms:>+7}ms")

    # ── 关键指标 ──
    print(f"\n  关键指标:")
    if total_base_rounds > 0:
        reduction = (total_base_rounds - total_hdc_rounds) / total_base_rounds * 100
        print(f"    Tool calling 轮次: {total_base_rounds} → {total_hdc_rounds} "
              f"({'减少' if reduction >= 0 else '增加'} {abs(int(reduction))}%)")
    if total_base_ms > 0:
        time_pct = (total_base_ms - total_hdc_ms) / total_base_ms * 100
        print(f"    总耗时: {total_base_ms:,}ms → {total_hdc_ms:,}ms "
              f"({'减少' if time_pct >= 0 else '增加'} {abs(int(time_pct))}%)")
    if total_base_tokens > 0:
        token_pct = (total_base_tokens - total_hdc_tokens) / total_base_tokens * 100
        print(f"    Token 消耗: {total_base_tokens:,} → {total_hdc_tokens:,} "
              f"({'减少' if token_pct >= 0 else '增加'} {abs(int(token_pct))}%)")

    # ── 每题详情 ──
    for r in results:
        tc = r["test_case"]
        base = r["base"]
        exp = r["exp"]

        print_section(f"详情 {tc['id']}: {tc['question']}")

        print(f"\n  ── 基线（无 HDC）──")
        print(f"  工具: {' → '.join(base['tool_call_names']) if base['tool_call_names'] else '(无)'}")
        for sql in base['sqls']:
            print(f"  SQL: {sql[:200]}")
        if base['thinking_texts']:
            print(f"  思考: {base['thinking_texts'][0][:200]}...")
        print(f"  耗时: {base['duration_ms']}ms | Token: {base['stats'].get('tokens', 0):,}")

        print(f"\n  ── 实验（有 HDC）──")
        if exp.get("hdc_info") and exp["hdc_info"].get("matched_tables"):
            print(f"  HDC 匹配:")
            for t in exp["hdc_info"]["matched_tables"][:5]:
                cols_str = ", ".join(t['relevant_columns'][:4])
                print(f"    • {t['table_name']} — {t['main_entity']} [{t['table_type']}]")
                if cols_str:
                    print(f"      {cols_str}")
        else:
            print(f"  HDC 匹配: (无)")
        print(f"  工具: {' → '.join(exp['tool_call_names']) if exp['tool_call_names'] else '(无)'}")
        for sql in exp['sqls']:
            print(f"  SQL: {sql[:200]}")
        if exp['thinking_texts']:
            print(f"  思考: {exp['thinking_texts'][0][:200]}...")
        print(f"  耗时: {exp['duration_ms']}ms | Token: {exp['stats'].get('tokens', 0):,}")

        # 对比分析
        print(f"\n  ── 分析 ──")
        saved = set(base['tool_call_names']) - set(exp['tool_call_names'])
        new = set(exp['tool_call_names']) - set(base['tool_call_names'])
        if saved:
            print(f"  HDC 节省的工具: {saved}")
        if new:
            print(f"  新增的工具: {new}")
        if r["improved"]:
            print(f"  ✅ HDC 有效: 减少 {r['delta_rounds']} 轮, 节省 {r['delta_ms']}ms")
        elif r["delta_rounds"] == 0:
            print(f"  ➖ 持平")
        else:
            print(f"  ❌ 无收益")

    # ── 结论 ──
    print_section("结论")
    improved_count = sum(1 for r in results if r["improved"])
    print(f"  有效题数: {improved_count}/{len(results)}")
    if total_base_rounds > 0:
        reduction = (total_base_rounds - total_hdc_rounds) / total_base_rounds * 100
        if reduction > 0:
            print(f"  🎯 HDC 将 Agent 的 tool calling 轮次减少了 {int(reduction)}%")
        elif reduction == 0:
            print(f"  ➖ 持平")
        else:
            print(f"  ⚠️ 增加了 {-int(reduction)}%")


if __name__ == "__main__":
    asyncio.run(main())
