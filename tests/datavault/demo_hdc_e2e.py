#!/usr/bin/env python3
"""
HDC 数据底座 端到端对比实验
==========================

对比同一 NL2SQL 问题，有 HDC 知识库 vs 无 HDC 基线的 Agent 表现差异。

流程：
  Phase 1: 用真实 OneDBA 数据库生成 HDC 知识库（一次性）
  Phase 2: 3 个测试问题，每个跑两轮（基线 vs 实验）
  Phase 3: 汇总对比报告

运行方式：
  cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
  python tests/datavault/demo_hdc_e2e.py [schema_id] [database_name]
"""

import asyncio
import json
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
OV_API = f"{OV_BASE_URL}/api/v1"
TEST_USER = "hdc-e2e-verify"
TEST_SESSION_PREFIX = f"hdc-{uuid.uuid4().hex[:8]}"

SETTINGS = get_settings()

TARGET_SCHEMA_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 25800743
TARGET_DB_NAME = sys.argv[2] if len(sys.argv) > 2 else "dw_onedba"

HDC_RESOURCE_BASE = f"viking://resources/hdc/{TARGET_DB_NAME}"

OV_HEADERS = {
    "Content-Type": "application/json",
    "X-OpenViking-Account": "default",
    "X-OpenViking-User": TEST_USER,
}


# ═══════════════════════════════════════════════════════════════
#  输出辅助
# ═══════════════════════════════════════════════════════════════

def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_sub(title: str):
    print(f"\n--- {title} ---")


# ═══════════════════════════════════════════════════════════════
#  OpenViking 辅助
# ═══════════════════════════════════════════════════════════════

async def ov_post(path: str, data: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=60, headers=OV_HEADERS) as c:
        r = await c.post(f"{OV_API}{path}", json=data or {})
        d = r.json()
        if d.get("status") == "error":
            print(f"  [OV ERROR] {d.get('error',{}).get('message','unknown')}")
        return d.get("result", d)


async def ov_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.get(f"{OV_API}{path}", params=params)
        return r.json()


async def ov_delete(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.request("DELETE", f"{OV_API}{path}", params=params or {})
        d = r.json()
        if d.get("status") == "error":
            print(f"  [OV ERROR] {d.get('error',{}).get('message','unknown')}")
        return d.get("result", d)


async def ov_ls(uri: str) -> list:
    raw = await ov_get("/fs/ls", {"uri": uri, "node_limit": 200})
    # ov_get returns raw JSON: {"status":"ok","result":[...]}
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if raw.get("status") == "error":
            return []
        result = raw.get("result")
        if isinstance(result, list):
            return result
    return []


# ═══════════════════════════════════════════════════════════════
#  HDC 知识库检索（用于 Step 2 实验组）
# ═══════════════════════════════════════════════════════════════

async def hdc_retrieve(question: str) -> dict[str, Any]:
    """从 HDC 知识库检索与问题相关的表和列信息。"""
    from app.datavault.retriever import HDCRetriever
    from app.knowledge.openviking import OpenVikingClient

    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    retriever = HDCRetriever(ov)
    hdc_ctx = await retriever.retrieve(question, TARGET_DB_NAME)
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
#  Agent 执行辅助
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
            print(f"    [HDC] 检索到 {hdc_info['table_count']} 张匹配表")
            for t in hdc_info["matched_tables"][:3]:
                print(f"          {t['table_name']} ({t['main_entity']}) [{t['table_type']}] "
                      f"— {len(t['relevant_columns'])} 相关列")
        else:
            print(f"    [HDC] 未检索到匹配表")
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
                trace_name=f"HDC-E2E-{round_label}",
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
                    elif step.startswith("tool:") and status == "completed":
                        pass  # tool end — already counted at start
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
        "hdc_benefit": "HDC 数据库摘要直接告诉 Agent 表数量、核心实体和业务域，"
                       "Agent 无需遍历搜索即可理解数据库全貌",
    },
    {
        "id": "Q2",
        "question": "统计一下最近创建的表的数据量",
        "expected_tools": ["execute_sql", "query_database"],
        "hdc_benefit": "HDC 表描述包含 row_count_estimate，Agent 可据此判断哪些表有数据",
    },
    {
        "id": "Q3",
        "question": "帮我看看数据库里有没有和订单相关的表，如果有的话描述一下结构",
        "expected_tools": ["find_table", "describe_table"],
        "hdc_benefit": "HDC main_entity 含同义词（如 '订单/交易/下单'），"
                       "Agent 无需关键词搜索即可直接定位订单表并获取其结构",
    },
]


