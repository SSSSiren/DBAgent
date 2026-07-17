#!/usr/bin/env python3
"""
OneDBA FAQ 知识库 RAG 验证脚本
==============================

验证思路：将 OneDBA常见问题汇总.md 作为 RAG 知识库，准备 5 个典型问题，
测试 Agent 能否正确借用知识库内容回答。通过对答案的关键词匹配打分。

知识库：
  OneDBA常见问题汇总/OneDBA常见问题汇总.md

运行方式：
  cd /Users/admin/DBR/VK-DBAgent
  python tests/verify_rag_faq.py

前置条件：
  - OpenViking Server 运行在 localhost:1933
  - LLM 可访问（通过 .env 配置）
"""

import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 服务地址 ──
OV_BASE_URL = "http://localhost:1933"
OV_API = f"{OV_BASE_URL}/api/v1"

# ── 测试标识 ──
TEST_USER = "vkdb-faq-verify"
TEST_SESSION_PREFIX = f"faq-{uuid.uuid4().hex[:8]}"

# ── 知识库 ──
RESOURCE_URI = "viking://resources/onedba-faq"
RESOURCE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "OneDBA常见问题汇总", "OneDBA常见问题汇总.md"
)

OV_HEADERS = {
    "Content-Type": "application/json",
    "X-OpenViking-Account": "default",
    "X-OpenViking-User": TEST_USER,
}

# ================================================================
#  5 个测试问题 + 参考答案（关键词）
# ================================================================

TEST_CASES = [
    {
        "id": "Q1",
        "question": "为什么我在OneDBA上创建数据变更工单时选不到数据库？",
        "reference": "需要有数据库的变更权限才能选到数据库。对于导出工单需要有导出权限。结构设计工单只能以开发环境数据库为基准库。",
        "keywords": [
            "变更权限", "导出权限", "结构设计", "开发环境", "基准库",
        ],
        "must_have": ["变更权限"],  # 至少命中一个
    },
    {
        "id": "Q2",
        "question": "OneDBA上还能管理Redis吗？如果不能，应该去哪里管理？",
        "reference": "Redis已经从DBA组移交到中间件负责维护，OneDBA相关Redis功能已下线。Redis相关功能在架构云支持，地址 middleware.dewu-inc.com。",
        "keywords": [
            "Redis", "下线", "中间件", "架构云", "middleware",
        ],
        "must_have": ["下线", "中间件"],
    },
    {
        "id": "Q3",
        "question": "在结构设计工单中，删除了表但测试环境没有被删除，应该怎么处理？",
        "reference": "需要提普通数据变更工单对测试环境进行删除表，工单描述清楚'结构设计中新建表删除后无法带到测试节点，提工单删除'。",
        "keywords": [
            "普通数据变更", "删除表", "测试环境", "测试节点", "工单",
        ],
        "must_have": ["普通数据变更"],
    },
    {
        "id": "Q4",
        "question": "我想成为某个数据库的Owner，有哪些方式？",
        "reference": "两种方式：1. 通过权限工单申请成为数据库Owner；2. 让当前数据库Owner手动添加你为Owner。在'工作台'页面可以查看我Owner的库表。",
        "keywords": [
            "权限工单", "申请", "Owner", "手动添加", "工作台",
        ],
        "must_have": ["权限工单", "Owner"],
    },
    {
        "id": "Q5",
        "question": "执行变更后，在查询窗口看不到最新的表结构，怎么解决？",
        "reference": "可以尝试点击'同步元数据'。查询窗口左侧的表信息非实时从数据库拉取，而是OneDBA最近一次收集的元数据信息。对于逻辑库变更，只有在整个工单结束后才会更新元数据。",
        "keywords": [
            "同步元数据", "非实时", "元数据", "收集", "逻辑库", "工单结束",
        ],
        "must_have": ["同步元数据"],
    },
]


# ================================================================
#  输出辅助
# ================================================================

def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_sub(title: str):
    print(f"\n--- {title} ---")


# ================================================================
#  OpenViking 辅助函数
# ================================================================

