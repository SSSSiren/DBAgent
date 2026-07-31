#!/usr/bin/env python3
"""
OneDBA 并发压测工具

测试 query_database 工具在不同并发度下的延迟表现，
分离网络排队 vs SQL 执行时间。

用法:
    python tools/onedba_bench.py                # 默认 concurrency=[1,4,8], repeat=5
    python tools/onedba_bench.py -c 1 2 4 8 16  # 自定义并发度
    python tools/onedba_bench.py -r 10           # 每并发度重复 10 次
    python tools/onedba_bench.py --sql "SELECT COUNT(*) FROM order_record"
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings

# ── 测试 SQL（简短，排除 SQL 执行差异）──
DEFAULT_SQLS = [
    ("simple_count", "SELECT COUNT(*) FROM order_record"),
    ("simple_filter", "SELECT id, committer_name FROM order_record WHERE is_finished = 1 LIMIT 10"),
    ("aggregation", "SELECT order_type, COUNT(*) FROM order_record GROUP BY order_type"),
]

# ── 从 .env 读取 OneDBA 配置 ──
settings = get_settings()
SCHEMA_ID = 65938636  # dw_onedba


async def _run_single(sql: str, label: str) -> dict:
    """执行单次 SQL 查询，返回耗时详情"""
    from app.client.onedba import get_onedba_client

    client = get_onedba_client()

    t0 = time.monotonic()
    try:
        result = await client.execute_sql(SCHEMA_ID, sql)
        elapsed_ms = (time.monotonic() - t0) * 1000
        rows = len(result.get("columnDatas", [])) if isinstance(result, dict) else 0
        return {
            "label": label,
            "elapsed_ms": round(elapsed_ms, 2),
            "rows": rows,
            "error": None,
        }
    except Exception as e:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return {
            "label": label,
            "elapsed_ms": round(elapsed_ms, 2),
            "rows": 0,
            "error": str(e)[:200],
        }


async def _run_concurrent(concurrency: int, sql: str, label: str, repeat: int) -> list[dict]:
    """以指定并发度重复执行 SQL"""
    tasks = [_run_single(sql, label) for _ in range(concurrency * repeat)]

    # 分批执行：每批 concurrency 个并发
    results = []
    for i in range(0, len(tasks), concurrency):
        batch = tasks[i : i + concurrency]
        batch_results = await asyncio.gather(*batch)
        results.extend(batch_results)

    return results


def _stats(results: list[dict]) -> dict:
    """计算统计指标"""
    latencies = [r["elapsed_ms"] for r in results if r["error"] is None]
    errors = [r for r in results if r["error"] is not None]

    if not latencies:
        return {"count": len(results), "error_count": len(errors), "error_rate": 1.0}

    latencies.sort()
    n = len(latencies)

    return {
        "count": len(results),
        "error_count": len(errors),
        "error_rate": round(len(errors) / len(results), 4),
        "p50_ms": round(latencies[n // 2], 2),
        "p95_ms": round(latencies[int(n * 0.95)], 2),
        "p99_ms": round(latencies[int(n * 0.99)], 2) if n > 1 else round(latencies[0], 2),
        "min_ms": round(latencies[0], 2),
        "max_ms": round(latencies[-1], 2),
        "avg_ms": round(sum(latencies) / n, 2),
    }


async def main():
    parser = argparse.ArgumentParser(description="OneDBA 并发压测")
    parser.add_argument("-c", "--concurrency", type=int, nargs="+", default=[1, 4, 8],
                        help="并发度列表（默认 1 4 8）")
    parser.add_argument("-r", "--repeat", type=int, default=5,
                        help="每并发度重复次数（默认 5）")
    parser.add_argument("--sql", type=str, default=None,
                        help="自定义 SQL（覆盖默认 SQL 列表）")
    args = parser.parse_args()

    sqls = [(f"custom", args.sql)] if args.sql else DEFAULT_SQLS

    print(f"OneDBA 并发压测 — schemaId={SCHEMA_ID}")
    print(f"并发度: {args.concurrency}")
    print(f"每并发度重复: {args.repeat}")
    print(f"测试 SQL: {[s[0] for s in sqls]}")
    print()

    # 表头
    header = f"{'SQL':<18} | {'并发':>4} | {'次数':>5} | {'错误率':>6} | {'Avg':>8} | {'P50':>8} | {'P95':>8} | {'P99':>8} | {'Min':>8} | {'Max':>8}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for label, sql in sqls:
        for conc in args.concurrency:
            results = await _run_concurrent(conc, sql, label, args.repeat)
            stats = _stats(results)
            print(
                f"{label:<18} | {conc:>4} | {stats['count']:>5} | "
                f"{stats['error_rate']:>5.0%} | {stats['avg_ms']:>7.1f}ms | "
                f"{stats['p50_ms']:>7.1f}ms | {stats['p95_ms']:>7.1f}ms | "
                f"{stats['p99_ms']:>7.1f}ms | {stats['min_ms']:>7.1f}ms | "
                f"{stats['max_ms']:>7.1f}ms"
            )
        print()

    print(sep)
    print(f"LLM Base URL: {settings.llm_base_url}")
    print(f"OneDBA Base URL: {settings.onedba_base_url}")


if __name__ == "__main__":
    asyncio.run(main())