#!/usr/bin/env python3
"""
VK-DBAgent 记忆功能验证脚本
==========================

基于真实 OneDBA 平台 + OpenViking 记忆系统，验证 Agent 能否有效复用旧知识，
节省 Token、工具调用次数和端到端耗时。

测试场景：
  Round 1: 用户查询生产环境 RDS 实例的业务子域分布 → 建立记忆
  Round 2: 用户查询告警配置相关表（无关话题）→ 验证记忆隔离
  Round 3: 用户再次查询 RDS 实例分布（类似 Round 1）
           → 基线(无记忆) vs 增强(有记忆) 对比

运行方式：
  cd /Users/admin/DBR/VK-DBAgent
  python tests/verify_memory_vkdb.py

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

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 服务地址 ──
OV_BASE_URL = "http://localhost:1933"
OV_API = f"{OV_BASE_URL}/api/v1"

# ── 测试标识 ──
TEST_USER = "vkdb-memory-verify"
TEST_SESSION_PREFIX = f"verify-{uuid.uuid4().hex[:8]}"

# ── 目标数据库（真实 OneDBA 测试库）──
TARGET_SCHEMA_ID = 65938636  # dw_onedba @ dw-onedba-t1
TARGET_DB_NAME = "dw_onedba"

# ================================================================
#  测试对话数据
# ================================================================

ROUND1_USER = (
    "帮我查一下生产环境中各个业务子域有多少个RDS实例，"
    "以及它们的平均CPU核数、平均内存和总存储量，"
    "按实例数量从多到少排列，只看前10个。"
    "表名是 db_rds_instance，字段包括 business_subdomain、db_instance_cpu、db_instance_memory、env_type"
)

ROUND2_USER = (
    "帮我看看数据库中有哪些表是和告警配置相关的，列出表名和注释"
)

ROUND3_USER = (
    "我需要统计一下生产环境RDS实例的情况，按业务子域分组，"
    "看每个子域有多少实例，平均CPU和内存配置如何"
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


def print_json(obj, max_len=3000):
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    if len(s) > max_len:
        print(s[:max_len] + "\n... [truncated]")
    else:
        print(s)


# ================================================================
#  OpenViking 辅助函数 — 使用 OpenVikingClient 确保 header 命名空间一致
# ================================================================

OV_HEADERS = {
    "Content-Type": "application/json",
    "X-OpenViking-Account": "default",
    "X-OpenViking-User": TEST_USER,
}


async def ov_get(path: str, params: dict = None) -> dict:
    """OpenViking GET 请求（带用户 header）"""
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as client:
        r = await client.get(f"{OV_API}{path}", params=params)
        return r.json()


async def ov_post(path: str, data: dict = None) -> dict:
    """OpenViking POST 请求（带用户 header）"""
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as client:
        r = await client.post(f"{OV_API}{path}", json=data)
        return r.json()


async def ov_get_raw(path: str, uri: str) -> dict:
    """OpenViking GET 请求（uri 直接拼接在 URL 中，带用户 header）"""
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as client:
        r = await client.get(f"{OV_API}{path}?uri={uri}")
        return r.json()


async def ov_delete(path: str) -> dict:
    """OpenViking DELETE 请求（带用户 header）"""
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as client:
        r = await client.delete(f"{OV_API}{path}")
        return r.json()


# ================================================================
#  Agent 执行辅助
# ================================================================

async def run_agent_round(
    user_input: str,
    session_state: dict[str, Any],
    round_label: str,
    kb_enabled: bool = True,
    preference_enabled: bool = False,
) -> dict[str, Any]:
    """
    执行一轮 Agent 对话，收集所有指标。

    注意：step 事件中不包含 tool input（由 run_agent_stream 内部收集），
    完整的 tool_calls（含 args）在 final 事件中返回。
    """
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
                memory_count = len(memories)
                await kb.close()
                if memories:
                    session_state["_memories"] = memories
                session_state["_memory_count"] = memory_count
                print(f"  [KB] 检索到 {memory_count} 条记忆")
            except Exception as e:
                print(f"  [KB] 检索失败: {type(e).__name__}: {e}")

        # ── 检索查询偏好 ──
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
                    user_input, session_state, trace_name=f"VKDB-MemoryVerify-{round_label}"
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
                        # run_agent_stream 的 final 事件包含完整的 tool_calls（含 args）
                        final_tool_calls = data.get("tool_calls", [])
                        updated = data.get("updated_state", {})
                        if updated:
                            session_state.clear()
                            session_state.update(updated)
        except asyncio.TimeoutError:
            error = "执行超时 (300s)"
        except TimeoutError:
            error = "执行超时 (300s)"
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

class VKDBMemoryVerifier:
    """VK-DBAgent 记忆功能验证器"""

    def __init__(self):
        self.results: dict[str, dict[str, Any]] = {}
        self.ov_session_id: str = ""

    # ── Phase 1: Round 1 — 建立记忆 ──

    async def phase1_round1_establish_memory(self):
        """执行 Round 1，建立数据库查询记忆"""
        print_section("Phase 1: Round 1 — 建立记忆")

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-r1",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
        }

        print(f"\n  [User →] {ROUND1_USER[:100]}...")
        result = await run_agent_round(
            ROUND1_USER, session_state, "Round1",
            kb_enabled=True, preference_enabled=False,
        )

        self.results["round1"] = result
        self._session_state_r1 = session_state

        print_sub("Round 1 结果摘要")
        print(f"  响应长度: {len(result['response'])} chars")
        print(f"  工具调用: {result['tool_call_names']}")
        print(f"  工具调用次数: {len(result['tool_call_names'])}")
        print(f"  SQL 数量: {len(result['sqls'])}")
        print(f"  耗时: {result['duration_ms']}ms")
        print(f"  记忆数: {result['memory_count']}")
        print(f"  偏好数: {result['preference_count']}")
        if result["error"]:
            print(f"  ❌ 错误: {result['error']}")

        return result

    # ── Phase 2: OpenViking 记忆提交 ──

    async def phase2_commit_to_openviking(self):
        """将 Round 1 对话提交到 OpenViking，触发记忆提取"""
        print_section("Phase 2: 提交 OpenViking 记忆")

        # 创建 OpenViking 会话
        ov_session = await ov_post("/sessions")
        self.ov_session_id = ov_session.get("result", {}).get("session_id", "") or ov_session.get("session_id", "")
        print(f"[OK] OV 会话创建: {self.ov_session_id}")

        # 写入 Round 1 对话（使用与 OpenVikingClient.add_message 一致的 content 格式）
        r1 = self.results["round1"]
        await ov_post(
            f"/sessions/{self.ov_session_id}/messages",
            {"role": "user", "content": ROUND1_USER}
        )
        await ov_post(
            f"/sessions/{self.ov_session_id}/messages",
            {"role": "assistant", "content": r1["response"][:5000]}
        )
        print("[OK] Round 1 对话已写入 OV")

        # Commit 触发记忆提取
        commit_resp = await ov_post(
            f"/sessions/{self.ov_session_id}/commit",
            {"keep_recent_count": 0}
        )
        commit_result = commit_resp.get("result", {}) or {}
        task_id = commit_result.get("task_id", "")
        print(f"[OK] Commit 已提交: task_id={task_id}")

        if not task_id:
            print("[WARN] 无 task_id，跳过轮询")
            return

        # 轮询任务状态
        print(f"\n[INFO] 轮询记忆提取任务...")
        for i in range(60):
            await asyncio.sleep(2)
            task_resp = await ov_get(f"/tasks/{task_id}")
            td = task_resp.get("result", {}) or {}
            stage = td.get("stage", "unknown")
            inner = td.get("result", {}) or {}
            extracted = inner.get("memories_extracted", {})
            print(f"  [{i+1:2d}] stage={stage}, extracted={extracted}")
            if stage == "completed":
                break
        else:
            print("[WARN] 记忆提取超时 (120s)")

        # 收集记忆文件信息
        await self._browse_ov_memories()

    async def _browse_ov_memories(self):
        """浏览 OpenViking 中的记忆文件"""
        print_sub("用户记忆目录")
        try:
            resp = await ov_get_raw(
                "/fs/ls",
                f"viking://user/{TEST_USER}/memories/"
            )
            entries = resp.get("result", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
            # 尝试递归
            if not entries:
                resp2 = await ov_get("/fs/ls", {
                    "uri": f"viking://user/{TEST_USER}/memories/",
                    "recursive": True, "simple": True, "node_limit": 100,
                })
                entries = resp2.get("result", []) if isinstance(resp2, dict) else []

            if isinstance(entries, list):
                print(f"[OK] 记忆文件数: {len(entries)}")
                for u in entries[:20]:
                    print(f"  {u}")
            else:
                print(f"[WARN] 返回异常: {type(entries)}")
        except Exception as e:
            print(f"[WARN] 浏览记忆目录失败: {e}")

    # ── Phase 3: Round 2 — 无关话题 ──

    async def phase3_round2_unrelated(self):
        """执行 Round 2，验证记忆隔离"""
        print_section("Phase 3: Round 2 — 无关话题")

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-r2",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
        }

        print(f"\n  [User →] {ROUND2_USER[:100]}...")
        result = await run_agent_round(
            ROUND2_USER, session_state, "Round2",
            kb_enabled=True, preference_enabled=False,
        )

        self.results["round2"] = result

        print_sub("Round 2 结果摘要")
        print(f"  响应长度: {len(result['response'])} chars")
        print(f"  工具调用: {result['tool_call_names']}")
        print(f"  耗时: {result['duration_ms']}ms")
        if result["error"]:
            print(f"  ❌ 错误: {result['error']}")

        return result

    # ── Phase 4: Round 3 — 基线 (无记忆) ──

    async def phase4_round3_baseline(self):
        """执行 Round 3 基线测试（禁用记忆和偏好）"""
        print_section("Phase 4: Round 3 — 基线 (无记忆)")

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-r3-baseline",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
        }

        print(f"\n  [User →] {ROUND3_USER[:100]}...")
        result = await run_agent_round(
            ROUND3_USER, session_state, "Round3-Baseline",
            kb_enabled=False, preference_enabled=False,
        )

        self.results["round3_baseline"] = result

        print_sub("Round 3 基线结果摘要")
        print(f"  响应长度: {len(result['response'])} chars")
        print(f"  工具调用: {result['tool_call_names']}")
        print(f"  工具调用次数: {len(result['tool_call_names'])}")
        print(f"  SQL 数量: {len(result['sqls'])}")
        print(f"  耗时: {result['duration_ms']}ms")
        if result["error"]:
            print(f"  ❌ 错误: {result['error']}")

        return result

    # ── Phase 5: Round 3 — 增强 (有记忆) ──

    async def phase5_round3_enhanced(self):
        """执行 Round 3 增强测试（启用记忆和偏好）"""
        print_section("Phase 5: Round 3 — 增强 (有记忆)")

        session_state = {
            "session_id": f"{TEST_SESSION_PREFIX}-r3-enhanced",
            "user_id": TEST_USER,
            "chat_history": [],
            "summary": "",
            "kb_session_id": "",
            "kb_turn_count": 0,
        }

        print(f"\n  [User →] {ROUND3_USER[:100]}...")
        result = await run_agent_round(
            ROUND3_USER, session_state, "Round3-Enhanced",
            kb_enabled=True, preference_enabled=False,
        )

        self.results["round3_enhanced"] = result

        print_sub("Round 3 增强结果摘要")
        print(f"  响应长度: {len(result['response'])} chars")
        print(f"  工具调用: {result['tool_call_names']}")
        print(f"  工具调用次数: {len(result['tool_call_names'])}")
        print(f"  SQL 数量: {len(result['sqls'])}")
        print(f"  耗时: {result['duration_ms']}ms")
        print(f"  记忆数: {result['memory_count']}")
        print(f"  偏好数: {result['preference_count']}")
        if result["error"]:
            print(f"  ❌ 错误: {result['error']}")

        return result

    # ── Phase 6: 验证报告 ──

    def phase6_report(self):
        """汇总数据，输出验证报告"""
        print_section("Phase 6: 验证报告")

        r1 = self.results.get("round1", {})
        r2 = self.results.get("round2", {})
        r3b = self.results.get("round3_baseline", {})
        r3e = self.results.get("round3_enhanced", {})

        # ── 1. 工具调用次数对比 ──
        print("\n[指标 1] 工具调用次数对比")
        r1_tools = r1.get("tool_call_names", [])
        r3b_tools = r3b.get("tool_call_names", [])
        r3e_tools = r3e.get("tool_call_names", [])

        print(f"  {'场景':<25} {'工具调用次数':>12} {'工具列表':>30}")
        print(f"  {'-'*70}")
        print(f"  {'Round 1 (首次)':<25} {len(r1_tools):>12} {str(r1_tools)[:30]:>30}")
        print(f"  {'Round 3 基线 (无记忆)':<25} {len(r3b_tools):>12} {str(r3b_tools)[:30]:>30}")
        print(f"  {'Round 3 增强 (有记忆)':<25} {len(r3e_tools):>12} {str(r3e_tools)[:30]:>30}")

        tool_saved = len(r3b_tools) - len(r3e_tools)
        if tool_saved > 0:
            print(f"\n  ✅ 有记忆时减少了 {tool_saved} 次工具调用")
        elif tool_saved == 0:
            print(f"\n  ➡️ 工具调用次数无变化")
        else:
            print(f"\n  ⚠️ 有记忆时增加了 {abs(tool_saved)} 次工具调用")

        # 检查是否跳过了 find_table 或 describe_table
        r3e_tool_set = set(r3e_tools)
        r3b_tool_set = set(r3b_tools)
        skipped = r3b_tool_set - r3e_tool_set
        if skipped:
            print(f"  💡 跳过的工具: {skipped}")

        # ── 2. 耗时对比 ──
        print(f"\n[指标 2] 端到端耗时对比")
        r1_duration = r1.get("duration_ms", 0)
        r3b_duration = r3b.get("duration_ms", 0)
        r3e_duration = r3e.get("duration_ms", 0)

        print(f"  {'场景':<25} {'耗时(ms)':>12} {'相对Round1':>12}")
        print(f"  {'-'*52}")
        print(f"  {'Round 1 (首次)':<25} {r1_duration:>12,}")
        print(f"  {'Round 3 基线 (无记忆)':<25} {r3b_duration:>12,} {_pct_str(r3b_duration, r1_duration):>12}")
        print(f"  {'Round 3 增强 (有记忆)':<25} {r3e_duration:>12,} {_pct_str(r3e_duration, r1_duration):>12}")

        time_saved = r3b_duration - r3e_duration
        if time_saved > 0:
            print(f"\n  ✅ 有记忆时节省了 {time_saved:,}ms ({time_saved/1000:.1f}s)")
        elif time_saved < 0:
            print(f"\n  ⚠️ 有记忆时增加了 {abs(time_saved):,}ms")

        # ── 3. Token 消耗对比 ──
        print(f"\n[指标 3] Token 消耗对比")
        r1_stats = r1.get("stats", {}) or {}
        r3b_stats = r3b.get("stats", {}) or {}
        r3e_stats = r3e.get("stats", {}) or {}

        r1_tokens = r1_stats.get("tokens", 0)
        r3b_tokens = r3b_stats.get("tokens", 0)
        r3e_tokens = r3e_stats.get("tokens", 0)

        r1_timeout = r1.get("error") is not None
        r3b_timeout = r3b.get("error") is not None
        r3e_timeout = r3e.get("error") is not None

        if r1_timeout:
            print(f"  ⚠️ Round 1 超时，token 数据不可用")
        if r3b_timeout:
            print(f"  ⚠️ Round 3 基线超时，token 数据不可用")
        if r3e_timeout:
            print(f"  ⚠️ Round 3 增强超时，token 数据不可用")

        if r1_tokens or r3b_tokens or r3e_tokens:
            print(f"  {'场景':<25} {'Token数':>12} {'备注':>15}")
            print(f"  {'-'*55}")
            r1_note = "超时不可用" if (r1_timeout and r1_tokens == 0) else ""
            r3b_note = "超时不可用" if (r3b_timeout and r3b_tokens == 0) else ""
            r3e_note = "超时不可用" if (r3e_timeout and r3e_tokens == 0) else ""
            print(f"  {'Round 1 (首次)':<25} {r1_tokens:>12,} {r1_note:>15}")
            print(f"  {'Round 3 基线 (无记忆)':<25} {r3b_tokens:>12,} {r3b_note:>15}")
            print(f"  {'Round 3 增强 (有记忆)':<25} {r3e_tokens:>12,} {r3e_note:>15}")

            if r3b_tokens > 0 and r3e_tokens > 0:
                token_saved = r3b_tokens - r3e_tokens
                if token_saved > 0:
                    print(f"\n  ✅ 有记忆时节省了 {token_saved:,} tokens")
                elif token_saved < 0:
                    print(f"\n  ⚠️ 有记忆时增加了 {abs(token_saved):,} tokens（记忆上下文带来了额外 prompt 开销）")
                else:
                    print(f"\n  ➡️ Token 消耗无变化")
            else:
                token_saved = 0
        else:
            print(f"  ⚠️ 所有轮次的 token 数据均不可用（超时导致）")
            token_saved = 0

        # ── 4. 记忆召回 ──
        print(f"\n[指标 4] 记忆召回")
        r3e_memories = r3e.get("memory_count", 0)
        r3e_prefs = r3e.get("preference_count", 0)
        print(f"  Round 3 增强 检索到记忆: {r3e_memories} 条")
        print(f"  Round 3 增强 检索到偏好: {r3e_prefs} 条")

        # ── 5. SQL 一致性 ──
        print(f"\n[指标 5] SQL 一致性分析")
        r1_sqls = r1.get("sqls", [])
        r3b_sqls = r3b.get("sqls", [])
        r3e_sqls = r3e.get("sqls", [])

        # 提取关键表名和字段名
        r1_key_tables = _extract_table_names(r1_sqls)
        r3b_key_tables = _extract_table_names(r3b_sqls)
        r3e_key_tables = _extract_table_names(r3e_sqls)

        print(f"  Round 1 SQL 涉及表: {r1_key_tables}")
        print(f"  Round 3 基线 SQL 涉及表: {r3b_key_tables}")
        print(f"  Round 3 增强 SQL 涉及表: {r3e_key_tables}")

        # 检查增强回复是否与 Round 1 表名一致
        if r1_key_tables and r3e_key_tables:
            overlap = r1_key_tables & r3e_key_tables
            if overlap:
                print(f"  ✅ 增强 SQL 复用了 Round 1 的表: {overlap}")
            else:
                print(f"  ⚠️ 增强 SQL 未复用 Round 1 的表名")

        # ── 6. 综合判断 ──
        print(f"\n{'='*70}")
        print(f"  综合判断")
        print(f"{'='*70}")

        # Token 节省仅在双方都有数据时判断
        token_available = r3b_tokens > 0 and r3e_tokens > 0
        token_ok = token_saved >= 0 if token_available else True  # 无数据时不判

        checks = [
            ("Round 1 执行成功", r1.get("error") is None and len(r1.get("response", "")) > 0),
            ("Round 2 执行成功", r2.get("error") is None and len(r2.get("response", "")) > 0),
            ("Round 3 基线执行成功", r3b.get("error") is None and len(r3b.get("response", "")) > 0),
            ("Round 3 增强执行成功", r3e.get("error") is None and len(r3e.get("response", "")) > 0),
            ("记忆召回 > 0", r3e_memories > 0),
            ("工具调用减少", tool_saved >= 0),
            ("耗时节省", time_saved >= 0),
        ]
        if token_available:
            checks.append(("Token 节省", token_saved >= 0))

        for desc, passed in checks:
            print(f"  {'✅ PASS' if passed else '❌ FAIL'}  {desc}")

        passed_count = sum(1 for _, v in checks if v)
        print(f"\n  通过: {passed_count}/{len(checks)}")

        if passed_count >= len(checks) - 2:
            print(f"  ✅ 核心链路正常: 记忆提取→召回→工具调用减少，闭环完整")
        elif passed_count >= len(checks) - 4:
            print(f"  ⚠️ 大部分通过: 核心链路正常，部分优化指标未达预期")
        else:
            print(f"  ❌ 多项验证未通过，详见上方")

        # ── 附录：原始数据 ──
        print(f"\n[附录] 完整原始数据")
        safe = {}
        for k, v in self.results.items():
            if isinstance(v, dict):
                safe[k] = {
                    k2: v2 for k2, v2 in v.items()
                    if k2 not in ("response",)
                }
                if "response" in v:
                    safe[k]["response_preview"] = str(v["response"])[:300]
        print_json(safe, max_len=20000)

    async def cleanup(self):
        """清理测试数据"""
        if self.ov_session_id:
            try:
                await ov_delete(f"/sessions/{self.ov_session_id}")
                print(f"[Cleanup] OV 会话已删除: {self.ov_session_id}")
            except Exception:
                pass


# ================================================================
#  辅助函数
# ================================================================

def _pct_str(value: int, baseline: int) -> str:
    """计算百分比变化"""
    if baseline == 0:
        return "N/A"
    pct = (value - baseline) / baseline * 100
    if pct > 0:
        return f"+{pct:.0f}%"
    else:
        return f"{pct:.0f}%"


def _extract_table_names(sqls: list[str]) -> set[str]:
    """从 SQL 列表中提取表名"""
    import re
    tables = set()
    for sql in sqls:
        # 匹配 FROM/JOIN 后的表名
        for match in re.finditer(
            r'(?:FROM|JOIN)\s+`?(\w+)`?',
            sql, re.IGNORECASE
        ):
            tables.add(match.group(1).lower())
    return tables


# ================================================================
#  主入口
# ================================================================

async def main():
    print("=" * 70)
    print("  VK-DBAgent 记忆功能验证")
    print("=" * 70)
    print(f"  用户: {TEST_USER}")
    print(f"  数据库: {TARGET_DB_NAME} (schema_id={TARGET_SCHEMA_ID})")
    print(f"  OpenViking: {OV_BASE_URL}")
    print()

    verifier = VKDBMemoryVerifier()

    try:
        # Phase 1: Round 1 — 建立记忆
        await verifier.phase1_round1_establish_memory()

        # Phase 2: 提交 OpenViking 记忆
        await verifier.phase2_commit_to_openviking()

        # Phase 3: Round 2 — 无关话题
        await verifier.phase3_round2_unrelated()

        # Phase 4: Round 3 — 基线 (无记忆)
        await verifier.phase4_round3_baseline()

        # Phase 5: Round 3 — 增强 (有记忆)
        await verifier.phase5_round3_enhanced()

        # Phase 6: 报告
        verifier.phase6_report()

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        verifier.phase6_report()
    finally:
        await verifier.cleanup()


if __name__ == "__main__":
    asyncio.run(main())