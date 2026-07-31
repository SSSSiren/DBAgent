#!/usr/bin/env python3
"""
LLM API 并发压测工具（真实 Agent prompt 版）

使用与 Agent 实际发送的完整系统提示词 + 上下文 + 全部工具定义，
测量真实场景下 LLM API 在不同并发度下的 TTFB 和总延迟。

用法:
    python tools/llm_api_bench.py                # 默认 concurrency=[1,4,8], repeat=3
    python tools/llm_api_bench.py -c 1 2 4 8     # 自定义并发度
    python tools/llm_api_bench.py -r 5            # 每并发度重复 5 次
    python tools/llm_api_bench.py --non-stream     # 非流式模式
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openai import AsyncOpenAI
from app.config import get_settings
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.runner import _build_tool_schemas

settings = get_settings()

# ── 构建与 Agent 实际发送一致的 prompt ──
TOOLS = _build_tool_schemas()

# 模拟 Agent 实际上下文（含 7 段 + 数据库信息 + 用户问题）
CONTEXT = f"""当前选择的数据库: dw_onedba (schema_id=65938636)

[对话历史]
用户: 帮我查一下工单系统里的数据变更类工单
助手: 好的，让我来查询工单系统。我已经设置好了 dw_onedba 数据库，现在使用 query_database 工具来查找表。

[长期记忆 — 来自之前的对话]
- 用户经常查询工单系统的 order_record 表和告警系统的 db_alert_history 表
- 用户负责 DBA 效能统计工作，经常使用 effect_dba_domain_cost_v2 表
- 用户的业务域包含交易平台和算法平台

[操作记忆 — 查询偏好]
- dw_onedba.order_record（查询 15 次）
- dw_onedba.db_alert_history（查询 8 次）
- dw_onedba.effect_dba_domain_cost_v2（查询 5 次）

[SQL 参考知识库 — 以下是你熟悉的数据库中已验证的 SQL 知识，包含真实的表名、字段名和常见取值，可以直接使用]
- order_record 表包含工单 ID、提交人名称(committer_name)、工单类型(order_type)、状态描述(status_desc)、创建时间(create_time)等字段
- order_type 常见取值: dataChange(数据变更), permission(权限申请), createInstance(创建实例), dataExport(数据导出)
- db_alert_history 表包含告警 ID、实例 ID(db_instance_id)、告警级别(level)、指标名称(metric_name)、告警时间(alert_time)等字段
- level 常见取值: critical, warn, ok

[SQL 历史记忆 — 相关查询]
以下是你或同事在此数据库上成功执行过的类似查询，可作为参考：

1. **问题**: 工单系统：查询 order_type='dataExport' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间升序。
   **SQL**: SELECT id, committer_name, status_desc, create_time FROM order_record WHERE order_type = 'dataExport' ORDER BY create_time ASC
   **结果**: 50 行，列: [id, committer_name, status_desc, create_time]
2. **问题**: 工单系统：统计每种工单类型的数量，按数量升序排列。
   **SQL**: SELECT order_type, COUNT(*) AS order_count FROM order_record GROUP BY order_type ORDER BY order_count ASC
   **结果**: 20 行，列: [order_type, order_count]

