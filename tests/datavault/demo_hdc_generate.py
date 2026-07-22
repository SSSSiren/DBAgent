#!/usr/bin/env python3
"""
HDC 知识库生成验证
===================

验证 HDC 知识库能否成功生成并持久化到 OpenViking。
运行完成后用 ov 命令行工具或 curl 检查输出。

运行方式：
  cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
  python tests/datavault/demo_hdc_generate.py [schema_id] [database_name]
  python tests/datavault/demo_hdc_generate.py [schema_id] [database_name] -v   # 详细日志

  验证持久化：
  ov ls viking://resources/hdc/{database_name}
  ov tree viking://resources/hdc/{database_name} -L 3
"""

import argparse
import asyncio
import logging
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.config import get_settings

# ═══════════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════════

OV_BASE_URL = "http://localhost:1933"
OV_API = f"{OV_BASE_URL}/api/v1"
TEST_USER = "hdc-gen-verify"

SETTINGS = get_settings()

# ── 命令行参数 ──
parser = argparse.ArgumentParser(description="HDC 知识库生成验证")
parser.add_argument("schema_id", nargs="?", type=int, default=25800743, help="OneDBA schema ID")
parser.add_argument("database_name", nargs="?", type=str, default="dw_onedba", help="数据库名称")
parser.add_argument("-v", "--verbose", action="store_true", help="输出详细中间日志（每张表/每个关系）")
parser.add_argument("--tables", type=str, default=None, help="逗号分隔的目标表名列表（部分表生成模式）")
_cli_args = parser.parse_args()

TARGET_SCHEMA_ID = _cli_args.schema_id
TARGET_DB_NAME = _cli_args.database_name
VERBOSE = _cli_args.verbose
TARGET_TABLES = [t.strip() for t in _cli_args.tables.split(",")] if _cli_args.tables else None

HDC_RESOURCE_BASE = f"viking://resources/hdc/{TARGET_SCHEMA_ID}/{TARGET_DB_NAME}"

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
#  OpenViking 辅助
# ═══════════════════════════════════════════════════════════════

async def ov_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.get(f"{OV_API}{path}", params=params)
        return r.json()


async def ov_ls(uri: str) -> list:
    raw = await ov_get("/fs/ls", {"uri": uri, "node_limit": 200})
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if raw.get("status") == "error":
            return []
        result = raw.get("result")
        if isinstance(result, list):
            return result
    return []


async def ov_tree(uri: str, depth: int = 3) -> list:
    raw = await ov_get("/fs/tree", {"uri": uri, "abs_limit": depth, "node_limit": 200})
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if raw.get("status") == "error":
            return []
        result = raw.get("result")
        if isinstance(result, list):
            return result
    return []


async def ov_read(uri: str, limit: int = 500) -> str:
    raw = await ov_get("/content/read", {"uri": uri, "limit": limit})
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        result = raw.get("result")
        if isinstance(result, str):
            return result
    return ""


async def ov_delete(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30, headers=OV_HEADERS) as c:
        r = await c.request("DELETE", f"{OV_API}{path}", params=params or {})
        d = r.json()
        if d.get("status") == "error":
            print(f"  [OV ERROR] {d.get('error',{}).get('message','unknown')}")
        return d.get("result", d)


# ═══════════════════════════════════════════════════════════════
#  Phase 1: 生成 HDC 知识库
# ═══════════════════════════════════════════════════════════════

