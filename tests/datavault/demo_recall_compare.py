#!/usr/bin/env python3
"""
HDC 召回准确率 A/B 对比实验
=============================

构造两个知识库（complete 6表 / overcomplete 11表），
对比新方案 vs 旧方案的检索准确率。

新方案：level=[0,1], limit=200, score_threshold=0.25, sum(top-3), 实体去重
旧方案：level=[2], limit=60, max(单列分), 无 threshold, 无去重

前置条件：OpenViking 运行在 localhost:1933
"""

import asyncio, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.knowledge.openviking import OpenVikingClient
from app.datavault.retriever import HDCRetriever
from app.datavault.uploader import (
    HDCUploader,
    _tables_dir_uri,
    _db_uri,
    storage_key,
)
from app.datavault.models import (
    ColumnSummary,
    TableDescriptionWithColumns,
)
from app.config import get_settings

# ══════════════ 配置 ══════════════
OV_URL = "http://localhost:1933"
SCHEMA_ID = 99999
DB_NAME = "recall_test_db"
COMPLETE_NS = "complete"
OVERCOMPLETE_NS = "overcomplete"

# ══════════════ 测试表定义 ══════════════

def make_cols(names: list[str]) -> list[ColumnSummary]:
    return [ColumnSummary(column_name=n, description=f"{n} 的业务描述", data_type="varchar", sample_values=[f"sample_{n}"]) for n in names]

# complete 场景：6 张表（核心业务表）
COMPLETE_TABLES = [
    TableDescriptionWithColumns(
        table_name="order_record", main_entity="工单/order", table_type="fact",
        primary_key="id", description="工单记录表，存储所有数据变更工单。", usage_scenario="查询工单状态、提交人、类型过滤时使用。",
        columns=make_cols(["id", "order_type", "committer_name", "status_desc", "create_time", "db_name", "sql_content"]),
    ),
    TableDescriptionWithColumns(
        table_name="db_alert_history", main_entity="告警/alert", table_type="fact",
        primary_key="id", description="告警历史记录表，存储所有系统告警事件。", usage_scenario="查询告警级别、类型、业务子域时使用。",
        columns=make_cols(["id", "level", "alert_type", "business_subdomain", "service_name", "alert_time", "message"]),
    ),
    TableDescriptionWithColumns(
        table_name="effect_dba_domain_cost_v2", main_entity="效能/efficiency", table_type="fact",
        primary_key="id", description="DBA 业务域成本统计表，按域汇总人力成本。", usage_scenario="统计各业务域成本、按负责人过滤时使用。",
        columns=make_cols(["id", "dba_domain", "cost_time", "dba_owner_name", "month", "year"]),
    ),
    TableDescriptionWithColumns(
        table_name="effect_daily_work_v2", main_entity="日常工作/daily_work", table_type="fact",
        primary_key="id", description="DBA 日常工作记录表，记录各类工作事项。", usage_scenario="统计工作类型、按飞书ID筛选时使用。",
        columns=make_cols(["id", "work_type", "feishu_id", "cost_time_hour", "cost_time_minute", "created_time", "description"]),
    ),
    TableDescriptionWithColumns(
        table_name="order_audit_record", main_entity="审计/audit", table_type="fact",
        primary_key="id", description="工单审核记录表，记录每一步审核详情。", usage_scenario="追溯审核步骤、统计每日审计量时使用。",
        columns=make_cols(["id", "order_id", "audit_stage", "audit_status", "risk_level", "create_time", "auditor"]),
    ),
    TableDescriptionWithColumns(
        table_name="db_account", main_entity="账户/account", table_type="dimension",
        primary_key="id", description="数据库账户信息表，管理所有 DB 账户。", usage_scenario="查询账户权限、过期时间时使用。",
        columns=make_cols(["id", "account_name", "host", "db_name", "privileges", "expire_time", "owner"]),
    ),
]

# overcomplete 场景：complete 6 表 + 5 张噪音表（同业务域相似表）
OVERCOMPLETE_EXTRA = [
    # 告警域相似表（噪音）
    TableDescriptionWithColumns(
        table_name="db_alert_daily", main_entity="告警/alert", table_type="fact",
        primary_key="id", description="告警日汇总表，按天聚合告警数据。", usage_scenario="查询每日告警汇总统计时使用。",
        columns=make_cols(["id", "alert_date", "level", "alert_count", "resolved_count", "avg_response_time"]),
    ),
    TableDescriptionWithColumns(
        table_name="effect_alert_v2", main_entity="告警/alert", table_type="fact",
        primary_key="id", description="告警效能统计表，关联告警与处理人效能。", usage_scenario="查询告警处理效率、责任人统计时使用。",
        columns=make_cols(["id", "alert_id", "handler", "response_time", "resolve_time", "is_escalated", "cost"]),
    ),
    # 工单域相似表（噪音）
    TableDescriptionWithColumns(
        table_name="order_task", main_entity="工单/order", table_type="fact",
        primary_key="id", description="工单任务子表，记录工单内的具体任务。", usage_scenario="查询工单任务执行进度时使用。",
        columns=make_cols(["id", "order_id", "task_name", "task_status", "assignee", "start_time", "end_time"]),
    ),
    # 效能域相似表（噪音）
    TableDescriptionWithColumns(
        table_name="effect_project_cost", main_entity="效能/efficiency", table_type="fact",
        primary_key="id", description="项目成本统计表，按项目汇总成本。", usage_scenario="查询项目维度成本分布时使用。",
        columns=make_cols(["id", "project_name", "cost_time", "dba_owner", "month", "year"]),
    ),
    # 日常域相似表（噪音）
    TableDescriptionWithColumns(
        table_name="daily_report", main_entity="日常工作/daily_work", table_type="fact",
        primary_key="id", description="日报表，记录每日工作总结。", usage_scenario="查询每日工作报告时使用。",
        columns=make_cols(["id", "report_date", "author", "content", "project", "hours"]),
    ),
]

