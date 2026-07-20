#!/usr/bin/env python3
"""
HDC 数据底座 端到端对比实验
==========================

对比同一 NL2SQL 问题，有 HDC 知识库 vs 无 HDC 基线的 Agent 表现差异。

流程：
  1. 用真实 OneDBA 数据库生成 HDC 知识库（一次性）
  2. 跑 3 个测试问题，每个问题跑两轮：
     - 基线：HDC 关闭，Agent 正常发现表
     - 实验：HDC 开启，Agent 上下文注入表语义
  3. 对比：tool calling 轮次、token 消耗、延迟

前置条件：
  - OpenViking Server 运行在 localhost:1933
  - OneDBA 可访问（通过 .env 配置）
  - LLM 可访问（通过 .env 配置）

运行方式：
  cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
  python tests/datavault/demo_hdc_e2e.py [schema_id] [database_name]

  可选参数：
    schema_id     — OneDBA schema ID，默认 25800743 (dw_onedba)
    database_name — 库名（用于 HDC 目录命名），默认 "dw_onedba"
"""

import asyncio
import json
import os
import sys
import time
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
OV_HEADERS = {
    "Content-Type": "application/json",
    "X-OpenViking-Account": "default",
    "X-OpenViking-User": TEST_USER,
}

SETTINGS = get_settings()

TARGET_SCHEMA_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 25800743
TARGET_DB_NAME = sys.argv[2] if len(sys.argv) > 2 else "dw_onedba"

HDC_RESOURCE_BASE = f"viking://resources/hdc/{TARGET_DB_NAME}"

print(f"⚙️  目标数据库: schemaId={TARGET_SCHEMA_ID}, name={TARGET_DB_NAME}")
print(f"⚙️  OpenViking: {OV_BASE_URL}")
print(f"⚙️  LLM: {SETTINGS.llm_model}")


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


async def ov_delete(path: str, params: dict = None) -> dict:
    """DELETE 请求"""
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.request("DELETE", f"{OV_API}{path}", params=params or {})
        d = r.json()
        if d.get("status") == "error":
            print(f"  [OV ERROR] {d.get('error',{}).get('message','unknown')}")
        return d.get("result", d)


async def ov_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.get(f"{OV_API}{path}", params=params)
        return r.json()


async def ov_ls(uri: str) -> list:
    result = await ov_get("/fs/ls", {"uri": uri, "node_limit": 200})
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and result.get("status") == "error":
        return []  # 目录不存在
    return []


# ═══════════════════════════════════════════════════════════════
#  Step 1: 生成 HDC 知识库
# ═══════════════════════════════════════════════════════════════

async def generate_hdc_knowledge_base():
    """调用 HDCGenerator.generate() 为目标数据库生成知识库。"""
    from app.client.onedba import get_onedba_client
    from app.datavault.collector import SchemaCollector
    from app.datavault.generator import HDCGenerator
    from app.datavault.uploader import HDCUploader
    from app.knowledge.openviking import OpenVikingClient
    from openai import AsyncOpenAI

    print("\n" + "=" * 70)
    print("  Step 1: 生成 HDC 知识库")
    print("=" * 70)

    # 检查是否已存在
    existing = await ov_ls(HDC_RESOURCE_BASE)
    if existing and len(existing) > 0:
        print(f"  ⚠️  HDC 数据已存在: {HDC_RESOURCE_BASE}")
        print(f"     已有 {len(existing)} 个条目")
        answer = input("  是否重新生成? [y/N] ")
        if answer.lower() != "y":
            print("  跳过生成，使用现有 HDC 数据")
            return
        print("  删除旧数据...")
        await ov_delete("/fs", {"uri": HDC_RESOURCE_BASE, "recursive": "true"})

    print(f"  正在为 {TARGET_DB_NAME} (schemaId={TARGET_SCHEMA_ID}) 生成 HDC...")

    llm = AsyncOpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.llm_base_url)
    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    onedba = get_onedba_client()

    collector = SchemaCollector(onedba)
    uploader = HDCUploader(ov)
    generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)

    t0 = time.monotonic()
    stats = await generator.generate(TARGET_SCHEMA_ID, TARGET_DB_NAME)
    elapsed = time.monotonic() - t0

    print(f"\n  生成结果:")
    print(f"    状态: {stats.get('status', 'unknown')}")
    print(f"    表总数: {stats.get('tables_total', 0)}")
    print(f"    成功: {stats.get('tables_succeeded', 0)}")
    print(f"    列摘要: {stats.get('columns', 0)}")
    print(f"    关系: {stats.get('relationships', 0)}")
    print(f"    耗时: {elapsed:.1f}s")
    if stats.get("errors"):
        for err in stats["errors"][:5]:
            print(f"    错误: {err}")

    entries = await ov_ls(HDC_RESOURCE_BASE)
    table_count = sum(1 for e in (entries or []) if e.get("isDir"))
    print(f"    OpenViking 验证: {len(entries or [])} 个条目, {table_count} 个子目录")

    await ov.close()


# ═══════════════════════════════════════════════════════════════
#  Step 2: 跑对比实验
# ═══════════════════════════════════════════════════════════════