async def generate_hdc():
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
    print(f"  LLM: {SETTINGS.llm_model}")

    # 检查是否已存在
    existing = await ov_ls(HDC_RESOURCE_BASE)
    if existing and len(existing) > 0:
        print(f"\n  ⚠️  HDC 数据已存在 ({len(existing)} 个条目)")
        answer = input("  是否重新生成? [y/N] ")
        if answer.lower() != "y":
            print("  → 跳过生成\n")
            return True
        print("  → 删除旧数据...")
        await ov_delete("/fs", {"uri": HDC_RESOURCE_BASE, "recursive": "true"})
        print("  [OK] 旧数据已删除")

    t0 = time.monotonic()

    llm = AsyncOpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.llm_base_url)
    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    onedba = get_onedba_client()

    collector = SchemaCollector(onedba)
    uploader = HDCUploader(ov)
    generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)

    print(f"\n  正在生成 HDC（预计 1-3 分钟，取决于表数量和 LLM 速度）...")
    print(f"  管线: 采集 schema → 列摘要 → 表描述 → 上传表 → 表关系 → 数据库摘要 → 上传摘要和关系\n")

    # ── 实时进度回调 ──
    # 每个步骤开始时打印 "[INFO] 正在执行...", 完成时打印 "[OK] 完成"
    _step_start_time: dict[str, float] = {}

    def _on_progress(step: str, info: dict):
        nonlocal _step_start_time
        label = info.get("phase_label", step)
        phase = info.get("phase", 0)
        status = info.get("status", "")

        if status == "running":
            _step_start_time[step] = time.monotonic()
            indicator = f"[{phase}/6]"
            extra = ""
            if "tables_total" in info:
                extra = f" ({info['tables_total']} 张表)"
            elif "tables_with_desc" in info:
                extra = f" ({info['tables_with_desc']} 张表)"
            elif "tables" in info:
                extra = f" ({info['tables']} 张表, {info.get('relationships', 0)} 个关系)"
            # 表流水线进度
            if step == "table_pipeline" and "tables_done" in info:
                done = info["tables_done"]
                total = info.get("tables_total", 0)
                pct = done / total * 100 if total else 0
                extra = f" ({done}/{total} 张表, {pct:.0f}%)"

            # ── 详细日志：逐表完成 ──
            if VERBOSE and step == "table_done":
                tn = info.get("table_name", "?")
                me = info.get("main_entity", "")
                tt = info.get("table_type", "")
                done = info.get("done", 0)
                total = info.get("total", 0)
                pct = done / total * 100 if total else 0
                me_str = f" → {me} [{tt}]" if me else ""
                print(f"       [{done}/{total} {pct:.0f}%] {tn}{me_str}")

            # ── 详细日志：关系检测 ──
            if VERBOSE and step == "relate_source":
                src = info.get("source_table", "?")
                cand = info.get("candidates", 0)
                find_src = info.get("find_source", "?")
                done = info.get("done", 0)
                total = info.get("total", 0)
                src_label = {"openviking": "OV", "fallback": "回退", "local": "本地", "none": "无"}.get(find_src, find_src)
                print(f"       [{done}/{total}] {src} → {cand} 候选 ({src_label})")

            if VERBOSE and step == "relate_found":
                src = info.get("source_table", "?")
                found = info.get("found", 0)
                targets = info.get("targets", [])
                targets_str = ", ".join(targets[:5])
                print(f"         {src}: 确认 {found} 个关系 → [{targets_str}]")

            print(f"  {indicator} {label}...{extra}")

        elif status == "done":
            elapsed = time.monotonic() - _step_start_time.get(step, 0)
            suffix = f" ({elapsed:.1f}s)"
            if step == "collect_schema":
                print(f"       [OK] 采集到 {info.get('tables_total', 0)} 张表{suffix}")
            elif step == "table_pipeline":
                ok = info.get("succeeded", 0)
                total = info.get("tables_total", 0)
                cols = info.get("total_columns", 0)
                print(f"       [OK] {ok}/{total} 张表, {cols} 个列{suffix}")
            elif step == "relationships":
                print(f"       [OK] 检测到 {info.get('count', 0)} 个关系{suffix}")
            elif step == "database_summary":
                hint = info.get("domain_hint", "")
                hint_str = f" — {hint}" if hint else ""
                print(f"       [OK]{hint_str}{suffix}")
            elif step == "upload_tables":
                tables = info.get("tables", 0)
                ok = "✅" if info.get("success") else "❌"
                print(f"       [{ok}] 上传表{'成功' if info.get('success') else '失败'} ({tables} 张表){suffix}")
            elif step == "upload_cascade":
                ok = "✅" if info.get("success") else "❌"
                rels = info.get("relationships", 0)
                print(f"       [{ok}] 上传摘要和关系{'成功' if info.get('success') else '失败'} ({rels} 个关系){suffix}")

    stats = await generator.generate(
        TARGET_SCHEMA_ID, TARGET_DB_NAME,
        tables=TARGET_TABLES,
        progress_callback=_on_progress,
    )
    elapsed = time.monotonic() - t0

    print(f"  ═══════════════════════════════════════════════════════════")
    print(f"  生成结果")
    print(f"  ═══════════════════════════════════════════════════════════")
    print(f"  模式:        {stats.get('mode', 'full')} {'(部分表)' if stats.get('mode') == 'partial' else '(全库)'}")
    print(f"  状态:        {stats.get('status', 'unknown')}")
    print(f"  表总数:      {stats.get('tables_total', 0)}")
    print(f"  成功:        {stats.get('tables_succeeded', 0)}")
    print(f"  列摘要:      {stats.get('columns', 0)}")
    print(f"  表关系:      {stats.get('relationships', 0)}")
    print(f"  耗时:        {elapsed:.1f}s")
    if stats.get("errors"):
        print(f"  错误数:      {len(stats['errors'])}")
        for err in stats["errors"][:5]:
            print(f"    • {err}")

    await ov.close()
    return True