async def ov_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.get(f"{OV_API}{path}", params=params)
        return r.json()


async def ov_post(path: str, data: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.post(f"{OV_API}{path}", json=data)
        return r.json()


async def ov_upload_file(path: str, filename: str) -> dict:
    with open(path, "rb") as f:
        async with httpx.AsyncClient(
            timeout=120,
            headers={"X-OpenViking-Account": "default", "X-OpenViking-User": TEST_USER},
        ) as c:
            r = await c.post(
                f"{OV_API}/resources/temp_upload",
                files={"file": (filename, f, "text/markdown")},
            )
            return r.json()


async def ov_delete_resource(uri: str) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.delete(f"{OV_API}/resources?uri={uri}")
        return r.json()


# ================================================================
#  RAG 检索
# ================================================================

async def rag_search(question: str) -> list[dict[str, str]]:
    """从知识库检索与问题相关的内容，返回 RAG 上下文列表"""
    search = await ov_post("/search/find", {
        "query": question,
        "target_uri": "viking://resources/",
        "context_type": "resource",
        "limit": 3,
    })
    resources = search.get("result", {}).get("resources", [])
    print(f"    检索到 {len(resources)} 条资源")

    rag_context: list[dict[str, str]] = []
    for i, r in enumerate(resources[:3]):
        uri = r.get("uri", "")
        score = r.get("score", 0)
        print(f"    [{i+1}] score={score:.4f} {uri}")

        try:
            read = await ov_get("/content/read", {"uri": uri, "limit": 200})
            full = read.get("result", "")
            if isinstance(full, dict):
                full = full.get("content", str(full))
        except Exception:
            full = ""

        content = str(full) if full else ""
        # 过滤空行和纯标题行
        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
        clean = "\n".join(lines)[:3000]

        rag_context.append({
            "category": "knowledge_base",
            "abstract": (
                f"[OneDBA FAQ 知识库 — 检索第{i+1}条, 相关性={score:.4f}] "
                f"{clean[:1000]}"
            ),
            "name": uri,
            "_raw_content": clean[:2000],
        })

    return rag_context


# ================================================================
#  Agent 执行辅助
# ================================================================

async def run_agent_with_rag(
    question: str,
    rag_context: list[dict[str, str]],
    round_label: str,
) -> dict[str, Any]:
    """Agent 携带 RAG 上下文执行回答"""
    from app.agent.runner import run_agent_stream
    from app.config import get_settings

    settings = get_settings()
    original_kb = settings.kb_enabled
    original_pref = settings.preference_enabled
    settings.kb_enabled = True
    settings.preference_enabled = False

    try:
        tool_call_names: list[str] = []
        sqls: list[str] = []
        final_response = ""
        stats: dict[str, Any] = {}
        error: str | None = None

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-{round_label}",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
        }

        # ── 检索长期记忆 + 注入 RAG ──
        try:
            from app.knowledge.openviking import OpenVikingClient
            kb = OpenVikingClient(settings.kb_openviking_url, TEST_USER)
            await kb.start()
            memories = await kb.retrieve_memories()
            await kb.close()
            if memories:
                session_state["_memories"] = memories
            if rag_context:
                session_state["_rag_reference"] = rag_context
                print(f"    [RAG] 注入 {len(rag_context)} 条知识库上下文")
        except Exception as e:
            print(f"    [KB] 检索失败: {type(e).__name__}: {e}")

        start_time = time.monotonic()

        try:
            async with asyncio.timeout(120):
                async for event_type, data in run_agent_stream(
                    question, session_state, trace_name=f"FAQ-RAG-{round_label}"
                ):
                    if event_type == "step":
                        step = data.get("step", "")
                        status = data.get("status", "")
                        if step.startswith("tool:") and status == "running":
                            tool_name = step.replace("tool:", "")
                            tool_call_names.append(tool_name)
                            print(f"    [Tool] {tool_name}")
                    elif event_type == "sql":
                        sql_text = data.get("sql", "")
                        if sql_text:
                            sqls.append(sql_text)
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
            "stats": stats,
            "duration_ms": duration_ms,
            "error": error,
        }
    finally:
        settings.kb_enabled = original_kb
        settings.preference_enabled = original_pref