# 测试问题（不包含任何表名/字段名提示，纯自然语言）
TEST_QUESTIONS = [
    "帮我查一下这个数据库里有哪些表",
    "统计一下最近创建的表的数据量",
    "帮我看看数据库里有没有和订单相关的表，如果有的话描述一下结构",
]


async def run_one_round(
    question: str,
    with_hdc: bool,
    round_label: str,
) -> dict[str, Any]:
    """执行一轮 Agent 对话，收集指标。"""
    from app.agent.runner import run_agent_stream

    session_state = {
        "user_input": question,
        "user_id": TEST_USER,
        "session_id": f"hdc-e2e-{int(time.time())}",
    }

    # 设置数据库上下文
    session_state["selected_database"] = {"schemaName": TARGET_DB_NAME}
    session_state["selected_schema_id"] = TARGET_SCHEMA_ID

    # ── HDC 检索 ──
    if with_hdc:
        try:
            from app.datavault.retriever import HDCRetriever
            from app.knowledge.openviking import OpenVikingClient
            ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
            await ov.start()
            retriever = HDCRetriever(ov)
            hdc_ctx = await retriever.retrieve(question, TARGET_DB_NAME)
            if hdc_ctx:
                session_state["_hdc_context"] = retriever.format_context(hdc_ctx)
            await ov.close()
        except Exception as e:
            print(f"    [HDC] 检索失败: {e}")

    # ── 执行 Agent ──
    tool_calls = []
    t0 = time.monotonic()
    final_response = ""

    try:
        async for event_type, data in run_agent_stream(question, session_state):
            if event_type == "step" and "tool:" in data.get("step", ""):
                if data.get("status") == "running":
                    tool_name = data["step"].replace("tool:", "")
                    tool_calls.append({"tool": tool_name, "start": time.monotonic() - t0})
            elif event_type == "final":
                final_response = data.get("response", "")[:500]
    except Exception as e:
        print(f"    [Agent] 执行出错: {e}")
        final_response = f"ERROR: {e}"

    elapsed_ms = (time.monotonic() - t0) * 1000

    return {
        "label": round_label,
        "with_hdc": with_hdc,
        "tool_rounds": len(tool_calls),
        "tools_used": [tc["tool"] for tc in tool_calls],
        "elapsed_ms": int(elapsed_ms),
        "response_preview": final_response[:200],
    }


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

async def main():
    # Step 1: 生成 HDC 知识库
    await generate_hdc_knowledge_base()

    # Step 2: 对比实验
    print("\n" + "=" * 70)
    print("  Step 2: 对比实验（有 HDC vs 无 HDC）")
    print("=" * 70)

    results = []

    for i, question in enumerate(TEST_QUESTIONS):
        print(f"\n  ── 问题 {i+1}: {question} ──")

        # 基线（无 HDC）
        print(f"    基线（无 HDC）...")
        base = await run_one_round(question, with_hdc=False, round_label=f"Q{i+1}-baseline")
        print(f"      轮次: {base['tool_rounds']} | 工具: {base['tools_used']} | 耗时: {base['elapsed_ms']}ms")

        # 实验（有 HDC）
        print(f"    实验（有 HDC）...")
        exp = await run_one_round(question, with_hdc=True, round_label=f"Q{i+1}-experiment")
        print(f"      轮次: {exp['tool_rounds']} | 工具: {exp['tools_used']} | 耗时: {exp['elapsed_ms']}ms")

        results.append((question, base, exp))

    # ── 汇总 ──
    print("\n" + "=" * 70)
    print("  对比结果汇总")
    print("=" * 70)

    print(f"\n  {'问题':<40s} {'基线轮次':>8s} {'HDC轮次':>8s} {'基线耗时':>10s} {'HDC耗时':>10s}")
    print(f"  {'-'*76}")

    total_base_rounds = 0
    total_hdc_rounds = 0
    total_base_ms = 0
    total_hdc_ms = 0

    for question, base, exp in results:
        short_q = question[:38] + "…" if len(question) > 39 else question
        print(f"  {short_q:<40s} {base['tool_rounds']:>4} 轮    {exp['tool_rounds']:>4} 轮    {base['elapsed_ms']:>6}ms    {exp['elapsed_ms']:>6}ms")
        total_base_rounds += base["tool_rounds"]
        total_hdc_rounds += exp["tool_rounds"]
        total_base_ms += base["elapsed_ms"]
        total_hdc_ms += exp["elapsed_ms"]

    print(f"  {'-'*76}")
    print(f"  {'合计':<40s} {total_base_rounds:>4} 轮    {total_hdc_rounds:>4} 轮    {total_base_ms:>6}ms    {total_hdc_ms:>6}ms")

    if total_base_rounds > 0:
        reduction = (total_base_rounds - total_hdc_rounds) / total_base_rounds * 100
        print(f"\n  🎯 Tool calling 轮次减少: {int(reduction)}%")
    if total_base_ms > 0:
        time_saved = (total_base_ms - total_hdc_ms) / total_base_ms * 100
        print(f"  🎯 总耗时减少: {int(time_saved)}%")


if __name__ == "__main__":
    asyncio.run(main())