# ═══════════════════════════════════════════════════════════════
#  Phase 2: 验证持久化
# ═══════════════════════════════════════════════════════════════

async def verify_persistence():
    """验证 HDC 数据已成功持久化到 OpenViking。"""
    print_section("Phase 2: 验证持久化")

    # ── 目录结构 ──
    print_sub("目录结构")
    entries = await ov_ls(HDC_RESOURCE_BASE)
    if not entries:
        print("  ❌ HDC 根目录为空 — 上传可能失败")
        return False

    tables_dir = [e for e in entries if e.get("name", "").startswith("_tables") or e.get("uri", "").endswith("_tables")]
    rel_dir = [e for e in entries if "relation" in (e.get("name", "") or "") or "relation" in (e.get("uri", "") or "")]
    index_files = [e for e in entries if not e.get("isDir")]

    print(f"  根目录条目: {len(entries)}")
    print(f"    目录: {sum(1 for e in entries if e.get('isDir'))} | 文件: {sum(1 for e in entries if not e.get('isDir'))}")

    # ── 表目录 ──
    tables_uri = f"{HDC_RESOURCE_BASE}/_tables"
    table_entries = await ov_ls(tables_uri)
    print(f"\n  _tables/ 条目: {len(table_entries)}")
    table_names = []
    for e in (table_entries or []):
        if e.get("isDir"):
            name = (e.get("name") or "").strip()
            if not name:
                uri = e.get("uri", "")
                name = uri.rstrip("/").split("/")[-1] if uri else "?"
            table_names.append(name)

    print(f"  表目录数: {len(table_names)}")
    for t in table_names:
        print(f"    📁 {t}")

    # ── 检查表内容 ──
    print_sub("表内容抽查（前 3 张表）")
    ok_count = 0
    fail_count = 0
    for t in table_names[:3]:
        table_uri = f"{tables_uri}/{t}"
        cols = await ov_ls(table_uri)
        index_file = any(("_INDEX.md" in (e.get("name", "") or "")) or ("_INDEX.md" in (e.get("uri", "") or "")) for e in (cols or []))
        col_files = sum(1 for e in (cols or []) if not e.get("isDir") and "_INDEX" not in (e.get("name", "") or ""))

        if index_file and col_files > 0:
            print(f"  ✅ {t}: _INDEX.md + {col_files} 列文件")
            ok_count += 1
        elif index_file:
            print(f"  ⚠️  {t}: _INDEX.md 存在，但无列文件")
            fail_count += 1
        else:
            print(f"  ❌ {t}: _INDEX.md 缺失")
            fail_count += 1

    # ── 读取 _INDEX.md 样例 ──
    if table_names:
        print_sub("表描述样例")
        sample_uri = f"{tables_uri}/{table_names[0]}/_INDEX.md"
        content = await ov_read(sample_uri)
        if content:
            lines = content.split("\n")[:15]
            for line in lines:
                if line.strip():
                    print(f"  {line}")
            if len(content.split("\n")) > 15:
                print(f"  ... (共 {len(content.splitlines())} 行)")
        else:
            print(f"  ❌ 无法读取 {sample_uri}")

    # ── 数据库摘要 ──
    print_sub("数据库摘要")
    db_index = await ov_read(f"{HDC_RESOURCE_BASE}/_INDEX.md")
    if db_index:
        lines = [l for l in db_index.split("\n") if l.strip() and not l.startswith("# ")][:5]
        for line in lines:
            print(f"  {line[:120]}")
    else:
        print(f"  ⚠️  数据库 _INDEX.md 不存在（可能被 SemanticProcessor 重命名）")

    # ── 关系目录 ──
    rel_uri = f"{HDC_RESOURCE_BASE}/_relationships"
    rel_entries = await ov_ls(rel_uri)
    rel_files = [e for e in (rel_entries or []) if not e.get("isDir")]
    print(f"\n  _relationships/ 文件数: {len(rel_files)}")
    for r in rel_files[:3]:
        print(f"    📄 {(r.get('name') or r.get('uri','').split('/')[-1])}")

    return ok_count > 0