# ══════════════ 测试查询列表 ══════════════
# 每个查询有预期正确表和业务域
QUERIES = [
    ("查询最近工单的提交人和状态", "order_record", "工单"),
    ("统计告警数量", "db_alert_history", "告警"),
    ("查询各业务域的成本时间", "effect_dba_domain_cost_v2", "效能"),
    ("统计日常工作类型", "effect_daily_work_v2", "日常工作"),
    ("查询审核记录", "order_audit_record", "审计"),
    ("查询数据库账户", "db_account", "账户"),
    ("查询 level=critical 的告警", "db_alert_history", "告警"),
    ("按月份统计工单数", "order_record", "工单"),
    ("查询效能负责人", "effect_dba_domain_cost_v2", "效能"),
    ("统计每日审计量", "order_audit_record", "审计"),
]


# ══════════════ 辅助函数 ══════════════

async def generate_kb(ov: OpenVikingClient, namespace: str, tables: list[TableDescriptionWithColumns]) -> str:
    """生成知识库，返回 key"""
    key = storage_key(SCHEMA_ID, DB_NAME, namespace=namespace)
    uploader = HDCUploader(ov)
    await uploader.upload_tables(key, tables)
    print(f"  -> 已生成 {len(tables)} 张表: {namespace}")
    return key


async def wait_for_ready(ov: OpenVikingClient, key: str, timeout: float = 120):
    """等待 L0/L1 就绪"""
    tables_uri = _tables_dir_uri(key)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = await ov.find("test", target_uri=tables_uri, level=[0, 1], limit=5)
        entries = r.get("resources", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
        if entries:
            print(f"  -> L0/L1 就绪 ({len(entries)} entries)")
            return True
        await asyncio.sleep(2)
    print(f"  -> 警告: L0/L1 未在 {timeout}s 内就绪")
    return False


async def run_new_retrieval(ov: OpenVikingClient, query: str, namespace: str) -> list[str]:
    """新方案检索"""
    retriever = HDCRetriever(ov)
    ctx = await retriever.retrieve(query, SCHEMA_ID, DB_NAME, namespace=namespace)
    return [t.table_name for t in (ctx.matched_tables if ctx else [])]


async def run_old_retrieval(ov: OpenVikingClient, query: str, namespace: str) -> list[str]:
    """旧方案检索（模拟）"""
    key = storage_key(SCHEMA_ID, DB_NAME, namespace=namespace)
    tables_uri = _tables_dir_uri(key)
    r = await ov.find(query, target_uri=tables_uri, level=[2], limit=60)
    matches = r.get("resources", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])

    # 旧方案表聚合：max(单匹配项分)
    candidates: dict[str, float] = {}
    for m in matches:
        uri = m.get("uri", "")
        parts = uri.rstrip("/").split("/")
        tn = "?"  # 尝试提取表名
        for i, p in enumerate(parts):
            if p == "_tables" and i + 1 < len(parts):
                tn = parts[i + 1]
                break
        if not tn or tn.startswith("_"):
            tn = parts[-1].replace(".md", "") if "." in parts[-1] else parts[-1]
        if tn.startswith("_"):
            continue
        candidates[tn] = max(candidates.get(tn, 0), m.get("score", 0))

    ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return [t for t, _ in ranked[:5]]


def compute_metrics(results: list[dict]) -> dict:
    """计算准确率指标"""
    total = len(results)
    hit1 = sum(1 for r in results if r["new_top1"] == r["expected"])
    hit5_new = sum(1 for r in results if r["expected"] in r["new_top5"])
    hit5_old = sum(1 for r in results if r["expected"] in r["old_top5"])
    return {
        "total": total,
        "new_top1_accuracy": hit1 / total * 100 if total else 0,
        "new_top5_recall": hit5_new / total * 100 if total else 0,
        "old_top5_recall": hit5_old / total * 100 if total else 0,
        "new_top1_count": hit1,
        "new_top5_count": hit5_new,
        "old_top5_count": hit5_old,
    }


