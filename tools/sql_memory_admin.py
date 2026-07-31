#!/usr/bin/env python3
"""
SQL 记忆库管理工具

用法:
    python tools/sql_memory_admin.py status          # 查看记忆库概览
    python tools/sql_memory_admin.py list            # 列出所有记录
    python tools/sql_memory_admin.py seed --file data.json --user alice  # 从文件灌入
    python tools/sql_memory_admin.py re-embed        # 重建所有 embedding
    python tools/sql_memory_admin.py re-embed --user default  # 指定用户
    python tools/sql_memory_admin.py clean           # 删除过期记录
    python tools/sql_memory_admin.py clean --all     # 清空记忆库
    python tools/sql_memory_admin.py stats           # 统计信息（表分布、状态分布等）

前置条件:
    export SQL_MEMORY_ENABLED=true
    export STORAGE_BACKEND=sqlite    # 可选，默认 memory
"""

import argparse
import asyncio
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def cmd_seed(args):
    """从 JSON 文件批量灌入 SQL 记忆"""
    from app.memory.manager import get_storage
    from app.memory.sql_memory import embed_text

    filepath = args.file
    if not os.path.exists(filepath):
        print(f"文件不存在: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 支持两种格式: 直接 records 数组, 或 {"user_id": "...", "records": [...]}
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict) and "records" in data:
        records = data["records"]
        if not args.user or args.user == "default":
            args.user = data.get("user_id", args.user)
    else:
        print("无效的 JSON 格式: 需要 records 数组或包含 user_id+records 的对象")
        return

    user_id = args.user or "default"
    store = get_storage().sql_memory_store
    if store is None:
        print("SQL 记忆存储未初始化，请设置 SQL_MEMORY_ENABLED=true")
        return

    await store.initialize()
    try:
        success = 0
        fail = 0
        for i, rec in enumerate(records):
            try:
                question = rec.get("question", "")
                sql = rec.get("sql", "")
                if not question or not sql:
                    print(f"  [{i}] 跳过: 缺少 question 或 sql")
                    fail += 1
                    continue

                table_names = rec.get("table_names", [])
                database_name = rec.get("database_name", "")
                schema_id = rec.get("schema_id", 0)
                execution_result = rec.get("execution_result", {})

                embedding = await embed_text(question)
                await store.record(
                    user_id=user_id,
                    question=question,
                    sql=sql,
                    table_names=table_names,
                    database_name=database_name,
                    schema_id=schema_id,
                    execution_result=execution_result,
                    embedding=embedding,
                )
                print(f"  [{i}] ✓ {question[:50]}")
                success += 1
            except Exception as e:
                print(f"  [{i}] ✗ {type(e).__name__}: {e}")
                fail += 1

        print(f"\n完成: user={user_id}  total={len(records)}  success={success}  failed={fail}")
    finally:
        await store.close()


