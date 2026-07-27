#!/usr/bin/env python3
"""HDC 召回 A/B 对比：新方案 vs 旧方案。

绕过 OpenViking SemanticProcessor 超时：用 wait=False 直接写 L2 embedding，
检索时 retriever 自动走 level=[2] fallback。同时模拟旧方案做对比。

用法: python tests/datavault/demo_recall_check.py [--keep]
"""

import asyncio, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.knowledge.openviking import OpenVikingClient
from app.datavault.retriever import HDCRetriever
from app.datavault.uploader import (
    _db_uri, _tables_dir_uri, storage_key,
)
from app.datavault.models import ColumnSummary, TableDescriptionWithColumns

# ── 配置 ──
OV_URL = "http://localhost:1933"
SCHEMA_ID, DB_NAME = 99999, "recall_check_db"

def col(n, desc=None):
    return ColumnSummary(column_name=n, description=desc or f"{n} 的业务数据", data_type="varchar")

def T(name, entity, desc, usage, cols):
    return TableDescriptionWithColumns(
        table_name=name, main_entity=entity, table_type="fact",
        primary_key="id", description=desc, usage_scenario=usage,
        columns=cols)

COMPLETE = [
    T("order_record", "工单/order", "工单记录表，存储所有数据变更工单", "查询工单状态、提交人、类型过滤",
      [col("id"),col("order_type"),col("committer_name"),col("status_desc"),col("create_time"),col("db_name"),col("sql_content")]),
    T("db_alert_history", "告警/alert", "告警历史记录表，存储所有系统告警事件", "查询告警级别、类型、业务子域",
      [col("id"),col("level"),col("alert_type"),col("business_subdomain"),col("service_name"),col("alert_time")]),
    T("effect_dba_domain_cost_v2", "效能/efficiency", "DBA业务域成本统计表，按域汇总人力成本", "统计各业务域成本、按负责人过滤",
      [col("id"),col("dba_domain"),col("cost_time"),col("dba_owner_name"),col("month"),col("year")]),
    T("effect_daily_work_v2", "日常工作/daily_work", "DBA日常工作记录表，记录各类工作事项", "统计工作类型、按飞书ID筛选",
      [col("id"),col("work_type"),col("feishu_id"),col("cost_time_hour"),col("cost_time_minute"),col("created_time")]),
    T("order_audit_record", "审计/audit", "工单审核记录表，记录每一步审核详情", "追溯审核步骤、统计每日审计量",
      [col("id"),col("order_id"),col("audit_stage"),col("audit_status"),col("risk_level"),col("create_time")]),
    T("db_account", "账户/account", "数据库账户信息表，管理所有DB账户", "查询账户权限、过期时间",
      [col("id"),col("account_name"),col("host"),col("db_name"),col("privileges"),col("expire_time")]),
]
EXTRA = [
    T("db_alert_daily", "告警/alert", "告警日汇总表，按天聚合告警数据", "查询每日告警汇总统计",
      [col("id"),col("alert_date"),col("level"),col("alert_count"),col("resolved_count")]),
    T("effect_alert_v2", "告警/alert", "告警效能统计表，关联告警与处理人效能", "查询告警处理效率、责任人统计",
      [col("id"),col("alert_id"),col("handler"),col("response_time"),col("resolve_time")]),
    T("order_task", "工单/order", "工单任务子表，记录工单内的具体任务", "查询工单任务执行进度",
      [col("id"),col("order_id"),col("task_name"),col("task_status"),col("assignee")]),
    T("effect_project_cost", "效能/efficiency", "项目成本统计表，按项目汇总成本", "查询项目维度成本分布",
      [col("id"),col("project_name"),col("cost_time"),col("dba_owner"),col("month")]),
    T("daily_report", "日常工作/daily_work", "日报表，记录每日工作总结", "查询每日工作报告",
      [col("id"),col("report_date"),col("author"),col("content"),col("project")]),
]

QUERIES = [
    ("查询最近工单的提交人和状态", "order_record"),
    ("统计告警数量", "db_alert_history"),
    ("查询各业务域的成本时间", "effect_dba_domain_cost_v2"),
    ("统计日常工作类型", "effect_daily_work_v2"),
    ("查询审核记录", "order_audit_record"),
    ("查询数据库账户", "db_account"),
    ("查询 critical 级别的告警", "db_alert_history"),
    ("按月份统计工单数", "order_record"),
    ("查询效能负责人", "effect_dba_domain_cost_v2"),
    ("统计每日审计量", "order_audit_record"),
]

