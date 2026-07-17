#!/usr/bin/env python3
"""
VK-DBAgent RAG 验证脚本
=======================

验证思路：对比实验法
  1. 无 RAG (基线)：Agent 仅靠自身知识 + OpenViking 长期记忆
  2. 有 RAG (实验组)：Agent 额外获得从 SQL 参考知识库检索到的相关信息

  如果 RAG 有效，有 RAG 组应减少工具调用次数、降低 Token 消耗、缩短耗时，
  且 Agent 能更快定位到正确的表和字段。

知识库：
  data/dba_sql_reference.md — OneDBA DBA 常用 SQL 参考（真实数据验证）

运行方式：
  cd /Users/admin/DBR/VK-DBAgent
  python tests/verify_rag_vkdb.py

前置条件：
  - OpenViking Server 运行在 localhost:1933
  - OneDBA 可访问
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
TEST_USER = "vkdb-rag-verify"
TEST_SESSION_PREFIX = f"rag-{uuid.uuid4().hex[:8]}"

# ── 目标数据库 ──
TARGET_SCHEMA_ID = 65938636
TARGET_DB_NAME = "dw_onedba"

# ── 知识库资源 ──
RESOURCE_URI = "viking://resources/dba-sql-reference"
RESOURCE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dba_sql_reference.md")

# ── OpenViking Header ──
OV_HEADERS = {
    "Content-Type": "application/json",
    "X-OpenViking-Account": "default",
    "X-OpenViking-User": TEST_USER,
}

# ================================================================
#  测试问题（无表名/字段名提示，纯自然语言）
# ================================================================

RAG_QUESTION = (
    "帮我统计一下生产环境中各个业务子域的RDS实例有多少告警，"
      "按告警数量从多到少排列"
)


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
#  OpenViking 辅助函数（含资源上传/检索）
# ================================================================

async def ov_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.get(f"{OV_API}{path}", params=params)
        return r.json()


async def ov_post(path: str, data: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.post(f"{OV_API}{path}", json=data)
        return r.json()


async def ov_get_raw(path: str, uri: str) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.get(f"{OV_API}{path}?uri={uri}")
        return r.json()


async def ov_upload_file(path: str, filename: str) -> dict:
    """上传文件到 OpenViking（multipart/form-data）"""
    with open(path, "rb") as f:
        async with httpx.AsyncClient(timeout=120, headers={"X-OpenViking-Account": "default", "X-OpenViking-User": TEST_USER}) as c:
            r = await c.post(f"{OV_API}/resources/temp_upload", files={"file": (filename, f, "text/markdown")})
            return r.json()


# ================================================================
#  Agent 执行辅助（复用 verify_memory_vkdb.py 的 run_agent_round）
# ================================================================

async def run_agent_round(
    user_input: str,
    session_state: dict[str, Any],
    round_label: str,
    kb_enabled: bool = True,
    preference_enabled: bool = False,
) -> dict[str, Any]:
    """执行一轮 Agent 对话，收集所有指标。"""
    from app.agent.runner import run_agent_stream
    from app.config import get_settings

    settings = get_settings()
    original_kb = settings.kb_enabled
    original_pref = settings.preference_enabled
    settings.kb_enabled = kb_enabled
    settings.preference_enabled = preference_enabled

    try:
        tool_call_names: list[str] = []
        tool_call_counts: dict[str, int] = {}
        sqls: list[str] = []
        final_response = ""
        stats: dict[str, Any] = {}
        error: str | None = None
        memory_count = 0
        preference_count = 0
        final_tool_calls: list[dict[str, Any]] = []

        # ── 检索长期记忆 ──
        if kb_enabled:
            try:
                from app.knowledge.openviking import OpenVikingClient
                kb = OpenVikingClient(settings.kb_openviking_url, TEST_USER)
                await kb.start()
                memories = await kb.retrieve_memories()
                await kb.close()

                # RAG 上下文作为独立的 [SQL 参考] 注入到 session_state
                rag_context = session_state.pop("_rag_context", [])
                if rag_context:
                    session_state["_rag_reference"] = rag_context
                    print(f"  [RAG] 注入 {len(rag_context)} 条知识库上下文")

                if memories:
                    session_state["_memories"] = memories
                memory_count = len(memories) + len(rag_context)
                session_state["_memory_count"] = memory_count
                print(f"  [KB] 总上下文: {len(memories)} 条长期记忆 + {len(rag_context)} 条 RAG 参考 = {memory_count} 条")
            except Exception as e:
                print(f"  [KB] 检索失败: {type(e).__name__}: {e}")

        if preference_enabled:
            try:
                from app.memory import get_storage
                pref_store = get_storage().preference_store
                if pref_store is not None:
                    await pref_store.initialize()
                    preferences = await pref_store.retrieve_preferences(TEST_USER, user_input)
                    if not preferences:
                        preferences = await pref_store.retrieve_top_preferences(TEST_USER)
                    preference_count = len(preferences)
                    if preferences:
                        session_state["_preferences"] = preferences
                    session_state["_preference_count"] = preference_count
                    print(f"  [Pref] 检索到 {preference_count} 条偏好")
            except Exception as e:
                print(f"  [Pref] 检索失败: {type(e).__name__}: {e}")

        start_time = time.monotonic()

        try:
            async with asyncio.timeout(300):
                async for event_type, data in run_agent_stream(
                    user_input, session_state, trace_name=f"VKDB-RAG-Verify-{round_label}"
                ):
                    if event_type == "step":
                        step = data.get("step", "")
                        status = data.get("status", "")
                        if step.startswith("tool:") and status == "running":
                            tool_name = step.replace("tool:", "")
                            tool_call_names.append(tool_name)
                            tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1
                            print(f"  [Tool] {tool_name}")
                        elif step == "thinking":
                            text = data.get("text", "")
                            if text:
                                print(f"  [Think] {text[:120]}...")
                    elif event_type == "sql":
                        sql_text = data.get("sql", "")
                        if sql_text:
                            sqls.append(sql_text)
                            print(f"  [SQL] {sql_text[:150]}...")
                    elif event_type == "final":
                        final_response = data.get("response", "")
                        stats = data.get("stats", {})
                        final_tool_calls = data.get("tool_calls", [])
                        updated = data.get("updated_state", {})
                        if updated:
                            session_state.clear()
                            session_state.update(updated)
        except asyncio.TimeoutError:
            error = f"执行超时 (300s)"
        except TimeoutError:
            error = f"执行超时 (300s)"
        except Exception as e:
            error = f"执行异常: {type(e).__name__}: {e}"

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return {
            "response": final_response,
            "tool_calls": final_tool_calls,
            "tool_call_names": tool_call_names,
            "tool_call_counts": tool_call_counts,
            "sqls": sqls,
            "stats": stats,
            "duration_ms": duration_ms,
            "error": error,
            "memory_count": memory_count,
            "preference_count": preference_count,
        }
    finally:
        settings.kb_enabled = original_kb
        settings.preference_enabled = original_pref


# ================================================================
#  主验证流程
# ================================================================

class RAGVerifier:
    """VK-DBAgent RAG 验证器"""

    def __init__(self):
        self.results: dict[str, dict[str, Any]] = {}
        self.rag_context: list[dict[str, str]] = []

    # ── Phase 1: 上传知识库到 OpenViking ──

    async def phase1_upload_knowledge_base(self):
        """将 DBA SQL 参考上传到 OpenViking resources"""
        print_section("Phase 1: 上传知识库到 OpenViking")

        if not os.path.exists(RESOURCE_FILE):
            print(f"[ERROR] 知识库文件不存在: {RESOURCE_FILE}")
            return False

        # 检查是否已存在
        stat = await ov_get("/fs/stat", {"uri": RESOURCE_URI})
        if stat.get("status") == "ok":
            print(f"[OK] 资源已存在: {RESOURCE_URI}")
            return True

        # 上传文件
        print(f"[INFO] 上传文件: {RESOURCE_FILE}")
        upload = await ov_upload_file(RESOURCE_FILE, "dba-sql-reference.md")
        temp_id = upload.get("result", {}).get("temp_file_id", "")

        if not temp_id:
            print(f"[ERROR] 上传失败: {json.dumps(upload, ensure_ascii=False)[:300]}")
            return False

        # 创建资源
        create = await ov_post("/resources", {
            "temp_file_id": temp_id,
            "to": RESOURCE_URI,
            "reason": "RAG 验证 — DBA SQL 参考知识库",
            "instruction": (
                "OneDBA DBA 常用 SQL 参考手册。包含 dw_onedba 库中 RDS 实例统计、"
                "Schema 数据库统计、告警数据分析等真实 SQL 语句和字段取值速查表。"
                "核心表: db_rds_instance, db_instance_v2, db_schemas, db_alert_history。"
            ),
            "wait": True,
            "timeout": 120,
        })
        result = create.get("result", {}) or {}
        if result.get("resource_id") or create.get("status") == "ok":
            print(f"[OK] 资源已创建: {RESOURCE_URI}")
            return True
        else:
            print(f"[WARN] 资源创建结果: {json.dumps(create, ensure_ascii=False)[:300]}")
            return False

    # ── Phase 2: Round 1 — 基线 (无 RAG) ──

    async def phase2_baseline_without_rag(self):
        """Agent 无 RAG 上下文执行查询"""
        print_section("Phase 2: 基线 (无 RAG)")

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-baseline",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
        }

        print(f"\n  [User →] {RAG_QUESTION[:100]}...")
        result = await run_agent_round(
            RAG_QUESTION, session_state, "Baseline",
            kb_enabled=True, preference_enabled=False,
        )

        self.results["baseline"] = result

        print_sub("基线结果摘要")
        print(f"  响应长度: {len(result['response'])} chars")
        print(f"  工具调用: {result['tool_call_names']}")
        print(f"  工具调用次数: {len(result['tool_call_names'])}")
        print(f"  SQL 数量: {len(result['sqls'])}")
        print(f"  耗时: {result['duration_ms']}ms")
        print(f"  记忆数: {result['memory_count']}")
        if result["error"]:
            print(f"  ❌ 错误: {result['error']}")

        return result

    # ── Phase 3: RAG 检索 ──

    async def phase3_rag_search(self) -> list[dict[str, str]]:
        """从知识库检索相关 SQL 参考"""
        print_section("Phase 3: RAG 检索")

        search = await ov_post("/search/find", {
            "query": RAG_QUESTION,
            "target_uri": "viking://resources/",
            "context_type": "resource",
            "limit": 5,
        })
        resources = search.get("result", {}).get("resources", [])
        print(f"[OK] 检索到 {len(resources)} 条相关资源")

        rag_context: list[dict[str, str]] = []

        for i, r in enumerate(resources[:3]):
            uri = r.get("uri", "")
            score = r.get("score", 0)
            content = str(r.get("content", ""))[:500]
            print(f"  [{i+1}] score={score:.4f} {uri}")

            # 读取完整内容
            try:
                read = await ov_get("/content/read", {"uri": uri, "limit": 200})
                full = read.get("result", "")
                if isinstance(full, dict):
                    full = full.get("content", str(full))
                if full:
                    # 过滤掉 markdown 标题行，提取有效内容
                    lines = []
                    for line in str(full).split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            lines.append(line)
                    content = "\n".join(lines)[:3000]
                    print(f"      完整内容: {len(str(full))} chars")
            except Exception:
                pass

            rag_context.append({
                "category": "knowledge_base",
                "abstract": (
                    f"[DBA SQL 参考知识库 — 检索第{i+1}条, 相关性={score:.4f}] "
                    f"{content[:1000]}"
                ),
                "name": uri,
                "_raw_content": str(full)[:2000],  # 保留完整原文供报告展示
            })

        self.rag_context = rag_context
        return rag_context

    # ── Phase 4: Round 2 — 有 RAG ──

    async def phase4_with_rag(self, rag_context: list[dict[str, str]]):
        """Agent 携带 RAG 上下文执行查询"""
        print_section("Phase 4: 有 RAG")

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-rag",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
            "_rag_context": rag_context,  # 由 run_agent_round 读取并合并到 _memories
        }

        print(f"\n  [User →] {RAG_QUESTION[:100]}...")
        result = await run_agent_round(
            RAG_QUESTION, session_state, "WithRAG",
            kb_enabled=True, preference_enabled=False,
        )

        self.results["with_rag"] = result

        print_sub("有 RAG 结果摘要")
        print(f"  响应长度: {len(result['response'])} chars")
        print(f"  工具调用: {result['tool_call_names']}")
        print(f"  工具调用次数: {len(result['tool_call_names'])}")
        print(f"  SQL 数量: {len(result['sqls'])}")
        print(f"  耗时: {result['duration_ms']}ms")
        print(f"  记忆数: {result['memory_count']}")
        if result["error"]:
            print(f"  ❌ 错误: {result['error']}")

        return result

    # ── Phase 5: 验证报告 ──

    def phase5_report(self):
        """汇总数据，输出对比报告"""
        print_section("Phase 5: 验证报告")

        bl = self.results.get("baseline", {})
        rag = self.results.get("with_rag", {})

        # ── 1. 工具调用次数 ──
        print("\n[指标 1] 工具调用次数对比")
        bl_tools = bl.get("tool_call_names", [])
        rag_tools = rag.get("tool_call_names", [])

        print(f"  {'场景':<20} {'工具调用':>8} {'详情'}")
        print(f"  {'-'*60}")
        print(f"  {'无 RAG (基线)':<20} {len(bl_tools):>8} {str(bl_tools)[:80]}")
        print(f"  {'有 RAG':<20} {len(rag_tools):>8} {str(rag_tools)[:80]}")

        tool_diff = len(bl_tools) - len(rag_tools)
        if tool_diff > 0:
            skipped = set(bl_tools) - set(rag_tools)
            print(f"\n  ✅ RAG 减少 {tool_diff} 次工具调用，跳过: {skipped}")
        elif tool_diff < 0:
            print(f"\n  ⚠️ RAG 增加 {abs(tool_diff)} 次工具调用")
        else:
            print(f"\n  ➡️ 工具调用次数无变化")

        # ── 2. 耗时 ──
        print(f"\n[指标 2] 耗时对比")
        bl_time = bl.get("duration_ms", 0)
        rag_time = rag.get("duration_ms", 0)
        print(f"  {'场景':<20} {'耗时(ms)':>12} {'相对基线'}")
        print(f"  {'-'*45}")
        print(f"  {'无 RAG (基线)':<20} {bl_time:>12,}")
        print(f"  {'有 RAG':<20} {rag_time:>12,} {_pct_change(rag_time, bl_time):>10}")

        time_saved = bl_time - rag_time
        if time_saved > 0:
            print(f"\n  ✅ RAG 节省 {time_saved:,}ms ({time_saved/1000:.1f}s)")
        elif time_saved < 0:
            print(f"\n  ⚠️ RAG 增加 {abs(time_saved):,}ms")
        else:
            print(f"\n  ➡️ 耗时无变化")

        # ── 3. Token 消耗 ──
        print(f"\n[指标 3] Token 消耗对比")
        bl_stats = bl.get("stats", {}) or {}
        rag_stats = rag.get("stats", {}) or {}

        bl_tokens = bl_stats.get("tokens", 0)
        rag_tokens = rag_stats.get("tokens", 0)

        bl_ok = bl.get("error") is None
        rag_ok = rag.get("error") is None

        if bl_ok and rag_ok:
            print(f"  {'场景':<20} {'Token数':>12} {'相对基线'}")
            print(f"  {'-'*45}")
            print(f"  {'无 RAG (基线)':<20} {bl_tokens:>12,}")
            print(f"  {'有 RAG':<20} {rag_tokens:>12,} {_pct_change(rag_tokens, bl_tokens):>10}")

            tok_saved = bl_tokens - rag_tokens
            if tok_saved > 0:
                print(f"\n  ✅ RAG 节省 {tok_saved:,} tokens")
            elif tok_saved < 0:
                print(f"\n  ⚠️ RAG 增加 {abs(tok_saved):,} tokens（知识库额外 prompt 开销）")
            else:
                print(f"\n  ➡️ Token 消耗无变化")
        else:
            if not bl_ok:
                print(f"  ⚠️ 基线超时，token 数据不可用")
            if not rag_ok:
                print(f"  ⚠️ 有 RAG 超时，token 数据不可用")

        # ── 4. RAG 检索到的参考资料原文 ──
        print(f"\n[指标 4] RAG 检索到的参考资料原文")
        for i, r in enumerate(self.rag_context):
            uri = r.get("name", "?")
            raw = r.get("_raw_content", "")
            print(f"\n  ── 参考资料 #{i+1} ── {uri}")
            print(f"  {raw[:1500]}")
            if len(raw) > 1500:
                print(f"  ... (共 {len(raw)} chars，已截断)")

        # ── 5. Agent 最终答案对比 ──
        print(f"\n[指标 5] Agent 最终答案对比")
        bl_response = bl.get("response", "")
        rag_response = rag.get("response", "")

        print(f"\n  ── 基线 (无 RAG) 答案 ({len(bl_response)} chars) ──")
        print(f"  {bl_response[:1500]}")
        if len(bl_response) > 1500:
            print(f"  ... (共 {len(bl_response)} chars，已截断)")

        print(f"\n  ── 有 RAG 答案 ({len(rag_response)} chars) ──")
        print(f"  {rag_response[:1500]}")
        if len(rag_response) > 1500:
            print(f"  ... (共 {len(rag_response)} chars，已截断)")

        # ── 6. 综合判断 ──
        print(f"\n{'='*70}")
        print(f"  综合判断")
        print(f"{'='*70}")

        checks = [
            ("基线执行成功", bl_ok and len(bl.get("response", "")) > 0),
            ("有 RAG 执行成功", rag_ok and len(rag.get("response", "")) > 0),
            ("工具调用减少", tool_diff >= 0),
            ("耗时减少", time_saved >= 0),
            ("Token 减少", rag_tokens <= bl_tokens if (bl_ok and rag_ok) else True),
            ("RAG 知识库已注入上下文", len(self.rag_context) > 0),
        ]

        for desc, passed in checks:
            print(f"  {'✅ PASS' if passed else '❌ FAIL'}  {desc}")

        passed = sum(1 for _, v in checks if v)
        print(f"\n  通过: {passed}/{len(checks)}")

        if passed == len(checks):
            print(f"  ✅ 全部通过: RAG 知识库有效提升了 Agent 效率")
        elif passed >= len(checks) - 1:
            print(f"  ⚠️ 大部分通过")
        else:
            print(f"  ❌ 多项验证未通过")

        # ── 附录 ──
        print(f"\n[附录] 原始对比数据")
        safe = {
            "baseline": _safe_result(bl),
            "with_rag": _safe_result(rag),
        }
        print(json.dumps(safe, indent=2, ensure_ascii=False, default=str)[:5000])


def _pct_change(value: int, baseline: int) -> str:
    if baseline == 0:
        return "N/A"
    pct = (value - baseline) / baseline * 100
    return f"{pct:+.0f}%"


def _safe_result(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_call_names": r.get("tool_call_names", []),
        "tool_call_counts": r.get("tool_call_counts", {}),
        "sqls_count": len(r.get("sqls", [])),
        "duration_ms": r.get("duration_ms", 0),
        "tokens": (r.get("stats", {}) or {}).get("tokens", 0),
        "memory_count": r.get("memory_count", 0),
        "error": r.get("error"),
        "response_preview": str(r.get("response", ""))[:300],
    }


def _extract_table_names(sqls: list[str]) -> set[str]:
    import re
    tables = set()
    for sql in sqls:
        for m in re.finditer(r'(?:FROM|JOIN)\s+`?(\w+)`?', sql, re.IGNORECASE):
            tables.add(m.group(1).lower())
    return tables


# ================================================================
#  主入口
# ================================================================

async def main():
    print("=" * 70)
    print("  VK-DBAgent RAG 验证 — 知识库增强效果对比")
    print("=" * 70)
    print(f"  用户: {TEST_USER}")
    print(f"  知识库: {RESOURCE_URI}")
    print(f"  目标库: {TARGET_DB_NAME} (schema_id={TARGET_SCHEMA_ID})")
    print()

    verifier = RAGVerifier()

    try:
        # Phase 1: 上传知识库
        ok = await verifier.phase1_upload_knowledge_base()
        if not ok:
            print("[ERROR] 知识库上传失败，终止")
            return

        # Phase 2: Round 1 — 基线 (无 RAG)
        await verifier.phase2_baseline_without_rag()

        # Phase 3: RAG 检索
        rag_context = await verifier.phase3_rag_search()

        # Phase 4: Round 2 — 有 RAG
        await verifier.phase4_with_rag(rag_context)

        # Phase 5: 报告
        verifier.phase5_report()

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())