# ═══════════════════════════════════════════════════════════════
#  Phase 1: 生成 HDC 知识库
# ═══════════════════════════════════════════════════════════════

async def generate_hdc_knowledge_base():
    """调用 HDCGenerator.generate() 为目标数据库生成知识库。"""
    from app.client.onedba import get_onedba_client
    from app.datavault.collector import SchemaCollector
    from app.datavault.generator import HDCGenerator
    from app.datavault.uploader import HDCUploader
    from app.knowledge.openviking import OpenVikingClient
    from openai import AsyncOpenAI

    print_section("Phase 1: 生成 HDC 知识库")
    print(f"  目标数据库: {TARGET_DB_NAME} (schemaId={TARGET_SCHEMA_ID})")
    print(f"  存储路径: {HDC_RESOURCE_BASE}")

    # 检查是否已存在
    existing = await ov_ls(HDC_RESOURCE_BASE)
    if existing and len(existing) > 0:
        print(f"\n  ⚠️  HDC 数据已存在 ({len(existing)} 个条目)")
        answer = input("  是否重新生成? [y/N] ")
        if answer.lower() != "y":
            print("  → 跳过生成，使用现有 HDC 数据\n")
            return True
        print("  → 删除旧数据...")
        await ov_delete("/fs", {"uri": HDC_RESOURCE_BASE, "recursive": "true"})
        print("  [OK] 旧数据已删除")

    print(f"\n  [Step 1/5] 采集 schema 元数据...")
    t0 = time.monotonic()

    llm = AsyncOpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.llm_base_url)
    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    onedba = get_onedba_client()

    collector = SchemaCollector(onedba)
    raw = await collector.collect_database(TARGET_SCHEMA_ID)
    total_cols = sum(len(t.columns) for t in raw.tables)
    print(f"  [OK] 采集完成: {len(raw.tables)} 张表, {total_cols} 列")

    uploader = HDCUploader(ov)
    generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)

    print(f"  [Step 2/5] 生成列摘要 (垂直分区, 每 6 列一组并行 LLM)...")
    col_start = time.monotonic()
    col_summaries = await generator.generate_column_summaries(raw.tables)
    col_elapsed = time.monotonic() - col_start
    col_count = sum(len(cs) for cs in col_summaries.values())
    print(f"  [OK] 列摘要: {col_count} 列 ({col_elapsed:.1f}s)")

    print(f"  [Step 3/5] 生成表描述 (每表一次 LLM, 表间并行)...")
    tbl_start = time.monotonic()
    table_descs = await generator.generate_table_descriptions(raw.tables, col_summaries)
    tbl_elapsed = time.monotonic() - tbl_start
    print(f"  [OK] 表描述: {len(table_descs)} 张表 ({tbl_elapsed:.1f}s)")
    for td in table_descs[:5]:
        print(f"       {td.table_name} → main_entity=\"{td.main_entity}\" [{td.table_type}]")

    print(f"  [Step 4/5] 生成表关系 (两阶段: OpenViking 粗筛 → LLM 细筛)...")
    rel_start = time.monotonic()
    relationships = await generator.generate_relationships(TARGET_DB_NAME, table_descs, col_summaries)
    rel_elapsed = time.monotonic() - rel_start
    print(f"  [OK] 表关系: {len(relationships)} 条 ({rel_elapsed:.1f}s)")

    print(f"  [Step 5/5] 生成数据库摘要 + 上传到 OpenViking...")
    db_start = time.monotonic()
    db_summary = await generator.generate_database_summary(TARGET_DB_NAME, table_descs, relationships)
    from app.datavault.models import TableDescriptionWithColumns
    tbl_with_cols = []
    for td in table_descs:
        tdc = TableDescriptionWithColumns(
            table_name=td.table_name,
            main_entity=td.main_entity,
            table_type=td.table_type,
            primary_key=td.primary_key,
            key_attributes=td.key_attributes,
            description=td.description,
            row_count_estimate=td.row_count_estimate,
            columns=col_summaries.get(td.table_name, []),
        )
        tbl_with_cols.append(tdc)
    await uploader.upload_database(TARGET_DB_NAME, db_summary, tbl_with_cols, relationships)
    db_elapsed = time.monotonic() - db_start
    print(f"  [OK] 上传完成 ({db_elapsed:.1f}s)")
    print(f"       数据库摘要: {db_summary.domain_hint} — {db_summary.description[:80]}...")

    total_elapsed = time.monotonic() - t0

    # 验证
    entries = await ov_ls(HDC_RESOURCE_BASE)
    table_dirs = [e for e in (entries or []) if e.get("isDir")]
    print(f"\n  生成结果汇总:")
    print(f"    表总数: {len(raw.tables)}")
    print(f"    列摘要: {col_count}")
    print(f"    表描述: {len(table_descs)}")
    print(f"    表关系: {len(relationships)}")
    print(f"    总耗时: {total_elapsed:.1f}s")
    print(f"    OpenViking 验证: {len(entries or [])} 个条目, {len(table_dirs)} 个子目录")

    await ov.close()
    return True