用户问题: 工单系统：查询 order_type='dataChange' 的工单，返回工单ID、提交人、状态和创建时间，按创建时间降序。"""

MESSAGES = [
    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    {"role": "user", "content": CONTEXT},
]

# ── 转换为 OpenAI tool format ──
def _to_openai_tool(schema: dict) -> dict:
    """将内部 tool schema 转为 OpenAI function calling 格式"""
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema.get("description", ""),
            "parameters": schema.get("input_schema", {"type": "object", "properties": {}}),
        },
    }

OPENAI_TOOLS = [_to_openai_tool(s) for s in TOOLS]


async def _single_llm_call(client: AsyncOpenAI, label: str, stream: bool) -> dict:
    """单次 LLM 调用，返回 TTFB + 总延迟"""
    t0 = time.monotonic()
    ttfb_ms = None
    total_ms = None
    error = None
    token_info = {}

    try:
        if stream:
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=MESSAGES,
                tools=OPENAI_TOOLS,
                temperature=0.1,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in resp:
                if ttfb_ms is None and chunk.choices:
                    ttfb_ms = (time.monotonic() - t0) * 1000
                if hasattr(chunk, "usage") and chunk.usage:
                    token_info = {
                        "input": chunk.usage.prompt_tokens,
                        "output": chunk.usage.completion_tokens,
                    }
        else:
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=MESSAGES,
                tools=OPENAI_TOOLS,
                temperature=0.1,
            )
            total_ms = (time.monotonic() - t0) * 1000
            if resp.usage:
                token_info = {
                    "input": resp.usage.prompt_tokens,
                    "output": resp.usage.completion_tokens,
                }

        total_ms = (time.monotonic() - t0) * 1000

    except Exception as e:
        total_ms = (time.monotonic() - t0) * 1000
        error = str(e)[:200]

    return {
        "ttfb_ms": round(ttfb_ms, 2) if ttfb_ms else None,
        "total_ms": round(total_ms, 2) if total_ms else None,
        "error": error,
        "input_tokens": token_info.get("input"),
        "output_tokens": token_info.get("output"),
    }


async def _run_concurrent(client: AsyncOpenAI, concurrency: int, repeat: int, stream: bool) -> list[dict]:
    """以指定并发度重复调用"""
    all_results = []
    for batch in range(repeat):
        tasks = [_single_llm_call(client, f"c{concurrency}_b{batch}", stream) for _ in range(concurrency)]
        batch_results = await asyncio.gather(*tasks)
        all_results.extend(batch_results)
    return all_results


def _stats(results: list[dict]) -> dict:
    """计算统计指标"""
    ttfb_values = [r["ttfb_ms"] for r in results if r["ttfb_ms"] is not None]
    total_values = [r["total_ms"] for r in results if r["total_ms"] is not None]
    errors = [r for r in results if r["error"] is not None]
    input_tokens = [r["input_tokens"] for r in results if r["input_tokens"] is not None]

    def _p(latencies: list[float]) -> dict:
        if not latencies:
            return {"count": 0}
        l = sorted(latencies)
        n = len(l)
        return {
            "count": n,
            "avg": round(sum(l) / n, 2),
            "p50": round(l[n // 2], 2),
            "p95": round(l[int(n * 0.95)], 2),
            "p99": round(l[int(n * 0.99)], 2) if n > 1 else round(l[0], 2),
            "min": round(l[0], 2),
            "max": round(l[-1], 2),
        }

    avg_input = round(sum(input_tokens) / len(input_tokens), 0) if input_tokens else None

    return {
        "total_calls": len(results),
        "error_count": len(errors),
        "avg_input_tokens": avg_input,
        "ttfb": _p(ttfb_values),
        "total": _p(total_values),
    }


async def main():
    parser = argparse.ArgumentParser(description="LLM API 并发压测（真实 Agent prompt）")
    parser.add_argument("-c", "--concurrency", type=int, nargs="+", default=[1, 2, 4, 8],
                        help="并发度列表（默认 1 2 4 8）")
    parser.add_argument("-r", "--repeat", type=int, default=2,
                        help="每并发度批次数（默认 2）")
    parser.add_argument("--non-stream", action="store_true",
                        help="非流式模式（默认流式）")
    args = parser.parse_args()

    stream = not args.non_stream
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    token_count = sum(len(TOOLS) for _ in [])  # placeholder
    total_calls = sum(c * args.repeat for c in args.concurrency)

    print(f"LLM API 并发压测（真实 Agent prompt）")
    print(f"URL: {settings.llm_base_url}")
    print(f"Model: {settings.llm_model}")
    print(f"Tool 数量: {len(TOOLS)}")
    print(f"Stream: {stream}")
    print(f"并发度: {args.concurrency}")
    print(f"每并发度批次数: {args.repeat}")
    print(f"总调用数: {total_calls}")
    print(f"系统提示词: {len(AGENT_SYSTEM_PROMPT)} 字符")
    print(f"用户输入（含上下文）: {len(CONTEXT)} 字符")
    print()

    header = f"{'并发':>4} | {'调用':>4} | {'错误':>4} | {'输入Token':>9} | {'TTFB Avg':>9} | {'TTFB P50':>9} | {'TTFB P95':>9} | {'Total Avg':>9} | {'Total P50':>9} | {'Total P95':>9}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for conc in args.concurrency:
        results = await _run_concurrent(client, conc, args.repeat, stream)
        stats = _stats(results)
        t = stats["ttfb"]
        total = stats["total"]
        itok = f"{stats['avg_input_tokens']:.0f}" if stats.get("avg_input_tokens") else "N/A"
        print(
            f"{conc:>4} | {stats['total_calls']:>4} | {stats['error_count']:>4} | {itok:>9} | "
            f"{t['avg']:>8.1f}ms | {t['p50']:>8.1f}ms | {t['p95']:>8.1f}ms | "
            f"{total['avg']:>8.1f}ms | {total['p50']:>8.1f}ms | {total['p95']:>8.1f}ms"
        )

    print(sep)
    print()
    print("与上一轮轻量压测对比:")
    print("  轻量版: 1-2K token prompt, TTFB ~1.4s")
    print("  真实版: 完整系统提示词 + 8段上下文 + 6个工具定义, TTFB ?")
    print("  差异 = 模型处理大 prompt 的额外开销")


if __name__ == "__main__":
    asyncio.run(main())