# ================================================================
#  评分
# ================================================================

def score_answer(answer: str, test_case: dict) -> dict:
    """基于关键词匹配打分"""
    answer_lower = answer.lower()
    keywords = test_case["keywords"]
    must_have = test_case["must_have"]

    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    missing = [kw for kw in keywords if kw.lower() not in answer_lower]
    must_hit = [kw for kw in must_have if kw.lower() in answer_lower]
    must_miss = [kw for kw in must_have if kw.lower() not in answer_lower]

    kw_score = len(matched) / len(keywords) if keywords else 0
    must_score = len(must_hit) / len(must_have) if must_have else 1.0

    # 综合分：关键项权重 60%，关键词覆盖率 40%
    final_score = round(must_score * 60 + kw_score * 40, 1)

    return {
        "score": final_score,
        "kw_hit_rate": f"{len(matched)}/{len(keywords)}",
        "matched": matched,
        "missing": missing,
        "must_hit": must_hit,
        "must_miss": must_miss,
    }


# ================================================================
#  主验证流程
# ================================================================

async def upload_knowledge_base():
    """上传 OneDBA FAQ 到 OpenViking resources"""
    print_section("Phase 1: 上传知识库")

    if not os.path.exists(RESOURCE_FILE):
        print(f"[ERROR] 文件不存在: {RESOURCE_FILE}")
        return False

    # 先删除旧资源（确保每次都是最新内容）
    try:
        await ov_delete_resource(RESOURCE_URI)
        print(f"[INFO] 已删除旧资源")
    except Exception:
        pass

    print(f"[INFO] 上传: {RESOURCE_FILE}")
    upload = await ov_upload_file(RESOURCE_FILE, "OneDBA常见问题汇总.md")
    temp_id = upload.get("result", {}).get("temp_file_id", "")

    if not temp_id:
        print(f"[ERROR] 上传失败: {json.dumps(upload, ensure_ascii=False)[:300]}")
        return False

    create = await ov_post("/resources", {
        "temp_file_id": temp_id,
        "to": RESOURCE_URI,
        "reason": "RAG 验证 — OneDBA 常见问题汇总",
        "instruction": (
            "OneDBA 平台常见问题汇总。涵盖工单使用、数据库权限、"
            "结构设计、Redis 下线、元数据同步、数据库 Owner 管理等常见问题。"
        ),
        "wait": True,
        "timeout": 120,
    })
    if create.get("status") == "ok":
        print(f"[OK] 资源已创建: {RESOURCE_URI}")
        return True
    else:
        print(f"[WARN] 创建结果: {json.dumps(create, ensure_ascii=False)[:300]}")
        return False


async def run_all_tests():
    """执行全部 5 个问题的测试"""
    results = []

    for i, tc in enumerate(TEST_CASES):
        qid = tc["id"]
        print_section(f"Phase 2.{i+1}: {qid} — {tc['question'][:40]}...")

        # Step 1: RAG 检索
        print_sub("RAG 检索")
        rag_context = await rag_search(tc["question"])

        # Step 2: Agent 回答
        print_sub("Agent 回答")
        start = time.monotonic()
        agent_result = await run_agent_with_rag(tc["question"], rag_context, qid)
        elapsed = int((time.monotonic() - start) * 1000)

        # Step 3: 评分
        score = score_answer(agent_result["response"], tc)

        print_sub(f"{qid} 结果")
        print(f"  回答长度: {len(agent_result['response'])} chars")
        print(f"  耗时: {agent_result['duration_ms']}ms")
        print(f"  工具调用: {agent_result['tool_call_names']}")
        print(f"  得分: {score['score']}/100")
        print(f"  关键词命中: {score['kw_hit_rate']} → {score['matched']}")
        if score['must_miss']:
            print(f"  ❌ 关键项缺失: {score['must_miss']}")
        if score['missing']:
            print(f"  ⚠️ 未命中: {score['missing']}")

        results.append({
            "test_case": tc,
            "rag_context": rag_context,
            "agent_result": agent_result,
            "score": score,
        })

    return results