# ═══════════════════════════════════════════════════════════════
#  Phase 2: 对比实验
# ═══════════════════════════════════════════════════════════════

async def run_all_tests():
    """执行全部 3 个问题的基线 vs 实验对比。"""
    results = []

    for i, tc in enumerate(TEST_QUESTIONS):
        qid = tc["id"]
        print_section(f"Phase 2.{i+1}: {qid} — {tc['question']}")

        # ── 基线（无 HDC）──
        print_sub(f"{qid} 基线（无 HDC）")
        print(f"  HDC 状态: 关闭")
        print(f"  Agent 仅靠自身能力发现表结构")
        base = await run_agent_round(tc["question"], with_hdc=False, round_label=f"{qid}-baseline")

        print_sub(f"{qid} 基线结果")
        print(f"  工具调用 ({len(base['tool_call_names'])} 轮): {base['tool_call_names']}")
        print(f"  生成 SQL: {len(base['sqls'])} 条")
        print(f"  耗时: {base['duration_ms']}ms")
        print(f"  Token 消耗: {base['stats'].get('tokens', 0):,}")
        if base["error"]:
            print(f"  ❌ 错误: {base['error']}")

        # ── 实验（有 HDC）──
        print_sub(f"{qid} 实验（有 HDC）")
        print(f"  HDC 状态: 开启")
        print(f"  预期收益: {tc['hdc_benefit']}")
        exp = await run_agent_round(tc["question"], with_hdc=True, round_label=f"{qid}-experiment")

        print_sub(f"{qid} 实验结果")
        print(f"  工具调用 ({len(exp['tool_call_names'])} 轮): {exp['tool_call_names']}")
        print(f"  生成 SQL: {len(exp['sqls'])} 条")
        print(f"  耗时: {exp['duration_ms']}ms")
        print(f"  Token 消耗: {exp['stats'].get('tokens', 0):,}")
        if exp["error"]:
            print(f"  ❌ 错误: {exp['error']}")

        # ── 对比 ──
        delta_rounds = base["tool_call_names"] and len(base["tool_call_names"]) - len(exp["tool_call_names"]) or 0
        delta_ms = base["duration_ms"] - exp["duration_ms"]
        delta_tokens = (base["stats"].get("tokens", 0) or 0) - (exp["stats"].get("tokens", 0) or 0)

        improved = delta_rounds > 0 or delta_ms > 0
        icon = "✅" if improved else ("➖" if delta_rounds == 0 else "❌")

        print_sub(f"{qid} 对比 ({icon} {'HDC 更优' if improved else '持平/更差'})")
        print(f"  轮次差: {'-' if delta_rounds >= 0 else '+'}{abs(delta_rounds)} 轮")
        print(f"  耗时差: {'-' if delta_ms >= 0 else '+'}{abs(delta_ms)}ms")
        if delta_tokens != 0:
            print(f"  Token 差: {'-' if delta_tokens >= 0 else '+'}{abs(delta_tokens):,}")

        results.append({
            "test_case": tc,
            "base": base,
            "exp": exp,
            "delta_rounds": delta_rounds,
            "delta_ms": delta_ms,
            "delta_tokens": delta_tokens,
            "improved": improved,
        })

    return results


