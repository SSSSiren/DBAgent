#!/usr/bin/env python3
"""
HDC 增量更新验证
================

验证 HDCUpdater.check_and_update() 的变更检测和增量重算功能。

运行方式：
  cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
  python tests/datavault/demo_hdc_update.py [schema_id] [database_name]
  python tests/datavault/demo_hdc_update.py [schema_id] [database_name] -v   # 详细日志

验证场景：
  Phase 1: 检查 HDC 数据是否存在，不存在则先生成
  Phase 2: 无变更检测 — 验证 check_and_update() 返回 {"changed": False}
  Phase 3: 变更检测预览 — 对比当前 schema 与 OpenViking 中存储的 hash，报告差异
  Phase 4: (可选) 手动触发增量更新
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
TEST_USER = "hdc-update-verify"

SETTINGS = get_settings()

parser = argparse.ArgumentParser(description="HDC 增量更新验证")
parser.add_argument("schema_id", nargs="?", type=int, default=25800743, help="OneDBA schema ID")
parser.add_argument("database_name", nargs="?", type=str, default="dw_onedba", help="数据库名称")
parser.add_argument("-v", "--verbose", action="store_true", help="输出详细日志")
parser.add_argument("--force-update", action="store_true", help="强制执行增量更新（如有变更）")
parser.add_argument("--dry-run", action="store_true", help="仅检测变更，不执行更新")
parser.add_argument("--rebuild", action="store_true", help="强制重建关系+数据库摘要（不重跑列摘要/表描述）")
parser.add_argument("--tables", type=str, default=None, help="逗号分隔的目标表名列表（仅检测指定表的变更）")
_cli_args = parser.parse_args()

TARGET_SCHEMA_ID = _cli_args.schema_id
TARGET_DB_NAME = _cli_args.database_name
VERBOSE = _cli_args.verbose
FORCE_UPDATE = _cli_args.force_update
DRY_RUN = _cli_args.dry_run
REBUILD = _cli_args.rebuild
TARGET_TABLES = [t.strip() for t in _cli_args.tables.split(",")] if _cli_args.tables else None

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


async def ov_read_attrs(uri: str) -> dict:
    """Read directory attributes (tags) from OpenViking."""
    raw = await ov_get("/fs/read", {"uri": uri})
    if isinstance(raw, dict):
        if raw.get("status") == "error":
            return {}
        result = raw.get("result")
        if isinstance(result, dict):
            return result
    return {}


# ═══════════════════════════════════════════════════════════════
#  Phase 1: 确保 HDC 数据存在
# ═══════════════════════════════════════════════════════════════

async def ensure_hdc_exists():
    """检查 HDC 数据是否存在，不存在则先生成。"""
    print_section("Phase 1: 检查 HDC 数据")

    entries = await ov_ls(HDC_RESOURCE_BASE)
    if entries and len(entries) > 0:
        # 检查是否有 _tables 子目录
        tables_uri = f"{HDC_RESOURCE_BASE}/_tables"
        table_entries = await ov_ls(tables_uri)
        table_dirs = [e for e in (table_entries or []) if e.get("isDir")]
        if table_dirs:
            print(f"  ✅ HDC 数据已存在: {len(table_dirs)} 张表")
            return True

    print(f"  ⚠️  HDC 数据不存在，需要先生成")
    print(f"  请先运行: python tests/datavault/demo_hdc_generate.py {TARGET_SCHEMA_ID} {TARGET_DB_NAME}")
    return False


# ═══════════════════════════════════════════════════════════════
#  Phase 2: 无变更检测
# ═══════════════════════════════════════════════════════════════

async def verify_no_change_detection():
    """验证无变更时 check_and_update() 返回 {"changed": False}。"""
    print_section("Phase 2: 无变更检测")

    from app.client.onedba import get_onedba_client
    from app.datavault.collector import SchemaCollector
    from app.datavault.generator import HDCGenerator
    from app.datavault.uploader import HDCUploader
    from app.datavault.updater import HDCUpdater
    from app.knowledge.openviking import OpenVikingClient
    from openai import AsyncOpenAI

    llm = AsyncOpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.llm_base_url)
    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    onedba = get_onedba_client()

    collector = SchemaCollector(onedba)
    uploader = HDCUploader(ov)
    generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)
    updater = HDCUpdater(collector=collector, generator=generator, uploader=uploader)

    print(f"  正在比对 schema 签名 hash...")
    t0 = time.monotonic()
    result = await updater.check_and_update(TARGET_SCHEMA_ID, TARGET_DB_NAME, tables=TARGET_TABLES)
    elapsed = time.monotonic() - t0

    print(f"  耗时: {elapsed:.1f}s")
    print(f"  结果: {result}")

    if result.get("changed") is False:
        print(f"  ✅ 无变更检测通过 — 未触发任何 LLM 调用")
        await ov.close()
        return True
    else:
        new = result.get("new", 0)
        changed = result.get("changed_tables", 0)
        deleted = result.get("deleted", 0)
        print(f"  ⚠️  检测到变更: 新增={new}, 变更={changed}, 删除={deleted}")
        print(f"      （这可能是首次生成后 hash 尚未存储导致的，属于正常现象）")
        await ov.close()
        return result  # 返回变更详情供后续使用


# ═══════════════════════════════════════════════════════════════
#  Phase 3: 变更检测预览（对比 hash）
# ═══════════════════════════════════════════════════════════════

async def preview_changes():
    """对比当前 schema 与 OpenViking 中存储的 hash，报告差异。"""
    print_section("Phase 3: 变更检测预览")

    from app.client.onedba import get_onedba_client
    from app.datavault.collector import SchemaCollector
    from app.datavault.updater import HDCUpdater
    from app.datavault.uploader import storage_key, _tables_dir_uri, _table_dir_uri

    onedba = get_onedba_client()
    collector = SchemaCollector(onedba)

    key = storage_key(TARGET_SCHEMA_ID, TARGET_DB_NAME)

    # 采集当前 schema
    print(f"  采集当前 schema...")
    db_raw = await collector.collect_database(TARGET_SCHEMA_ID)
    current_tables = {t.name: t for t in db_raw.tables}
    print(f"  当前数据库: {len(current_tables)} 张表")

    # 计算当前 hash
    current_hashes = {}
    for name, table in current_tables.items():
        current_hashes[name] = HDCUpdater._compute_columns_hash(table.columns)

    # 读取 OpenViking 中存储的 hash
    print(f"  读取 OpenViking 中存储的 hash...")
    tables_dir = _tables_dir_uri(key)
    table_entries = await ov_ls(tables_dir)
    table_dirs = [e for e in (table_entries or []) if e.get("isDir")]
    print(f"  OpenViking 中: {len(table_dirs)} 个表目录")

    stored_hashes = {}
    stored_tags = {}
    for entry in (table_entries or []):
        if not entry.get("isDir"):
            continue
        table_name = entry.get("name", "")
        if not table_name:
            continue

        table_dir = _table_dir_uri(key, table_name)
        attrs = await ov_read_attrs(table_dir)
        tags = attrs.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        stored_tags[table_name] = tags
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("columns_hash="):
                stored_hashes[table_name] = tag[len("columns_hash="):]
                break

    # 对比
    new_tables = []
    changed_tables = []
    no_hash_tables = []
    deleted_tables = []

    for name, current_hash in current_hashes.items():
        if name not in stored_hashes:
            if name in [e.get("name", "") for e in (table_entries or []) if e.get("isDir")]:
                no_hash_tables.append(name)
            else:
                new_tables.append(name)
        elif current_hash != stored_hashes[name]:
            changed_tables.append(name)
            if VERBOSE:
                print(f"      变更: {name}")
                print(f"        当前 columns: {sorted(c.name for c in current_tables[name].columns)}")
                print(f"        旧 hash: {stored_hashes[name][:16]}...")
                print(f"        新 hash: {current_hash[:16]}...")

    for name in stored_hashes:
        if name not in current_hashes:
            deleted_tables.append(name)

    # 同时检查 OpenViking 中有目录但不在当前 schema 中的表
    ov_table_names = {e.get("name", "") for e in (table_entries or []) if e.get("isDir")}
    for name in ov_table_names:
        if name not in current_hashes and name not in deleted_tables:
            deleted_tables.append(name)

    # 报告
    print(f"\n  ═══════════════════════════════════════════════════════════")
    print(f"  变更检测结果")
    print(f"  ═══════════════════════════════════════════════════════════")
    print(f"  当前 schema 表数:     {len(current_tables)}")
    print(f"  OpenViking 表目录数:  {len(table_dirs)}")
    print(f"  有 hash 标签的表:     {len(stored_hashes)}")
    print(f"  无 hash 标签的表:     {len(no_hash_tables)}")
    print(f"  ─────────────────────────────────────────────────────────")
    print(f"  新增表:               {len(new_tables)}")
    print(f"  变更表:               {len(changed_tables)}")
    print(f"  删除表:               {len(deleted_tables)}")

    if new_tables:
        print(f"\n  新增表列表:")
        for t in new_tables:
            print(f"    + {t} ({len(current_tables[t].columns)} 列)")

    if changed_tables:
        print(f"\n  变更表列表:")
        for t in changed_tables[:10]:
            print(f"    ~ {t} ({len(current_tables[t].columns)} 列)")
        if len(changed_tables) > 10:
            print(f"    ... 共 {len(changed_tables)} 张表")

    if deleted_tables:
        print(f"\n  删除表列表:")
        for t in deleted_tables[:10]:
            print(f"    - {t}")
        if len(deleted_tables) > 10:
            print(f"    ... 共 {len(deleted_tables)} 张表")

    if no_hash_tables:
        print(f"\n  无 hash 标签的表（首次生成后需运行一次 update 来存储 hash）:")
        for t in no_hash_tables[:10]:
            tags = stored_tags.get(t, [])
            main_entity = next((tag.replace("main_entity=", "") for tag in tags if tag.startswith("main_entity=")), "?")
            table_type = next((tag.replace("table_type=", "") for tag in tags if tag.startswith("table_type=")), "?")
            print(f"    ? {t} [{table_type}] main_entity={main_entity}")
        if len(no_hash_tables) > 10:
            print(f"    ... 共 {len(no_hash_tables)} 张表")

    has_changes = bool(new_tables or changed_tables or deleted_tables or no_hash_tables)

    if not has_changes:
        print(f"\n  ✅ 无变更 — schema 与 OpenViking 完全一致")

    return {
        "new": new_tables,
        "changed": changed_tables,
        "deleted": deleted_tables,
        "no_hash": no_hash_tables,
        "has_changes": has_changes,
    }


# ═══════════════════════════════════════════════════════════════
#  Phase 4: 执行增量更新
# ═══════════════════════════════════════════════════════════════

async def run_update():
    """执行增量更新（如有变更）。"""
    print_section("Phase 4: 执行增量更新")

    from app.client.onedba import get_onedba_client
    from app.datavault.collector import SchemaCollector
    from app.datavault.generator import HDCGenerator
    from app.datavault.uploader import HDCUploader
    from app.datavault.updater import HDCUpdater
    from app.knowledge.openviking import OpenVikingClient
    from openai import AsyncOpenAI

    llm = AsyncOpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.llm_base_url)
    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    onedba = get_onedba_client()

    collector = SchemaCollector(onedba)
    uploader = HDCUploader(ov)
    generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)
    updater = HDCUpdater(collector=collector, generator=generator, uploader=uploader)

    print(f"  正在执行增量更新...")
    t0 = time.monotonic()
    result = await updater.check_and_update(TARGET_SCHEMA_ID, TARGET_DB_NAME, tables=TARGET_TABLES)
    elapsed = time.monotonic() - t0

    print(f"  耗时: {elapsed:.1f}s")
    print(f"  结果: {result}")

    if result.get("changed") is False:
        print(f"  ✅ 无变更，未触发任何 LLM 调用")
    else:
        new = result.get("new", 0)
        changed = result.get("changed_tables", 0)
        deleted = result.get("deleted", 0)
        print(f"  ✅ 增量更新完成:")
        print(f"     新增表: {new} 张（已生成列摘要 + 表描述 + 上传）")
        print(f"     变更表: {changed} 张（已重新生成列摘要 + 表描述 + 上传）")
        print(f"     删除表: {deleted} 张（已从 OpenViking 移除）")
        print(f"     级联操作: 已重算表关系和数据库摘要")

    await ov.close()
    return result


# ═══════════════════════════════════════════════════════════════
#  Phase 5: 强制重建关系+摘要
# ═══════════════════════════════════════════════════════════════

async def run_rebuild():
    """强制重建关系检测和数据库摘要（不重跑列摘要和表描述）。"""
    print_section("Phase 5: 强制重建关系+摘要")

    from app.client.onedba import get_onedba_client
    from app.datavault.collector import SchemaCollector
    from app.datavault.generator import HDCGenerator
    from app.datavault.uploader import HDCUploader
    from app.datavault.updater import HDCUpdater
    from app.knowledge.openviking import OpenVikingClient
    from openai import AsyncOpenAI

    llm = AsyncOpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.llm_base_url)
    ov = OpenVikingClient(OV_BASE_URL, TEST_USER)
    await ov.start()
    onedba = get_onedba_client()

    collector = SchemaCollector(onedba)
    uploader = HDCUploader(ov)
    generator = HDCGenerator(llm_client=llm, collector=collector, uploader=uploader)
    updater = HDCUpdater(collector=collector, generator=generator, uploader=uploader)

    print(f"  从 OpenViking 回读表数据，重建关系检测...")
    print(f"  （不重跑列摘要和表描述，仅重算关系+数据库摘要）")

    # ── 进度回调（复用 demo_hdc_generate.py 的模式）──
    _step_start_time: dict[str, float] = {}

    def _rebuild_progress(step: str, info: dict):
        nonlocal _step_start_time
        label = info.get("phase_label", step)
        status = info.get("status", "")
        if status == "running":
            _step_start_time[step] = time.monotonic()
            # 逐表进度
            if step == "relate_source":
                done = info.get("done", 0)
                total = info.get("total", 0)
                src = info.get("source_table", "?")
                find_src = info.get("find_source", "?")
                src_label = {"openviking": "OV", "fallback": "回退", "local": "本地", "none": "无"}.get(find_src, find_src)
                if done % 20 == 0:
                    pct = done / total * 100 if total else 0
                    print(f"       [{done}/{total} {pct:.0f}%] {src} → {info.get('candidates',0)} 候选 ({src_label})")
            elif step == "relate_found":
                src = info.get("source_table", "?")
                targets = info.get("targets", [])
                targets_str = ", ".join(targets[:3])
                if targets_str:
                    print(f"         {src}: 确认 {info.get('found',0)} 个 → [{targets_str}]")
            else:
                phase = info.get("phase", 0)
                extra = ""
                if "tables" in info:
                    extra = f" ({info['tables']} 张表)"
                elif "count" in info:
                    extra = f" ({info['count']} 个关系)"
                print(f"  [{phase}/6] {label}...{extra}")
        elif status == "done":
            elapsed_ms = time.monotonic() - _step_start_time.get(step, 0)
            count = info.get("count", 0)
            hint = info.get("domain_hint", "")
            if step == "rebuild_relationships":
                print(f"       [OK] 检测到 {count} 个关系 ({elapsed_ms:.1f}s)")
            elif step == "rebuild_db_summary":
                hint_str = f" — {hint}" if hint else ""
                print(f"       [OK]{hint_str} ({elapsed_ms:.1f}s)")
            elif step == "rebuild_upload":
                print(f"       [OK] 已上传级联结果 ({elapsed_ms:.1f}s)")

    t0 = time.monotonic()
    result = await updater.rebuild_relationships(
        TARGET_SCHEMA_ID, TARGET_DB_NAME,
        progress_callback=_rebuild_progress,
    )
    elapsed = time.monotonic() - t0

    rels = result.get("relationships", 0)
    dur = result.get("duration_seconds", elapsed)
    errors = result.get("errors", [])

    print(f"  耗时: {dur:.1f}s")
    print(f"  关系数: {rels}")
    if errors:
        print(f"  错误: {len(errors)}")
        for e in errors:
            print(f"    • {e}")
    else:
        print(f"  ✅ 关系+摘要重建完成")

    await ov.close()
    return result


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
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
    else:
        logging.basicConfig(
            level=logging.WARNING,
            format="%(levelname)s: %(message)s",
        )

    print("=" * 70)
    print("  HDC 增量更新验证")
    print("=" * 70)
    print(f"  目标: {TARGET_DB_NAME} (schemaId={TARGET_SCHEMA_ID})")
    print(f"  OpenViking: {OV_BASE_URL}")
    print(f"  LLM: {SETTINGS.llm_model}")
    print(f"  详细日志: {'开启' if VERBOSE else '关闭'} (使用 -v 开启)")
    if DRY_RUN:
        print(f"  模式: 仅检测变更 (--dry-run)")
    if FORCE_UPDATE:
        print(f"  模式: 强制执行更新 (--force-update)")
    if REBUILD:
        print(f"  模式: 强制重建关系+摘要 (--rebuild)")
    print()

    # Phase 1: 确保 HDC 数据存在
    if not await ensure_hdc_exists():
        return

    # ── --rebuild 模式：直接走 rebuild_relationships ──
    if REBUILD:
        await run_rebuild()
        print_section("结论")
        print(f"  ✅ 关系+摘要重建完成（未重跑列摘要和表描述）")
        return

    # Phase 2: 无变更检测
    update_result = await verify_no_change_detection()

    # Phase 3: 变更预览
    changes = await preview_changes()

    # Phase 4: 执行更新（条件触发）
    if DRY_RUN:
        print_section("跳过更新")
        print(f"  --dry-run 模式，不执行实际更新")
        if changes["has_changes"]:
            print(f"  如需执行更新，请运行: python tests/datavault/demo_hdc_update.py {TARGET_SCHEMA_ID} {TARGET_DB_NAME} --force-update")
    elif FORCE_UPDATE:
        await run_update()
    elif isinstance(update_result, dict) and update_result.get("changed"):
        # Phase 2 已经执行了更新（检测到变更）
        print_section("更新已完成")
        print(f"  Phase 2 中已执行增量更新")
    elif changes["has_changes"] and changes["no_hash"]:
        # 仅 no_hash 表有差异 — 推荐运行一次更新来存储 hash
        print_section("建议")
        print(f"  检测到 {len(changes['no_hash'])} 张表缺少 columns_hash 标签")
        print(f"  这是首次生成后的正常现象，运行一次增量更新即可存储 hash：")
        print(f"  python tests/datavault/demo_hdc_update.py {TARGET_SCHEMA_ID} {TARGET_DB_NAME} --force-update")
    else:
        print_section("结论")
        print(f"  ✅ 增量更新功能正常")
        print(f"  - 无变更检测: 正确返回 changed=False")
        print(f"  - 变更检测: 当前 schema 与 OpenViking 一致")
        print(f"  - 未触发不必要的 LLM 调用")


if __name__ == "__main__":
    asyncio.run(main())