def print_report(results: list[dict]):
    """输出完整报告"""
    print_section("Phase 3: 验证报告")

    # ── 各题得分总览 ──
    print(f"\n{'='*70}")
    print(f"  各题得分总览")
    print(f"{'='*70}")
    print(f"  {'问题':<6} {'得分':>6} {'关键词命中':>14} {'是否合格':>10}")
    print(f"  {'-'*40}")
    total_score = 0
    for r in results:
        tc = r["test_case"]
        sc = r["score"]
        passed = "✅" if sc["score"] >= 60 else "❌"
        print(f"  {tc['id']:<6} {sc['score']:>5.0f}/100  {sc['kw_hit_rate']:>14}  {passed:>10}")
        total_score += sc["score"]

    avg = total_score / len(results) if results else 0
    print(f"  {'-'*40}")
    print(f"  {'平均':<6} {avg:>5.1f}/100")
    print(f"  合格率: {sum(1 for r in results if r['score']['score'] >= 60)}/{len(results)}")

    # ── 每题详细信息 ──
    for i, r in enumerate(results):
        tc = r["test_case"]
        agent = r["agent_result"]
        sc = r["score"]

        print_section(f"详情 {tc['id']}: {tc['question']}")

        # 参考答案
        print(f"\n  ── 参考答案（来自知识库）──")
        print(f"  {tc['reference']}")

        # RAG 检索到的原文
        print(f"\n  ── RAG 检索到的知识库原文 ──")
        for j, rag in enumerate(r["rag_context"]):
            raw = rag.get("_raw_content", "")
            print(f"  [检索 #{j+1}] {rag.get('name', '?')}")
            print(f"  {raw[:800]}")
            if len(raw) > 800:
                print(f"  ... (共 {len(raw)} chars，已截断)")

        # Agent 回答
        print(f"\n  ── Agent 回答 ({len(agent['response'])} chars, {agent['duration_ms']}ms) ──")
        print(f"  {agent['response']}")
        if agent["error"]:
            print(f"  ❌ 错误: {agent['error']}")

        # 评分明细
        print(f"\n  ── 评分明细 ──")
        print(f"  得分: {sc['score']}/100")
        print(f"  关键词: {sc['matched']} 命中, {sc['missing']} 未命中")
        if sc["must_miss"]:
            print(f"  ❌ 关键项缺失: {sc['must_miss']}")

    # ── 资源消耗汇总 ──
    print_section("资源消耗汇总")
    total_tokens = 0
    total_time = 0
    total_tools = 0
    for r in results:
        agent = r["agent_result"]
        stats = agent.get("stats", {}) or {}
        total_tokens += stats.get("tokens", 0)
        total_time += agent.get("duration_ms", 0)
        total_tools += len(agent.get("tool_call_names", []))

    print(f"  总 Token 消耗: {total_tokens:,}")
    print(f"  总耗时: {total_time:,}ms ({total_time/1000:.1f}s)")
    print(f"  总工具调用: {total_tools} 次")
    print(f"  平均 Token/题: {total_tokens/len(results):,.0f}")
    print(f"  平均耗时/题: {total_time/len(results):,.0f}ms")


# ================================================================
#  主入口
# ================================================================

async def main():
    print("=" * 70)
    print("  OneDBA FAQ 知识库 RAG 验证")
    print("=" * 70)
    print(f"  知识库: {RESOURCE_URI}")
    print(f"  测试问题数: {len(TEST_CASES)}")
    print(f"  评分方式: 关键词匹配")
    print()

    # Phase 1: 上传知识库
    ok = await upload_knowledge_base()
    if not ok:
        print("[ERROR] 知识库上传失败，终止")
        return

    # Phase 2: 执行全部测试
    results = await run_all_tests()

    # Phase 3: 报告
    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())