# ═══════════════════════════════════════════════════════════════
#  Phase 3: 报告
# ═══════════════════════════════════════════════════════════════

def print_report(results: list[dict]):
    """输出完整对比报告。"""
    print_section("Phase 3: 对比报告")

    # ── 总览表 ──
    print(f"\n{'='*70}")
    print(f"  对比总览")
    print(f"{'='*70}")
    print(f"  {'问题':<6} {'基线轮次':>8} {'HDC轮次':>8} {'轮次差':>8} "
          f"{'基线耗时':>10} {'HDC耗时':>10} {'耗时差':>10} {'评估':>6}")
    print(f"  {'-'*72}")

    total_base_rounds = 0
    total_hdc_rounds = 0
    total_base_ms = 0
    total_hdc_ms = 0
    total_base_tokens = 0
    total_hdc_tokens = 0

    for r in results:
        tc = r["test_case"]
        base = r["base"]
        exp = r["exp"]
        icon = "✅" if r["improved"] else "➖"

        print(f"  {tc['id']:<6} {len(base['tool_call_names']):>4} 轮    "
              f"{len(exp['tool_call_names']):>4} 轮    "
              f"{r['delta_rounds']:>+5} 轮    "
              f"{base['duration_ms']:>6}ms   {exp['duration_ms']:>6}ms   "
              f"{r['delta_ms']:>+7}ms   {icon:>6}")

        total_base_rounds += len(base["tool_call_names"])
        total_hdc_rounds += len(exp["tool_call_names"])
        total_base_ms += base["duration_ms"]
        total_hdc_ms += exp["duration_ms"]
        total_base_tokens += base["stats"].get("tokens", 0) or 0
        total_hdc_tokens += exp["stats"].get("tokens", 0) or 0

    print(f"  {'-'*72}")
    print(f"  {'合计':<6} {total_base_rounds:>4} 轮    {total_hdc_rounds:>4} 轮    "
          f"{total_hdc_rounds - total_base_rounds:>+5} 轮    "
          f"{total_base_ms:>6}ms   {total_hdc_ms:>6}ms   "
          f"{total_hdc_ms - total_base_ms:>+7}ms")

    # ── 关键指标 ──
    print(f"\n{'='*70}")
    print(f"  关键指标")
    print(f"{'='*70}")

    if total_base_rounds > 0:
        reduction = (total_base_rounds - total_hdc_rounds) / total_base_rounds * 100
        print(f"  Tool calling 轮次: {total_base_rounds} → {total_hdc_rounds} "
              f"({'减少' if reduction >= 0 else '增加'} {abs(int(reduction))}%)")
    if total_base_ms > 0:
        time_diff = total_base_ms - total_hdc_ms
        time_pct = time_diff / total_base_ms * 100
        print(f"  总耗时: {total_base_ms:,}ms → {total_hdc_ms:,}ms "
              f"({'减少' if time_diff >= 0 else '增加'} {abs(int(time_pct)):.0f}%)")
    if total_base_tokens > 0:
        token_diff = total_base_tokens - total_hdc_tokens
        token_pct = token_diff / total_base_tokens * 100
        print(f"  Token 消耗: {total_base_tokens:,} → {total_hdc_tokens:,} "
              f"({'减少' if token_diff >= 0 else '增加'} {abs(int(token_pct)):.0f}%)")

    # ── 每题详细结果 ──
    for r in results:
        tc = r["test_case"]
        base = r["base"]
        exp = r["exp"]

        print_section(f"详情 {tc['id']}: {tc['question']}")

        print(f"\n  ── 预期 HDC 收益 ──")
        print(f"  {tc['hdc_benefit']}")

        print(f"\n  ── 基线（无 HDC）──")
        print(f"  工具调用序列: {' → '.join(base['tool_call_names']) if base['tool_call_names'] else '(无)'}")
        print(f"  生成 SQL: {len(base['sqls'])} 条")
        for sql in base['sqls']:
            print(f"    {sql[:200]}")
        print(f"  耗时: {base['duration_ms']}ms | Token: {base['stats'].get('tokens', 0):,}")
        if base['thinking_texts']:
            print(f"  LLM 思考摘要: {base['thinking_texts'][0][:200]}...")
        if base["error"]:
            print(f"  ❌ 错误: {base['error']}")

        print(f"\n  ── 实验（有 HDC）──")
        if exp.get("hdc_info") and exp["hdc_info"].get("matched_tables"):
            hi = exp["hdc_info"]
            print(f"  HDC 检索: {hi['table_count']} 张匹配表")
            for t in hi["matched_tables"][:5]:
                print(f"    • {t['table_name']} — {t['main_entity']} [{t['table_type']}]")
                if t['relevant_columns']:
                    print(f"      相关列: {', '.join(t['relevant_columns'][:6])}")
        else:
            print(f"  HDC 检索: 未匹配到表")
        print(f"  工具调用序列: {' → '.join(exp['tool_call_names']) if exp['tool_call_names'] else '(无)'}")
        print(f"  生成 SQL: {len(exp['sqls'])} 条")
        for sql in exp['sqls']:
            print(f"    {sql[:200]}")
        print(f"  耗时: {exp['duration_ms']}ms | Token: {exp['stats'].get('tokens', 0):,}")
        if exp['thinking_texts']:
            print(f"  LLM 思考摘要: {exp['thinking_texts'][0][:200]}...")
        if exp["error"]:
            print(f"  ❌ 错误: {exp['error']}")

        # 对比分析
        print(f"\n  ── 对比分析 ──")
        base_tools = set(base['tool_call_names'])
        exp_tools = set(exp['tool_call_names'])
        saved_tools = base_tools - exp_tools
        if saved_tools:
            print(f"  HDC 节省的工具: {saved_tools}")
        new_tools = exp_tools - base_tools
        if new_tools:
            print(f"  新增的工具: {new_tools}")
        if r["improved"]:
            print(f"  ✅ HDC 有效: 减少 {r['delta_rounds']} 轮调用, 节省 {r['delta_ms']}ms")
        elif r["delta_rounds"] == 0:
            print(f"  ➖ 持平: 两轮表现相同")
        else:
            print(f"  ❌ 本轮 HDC 未产生正向收益")

    # ── 资源消耗汇总 ──
    print_section("资源消耗汇总")
    print(f"  总 Token 消耗 — 基线: {total_base_tokens:,} | HDC: {total_hdc_tokens:,}")
    print(f"  总耗时 — 基线: {total_base_ms:,}ms | HDC: {total_hdc_ms:,}ms")
    print(f"  总工具调用 — 基线: {total_base_rounds} 次 | HDC: {total_hdc_rounds} 次")
    print(f"  平均耗时/题 — 基线: {total_base_ms/len(results):,.0f}ms | "
          f"HDC: {total_hdc_ms/len(results):,.0f}ms")

    # ── 结论 ──
    print_section("结论")
    improved_count = sum(1 for r in results if r["improved"])
    print(f"  有效题数: {improved_count}/{len(results)}")
    if total_base_rounds > 0:
        reduction = (total_base_rounds - total_hdc_rounds) / total_base_rounds * 100
        if reduction > 0:
            print(f"  🎯 HDC 将 Agent 的 tool calling 轮次减少了 {int(reduction)}%")
            print(f"     （从 {total_base_rounds} 轮降到 {total_hdc_rounds} 轮）")
        elif reduction == 0:
            print(f"  ➖ HDC 未显著改变 tool calling 轮次（持平）")
        else:
            print(f"  ⚠️ HDC 增加了 tool calling 轮次（可能因为测试问题不适合当前数据库）")
    print(f"  核心价值: 让 Agent 直接理解数据库的业务语义，跳过表名猜测和字段含义推理环节")


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 70)
    print("  HDC 数据底座 端到端对比实验")
    print("=" * 70)
    print(f"  目标数据库: {TARGET_DB_NAME} (schemaId={TARGET_SCHEMA_ID})")
    print(f"  OpenViking: {OV_BASE_URL}")
    print(f"  LLM: {SETTINGS.llm_model}")
    print(f"  测试问题数: {len(TEST_QUESTIONS)}")
    print(f"  对比方式: 每问题两轮 — 基线（无 HDC） vs 实验（有 HDC）")
    print()

    # Phase 1: 生成 HDC 知识库
    ok = await generate_hdc_knowledge_base()
    if not ok:
        print("[ERROR] HDC 知识库生成失败，终止")
        return

    # Phase 2: 对比实验
    results = await run_all_tests()

    # Phase 3: 报告
    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())