# ══════════════ 主流程 ══════════════

async def main():
    print("=" * 70)
    print("  HDC 召回准确率 A/B 对比实验")
    print("=" * 70)

    ov = OpenVikingClient(OV_URL, "recall-test")
    await ov.start()

    # ── 清理上次残留 ──
    for ns in [COMPLETE_NS, OVERCOMPLETE_NS]:
        try:
            key = storage_key(SCHEMA_ID, DB_NAME, namespace=ns)
            await ov.rm(_db_uri(key), recursive=True)
            print(f"  -> 已清理旧数据: {ns}")
        except Exception:
            pass

    # ── 生成知识库 ──
    print("\n[1] 生成知识库...")
    comp_key = await generate_kb(ov, COMPLETE_NS, COMPLETE_TABLES)
    # 等待 complete 的 SemanticProcessor 完成，避免与下一批写冲突
    await wait_for_ready(ov, comp_key)
    await asyncio.sleep(3)  # 额外缓冲
    over_key = await generate_kb(ov, OVERCOMPLETE_NS, COMPLETE_TABLES + OVERCOMPLETE_EXTRA)
    await wait_for_ready(ov, over_key)

    # ── 对比实验 ──
    all_results = {"complete": [], "overcomplete": []}

    for scenario, ns, label in [("complete", COMPLETE_NS, "Complete (6表)"), ("overcomplete", OVERCOMPLETE_NS, "Overcomplete (11表)")]:
        print(f"\n[2] 对比实验: {label}")
        print("-" * 70)
        print(f"{'查询':<30} {'预期表':<28} {'新方案 Top-1':<28} {'新方案 Top-5':<40} {'旧方案 Top-5':<40}")
        print("-" * 130)

        for query, expected, domain in QUERIES:
            new_top5 = await run_new_retrieval(ov, query, ns)
            old_top5 = await run_old_retrieval(ov, query, ns)

            new_top1 = new_top5[0] if new_top5 else "NONE"
            new_mark = "✅" if expected in new_top5 else "❌"
            old_mark = "✅" if expected in old_top5 else "❌"

            print(f"{query[:30]:<30} {expected:<28} {new_top1:<28} {new_mark} {', '.join(new_top5[:5]):<34} {old_mark} {', '.join(old_top5[:5]):<34}")

            all_results[scenario].append({
                "query": query, "expected": expected,
                "new_top1": new_top1, "new_top5": new_top5, "old_top5": old_top5,
            })

    # ── 汇总 ──
    print("\n" + "=" * 70)
    print("  汇总对比")
    print("=" * 70)

    for scenario, label in [("complete", "Complete (6表)"), ("overcomplete", "Overcomplete (11表)")]:
        m = compute_metrics(all_results[scenario])
        print(f"\n{label}:")
        print(f"  新方案 Top-1 准确率: {m['new_top1_accuracy']:.1f}% ({m['new_top1_count']}/{m['total']})")
        print(f"  新方案 Top-5 召回率: {m['new_top5_recall']:.1f}% ({m['new_top5_count']}/{m['total']})")
        print(f"  旧方案 Top-5 召回率: {m['old_top5_recall']:.1f}% ({m['old_top5_count']}/{m['total']})")
        delta = m['new_top5_recall'] - m['old_top5_recall']
        print(f"  新方案提升: {delta:+.1f}%")

    # 关键对比：overcomplete 场景下新旧方案差异
    print(f"\n{'='*70}")
    print("  关键发现")
    print(f"{'='*70}")
    comp_m = compute_metrics(all_results["complete"])
    over_m = compute_metrics(all_results["overcomplete"])
    print(f"  Complete(6表) → Overcomplete(11表) 退化:")
    print(f"    新方案: {comp_m['new_top5_recall']:.1f}% → {over_m['new_top5_recall']:.1f}% ({over_m['new_top5_recall'] - comp_m['new_top5_recall']:+.1f}%)")
    print(f"    旧方案: {comp_m['old_top5_recall']:.1f}% → {over_m['old_top5_recall']:.1f}% ({over_m['old_top5_recall'] - comp_m['old_top5_recall']:+.1f}%)")

    if over_m['new_top5_recall'] > over_m['old_top5_recall']:
        print(f"\n  ✅ 新方案在 overcomplete 场景下召回率更高，退化幅度更小")
    else:
        print(f"\n  ⚠️ 新方案未超越旧方案，需进一步调参")

    # ── 清理 ──
    if "--keep" not in sys.argv:
        print("\n[3] 清理测试数据...")
        for ns in [COMPLETE_NS, OVERCOMPLETE_NS]:
            key = storage_key(SCHEMA_ID, DB_NAME, namespace=ns)
            await ov.rm(_db_uri(key), recursive=True)
        print("  -> 已清理")
    else:
        print("\n[3] --keep 指定，保留测试数据")

    await ov.close()


if __name__ == "__main__":
    asyncio.run(main())