async def cmd_status(args):
    """查看记忆库概览"""
    from app.memory.manager import get_storage
    store = get_storage().sql_memory_store
    if store is None:
        print("SQL 记忆存储未初始化，请设置 SQL_MEMORY_ENABLED=true")
        return
    await store.initialize()

    try:
        records = await store.list_by_user(args.user or "default", limit=1000)
        total = len(records)
        with_emb = sum(1 for r in records if r.get("embedding_json"))
        without_emb = total - with_emb

        print(f"总记录: {total}  |  有 embedding: {with_emb}  |  无 embedding: {without_emb}")
        if total > 0:
            statuses = {}
            for r in records:
                s = r.get("execution_status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
            print(f"状态分布: {statuses}")
            print(f"最早: {records[-1].get('created_at', '?')}")
            print(f"最新: {records[0].get('created_at', '?')}")
    finally:
        await store.close()


async def cmd_list(args):
    """列出记录"""
    from app.memory.manager import get_storage
    store = get_storage().sql_memory_store
    if store is None:
        print("SQL 记忆存储未初始化")
        return
    await store.initialize()

    try:
        records = await store.list_by_user(args.user or "default", limit=args.limit)
        for i, r in enumerate(records):
            emb = "✓" if r.get("embedding_json") else "✗"
            sql = (r.get("sql_text") or "")[:80]
            print(f"{i+1:3d}. [{emb}] [{r.get('execution_status', '?')}] {r.get('question', '')[:60]}")
            print(f"      SQL: {sql}")
            print(f"      db={r.get('database_name')}  created={r.get('created_at', '?')}")
            print()
    finally:
        await store.close()


async def cmd_re_embed(args):
    """重建 embedding"""
    from app.memory.manager import get_storage
    from app.memory.sql_memory import embed_text

    store = get_storage().sql_memory_store
    if store is None:
        print("SQL 记忆存储未初始化")
        return
    await store.initialize()

    try:
        user = args.user or "default"
        print(f"正在重建 embedding（user={user}）...")
        updated = await store.re_embed_all(embed_fn=embed_text, user_id=user)
        print(f"完成: 已重建 {updated} 条记录")
    finally:
        await store.close()


async def cmd_clean(args):
    """清理记录"""
    from app.memory.manager import get_storage
    store = get_storage().sql_memory_store
    if store is None:
        print("SQL 记忆存储未初始化")
        return
    await store.initialize()

    try:
        if args.all:
            # 确认
            if not args.force:
                resp = input("确认清空所有记忆记录？[y/N] ")
                if resp.lower() != "y":
                    print("已取消")
                    return
            # 通过重新初始化清空表
            if hasattr(store, "_conn") and store._conn is not None:
                await store._conn.execute("DELETE FROM sql_memories")
                await store._conn.commit()
                remaining = await store._conn.execute_fetchall("SELECT COUNT(*) as cnt FROM sql_memories")
            else:
                print("无法访问底层连接，请使用 SQLite 后端")
                return
            print("所有记录已清空")
        else:
            ttl = args.ttl_days or 90
            deleted = await store.delete_expired(ttl)
            print(f"已删除 {deleted} 条超过 {ttl} 天的记录")
    finally:
        await store.close()


async def cmd_stats(args):
    """统计信息"""
    from app.memory.manager import get_storage
    store = get_storage().sql_memory_store
    if store is None:
        print("SQL 记忆存储未初始化")
        return
    await store.initialize()

    try:
        records = await store.list_by_user(args.user or "default", limit=10000)
        if not records:
            print("无记录")
            return

        print(f"总记录: {len(records)}")

        # 表分布
        tables: dict[str, int] = {}
        for r in records:
            for t in r.get("table_names", []):
                tables[t] = tables.get(t, 0) + 1
        if tables:
            print("\n高频表:")
            for t, c in sorted(tables.items(), key=lambda x: -x[1])[:10]:
                print(f"  {t}: {c} 次")

        # 数据库分布
        dbs: dict[str, int] = {}
        for r in records:
            db = r.get("database_name", "?")
            dbs[db] = dbs.get(db, 0) + 1
        print(f"\n数据库分布: {dbs}")

        # 按天分布
        days: dict[str, int] = {}
        for r in records:
            day = (r.get("created_at") or "")[:10]
            if day:
                days[day] = days.get(day, 0) + 1
        if days:
            print("\n按天统计:")
            for day in sorted(days.keys()):
                bar = "█" * days[day]
                print(f"  {day}: {bar} ({days[day]})")

        # 模式挖掘
        if args.mine:
            db_name = records[0].get("database_name", "")
            patterns = await store.mine_patterns(db_name, min_records=5)
            if patterns.get("top_tables"):
                print(f"\n挖掘结果:")
                print(f"  top_tables: {[(t['table'], t['count']) for t in patterns['top_tables'][:5]]}")
                if patterns.get("top_condition_patterns"):
                    print(f"  top_conditions: {patterns['top_condition_patterns'][0]['pattern'][:60]}...")
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description="SQL 记忆库管理工具")
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="查看记忆库概览")
    p_status.add_argument("--user", default="default", help="用户 ID")
    p_status.set_defaults(func=cmd_status)

    p_list = sub.add_parser("list", help="列出所有记录")
    p_list.add_argument("--user", default="default", help="用户 ID")
    p_list.add_argument("--limit", type=int, default=50, help="最大条数")
    p_list.set_defaults(func=cmd_list)

    p_seed = sub.add_parser("seed", help="从 JSON 文件批量灌入 SQL 记忆")
    p_seed.add_argument("--file", required=True, help="JSON 文件路径")
    p_seed.add_argument("--user", default="default", help="目标用户 ID（文件中有 user_id 时可选）")
    p_seed.set_defaults(func=cmd_seed)

    p_re = sub.add_parser("re-embed", help="重建 embedding")
    p_re.add_argument("--user", default="default", help="用户 ID")
    p_re.set_defaults(func=cmd_re_embed)

    p_clean = sub.add_parser("clean", help="清理记录")
    p_clean.add_argument("--ttl-days", type=int, default=90, help="过期天数")
    p_clean.add_argument("--all", action="store_true", help="清空全部记录")
    p_clean.add_argument("--force", "-f", action="store_true", help="跳过确认")
    p_clean.set_defaults(func=cmd_clean)

    p_stats = sub.add_parser("stats", help="统计信息")
    p_stats.add_argument("--user", default="default", help="用户 ID")
    p_stats.add_argument("--mine", action="store_true", help="同时运行模式挖掘")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return

    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()