# ═══════════════════════════════════════════════════════════════
#  Phase 3: 检索验证
# ═══════════════════════════════════════════════════════════════

async def verify_retrieval():
    """验证 HDC 检索能否找到匹配表。"""
    print_section("Phase 3: 检索验证")

    from app.datavault.retriever import HDCRetriever
    from app.knowledge.openviking import OpenVikingClient

    test_queries = [
        ("告警", "应匹配 db_alert_history（main_entity 含 '告警'）"),
        ("权限", "应匹配 dp_permission（main_entity 含 '权限'）"),
        ("表结构", "应匹配多张表"),
    ]

    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    retriever = HDCRetriever(ov)

    all_ok = True
    for query, expectation in test_queries:
        print_sub(f"查询: \"{query}\" — {expectation}")
        hdc_ctx = await retriever.retrieve(query, TARGET_SCHEMA_ID, TARGET_DB_NAME)
        if hdc_ctx and hdc_ctx.matched_tables:
            print(f"  ✅ 匹配 {len(hdc_ctx.matched_tables)} 张表:")
            for t in hdc_ctx.matched_tables:
                print(f"     • {t.table_name} — {t.main_entity} [{t.table_type}]")
                if t.relevant_columns:
                    print(f"       相关列: {', '.join(t.relevant_columns[:4])}")
        else:
            print(f"  ❌ 未匹配到表")
            all_ok = False

    await ov.close()
    return all_ok


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

async def main():
    # ── 配置日志 ──
    if VERBOSE:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        # 抑制 httpx 等第三方库的噪音
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
    else:
        logging.basicConfig(
            level=logging.WARNING,
            format="%(levelname)s: %(message)s",
        )

    print("=" * 70)
    print("  HDC 知识库生成验证")
    print("=" * 70)
    print(f"  目标: {TARGET_DB_NAME} (schemaId={TARGET_SCHEMA_ID})")
    print(f"  OpenViking: {OV_BASE_URL}")
    print(f"  LLM: {SETTINGS.llm_model}")
    print(f"  详细日志: {'开启' if VERBOSE else '关闭'} (使用 -v 开启)")
    print()

    # Phase 1: 生成
    ok = await generate_hdc()
    if not ok:
        print("\n[ERROR] HDC 生成失败")
        return

    # Phase 2: 验证持久化
    persisted = await verify_persistence()

    # Phase 3: 检索验证
    retrieval_ok = await verify_retrieval()

    # ── 总结 ──
    print_section("总结")
    print(f"  生成: ✅ 完成")
    print(f"  持久化: {'✅' if persisted else '❌'} {'成功' if persisted else '失败'}")
    print(f"  检索: {'✅' if retrieval_ok else '❌'} {'正常' if retrieval_ok else '异常'}")

    if persisted and retrieval_ok:
        print(f"\n  🎯 HDC 知识库已就绪，可以运行对比实验:")
        print(f"     python tests/datavault/demo_hdc_compare.py {TARGET_SCHEMA_ID} {TARGET_DB_NAME}")
    else:
        print(f"\n  ⚠️  请先排查上述问题后再运行对比实验")

    print(f"\n  手动验证命令:")
    print(f"     ov ls viking://resources/hdc/{TARGET_SCHEMA_ID}/{TARGET_DB_NAME}")
    print(f"     ov tree viking://resources/hdc/{TARGET_SCHEMA_ID}/{TARGET_DB_NAME} -L 3")


if __name__ == "__main__":
    asyncio.run(main())