# ── 使用 HDCUploader 正常写入（含 L0/L1） ──
async def upload_kb_normal(ov, ns, tables):
    """使用 HDCUploader.upload_table()，wait=True 触发 L0/L1"""
    from app.datavault.uploader import HDCUploader
    key = storage_key(SCHEMA_ID, DB_NAME, namespace=ns)
    await HDCUploader(ov).upload_tables(key, tables)

    print(f"  [{ns}] {len(tables)} 表已写入 (正常路径: wait=True 含 L0/L1)")

    # 等待 L0/L1 就绪
    tables_uri = _tables_dir_uri(key)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        r = await ov.find("test", target_uri=tables_uri, level=[0, 1], limit=3)
        entries = r.get("resources", []) if isinstance(r, dict) else []
        if entries:
            abstract = entries[0].get("abstract", "") if entries else ""
            valid = abstract and "[Directory overview is not generated]" not in str(abstract)
            print(f"  [{ns}] L0/L1 就绪 ({len(entries)} entries, 有效={valid})")
            return key
        await asyncio.sleep(3)
    print(f"  [{ns}] 警告: L0/L1 超时")

# ── 旧方案检索（模拟） ──
async def run_old(ov, query, ns):
    """旧方案: level=[2], limit=60, max评分, 无threshold"""
    key = storage_key(SCHEMA_ID, DB_NAME, namespace=ns)
    r = await ov.find(query, target_uri=_tables_dir_uri(key), level=[2], limit=60)
    matches = r.get("resources", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
    candidates = {}
    for m in matches:
        uri = m.get("uri", ""); parts = uri.rstrip("/").split("/")
        tn = None
        for i, p in enumerate(parts):
            if p == "_tables" and i + 1 < len(parts): tn = parts[i + 1]; break
        if not tn or tn.startswith("_"): continue
        candidates[tn] = max(candidates.get(tn, 0), m.get("score", 0))
    return [t for t, _ in sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:5]]

# ── 主流程 ──
async def main():
    print("=" * 70)
    print("  HDC 召回 A/B 对比（绕过 SemanticProcessor）")
    print("=" * 70)

    ov = OpenVikingClient(OV_URL, "recall-test")
    await ov.start()

    # 清理旧
    for ns in ["complete", "overcomplete"]:
        try: await ov.rm(_db_uri(storage_key(SCHEMA_ID, DB_NAME, namespace=ns)), recursive=True)
        except: pass

    print("\n[1] 写入知识库...")
    await upload_kb_normal(ov, "complete", COMPLETE)
    await upload_kb_normal(ov, "overcomplete", COMPLETE + EXTRA)

    all_results = {"complete": [], "overcomplete": []}
    for scenario, ns, label in [("complete", "complete", "Complete (6表)"), ("overcomplete", "overcomplete", "Overcomplete (11表)")]:
        print(f"\n[2] 对比: {label}")
        print(f"  {'查询':<30} {'预期':<28} {'新Top-1':<28} {'新Hit':<6} {'旧Hit':<6}")
        print(f"  {'-'*105}")

        retriever = HDCRetriever(ov)
        for query, expected in QUERIES:
            ctx_new = await retriever.retrieve(query, SCHEMA_ID, DB_NAME, namespace=ns)
            new_top5 = [t.table_name for t in (ctx_new.matched_tables if ctx_new else [])]
            old_top5 = await run_old(ov, query, ns)
            nh = "✅" if expected in new_top5 else "❌"
            oh = "✅" if expected in old_top5 else "❌"
            print(f"  {query[:30]:<30} {expected:<28} {new_top5[0] if new_top5 else 'NONE':<28} {nh:<6} {oh:<6}")
            all_results[scenario].append({"expected": expected, "new_top5": new_top5, "old_top5": old_top5})

    print(f"\n{'='*70}")
    print("  汇总")
    print("=" * 70)
    for s, l in [("complete","Complete(6表)"), ("overcomplete","Overcomplete(11表)")]:
        r = all_results[s]; n = len(r)
        n5 = sum(1 for x in r if x["expected"] in x["new_top5"])
        o5 = sum(1 for x in r if x["expected"] in x["old_top5"])
        print(f"  {l}: 新方案 Top-5={n5}/{n} ({n5/n*100:.0f}%)  旧方案 Top-5={o5}/{n} ({o5/n*100:.0f}%)")

    # 清理
    if "--keep" not in sys.argv:
        for ns in ["complete", "overcomplete"]:
            await ov.rm(_db_uri(storage_key(SCHEMA_ID, DB_NAME, namespace=ns)), recursive=True)
        print("\n  已清理")
    else:
        print("\n  --keep: 保留数据")

    await ov.close()

if __name__ == "__main__":
    asyncio.run(main())