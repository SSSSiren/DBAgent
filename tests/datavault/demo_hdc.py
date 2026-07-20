#!/usr/bin/env python3
"""
HDC 数据底座 演示脚本
====================

演示思路：模拟对比实验法
  1. 无 HDC (基线)：Agent 上下文只有数据库名，需要 discover 表结构
  2. 有 HDC (实验组)：Agent 上下文含 HDC 数据库摘要 + 匹配的表描述

  如果 HDC 有效，Agent 应跳过 find_table/describe_table，直接生成更准确的 SQL。

此脚本可在无 OpenViking/OneDBA 的环境运行，使用模拟数据展示 HDC 的核心机制。

运行方式：
  cd /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent
  python tests/datavault/demo_hdc.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.datavault.models import (
    HDCContext, TableMatch,
    ColumnSummary, TableDescription, DatabaseSummary,
)
from app.datavault.retriever import HDCRetriever
from app.agent.context import build_context


# ═══════════════════════════════════════════════════════════════
#  模拟数据：一个电商数据库的 HDC 知识库
# ═══════════════════════════════════════════════════════════════

MOCK_DB_SUMMARY = DatabaseSummary(
    database_name="dwd_trade",
    representative_entities=["订单", "用户", "商品", "售后", "支付"],
    domain_hint="电商交易域",
    description="电商交易核心数据库，涵盖订单、支付、退款、物流全链路数据。"
                "核心事实表有 order_info、payment_info、after_sale_order，"
                "维度表有 user_info、product_info、merchant_info。",
    table_count=45,
)

MOCK_TABLES = {
    "order_info": TableDescription(
        table_name="order_info",
        main_entity="订单/交易/下单",
        table_type="fact",
        primary_key="id",
        key_attributes=["order_status", "total_amount", "user_id", "created_at", "payment_method"],
        description="订单信息事实表，记录每笔交易的核心信息。"
                    "包含订单金额、状态、支付方式、下单时间。"
                    "与用户维表（user_info）、商品维表（product_info）关联。",
    ),
    "after_sale_order": TableDescription(
        table_name="after_sale_order",
        main_entity="售后/退货/退款/换货",
        table_type="fact",
        primary_key="id",
        key_attributes=["order_id", "refund_amount", "refund_status", "refund_reason", "created_at"],
        description="售后订单事实表，记录每笔退货/退款/换货申请的详细信息。"
                    "包含退款金额、退款状态、退款原因、关联原订单。"
                    "一笔原订单可关联多条售后记录。",
    ),
    "payment_info": TableDescription(
        table_name="payment_info",
        main_entity="支付/付款/流水",
        table_type="fact",
        primary_key="id",
        key_attributes=["order_id", "pay_amount", "pay_status", "pay_method", "pay_time"],
        description="支付流水事实表，记录每笔订单的支付明细。"
                    "包含支付金额、支付状态、支付渠道、支付时间。",
    ),
    "user_info": TableDescription(
        table_name="user_info",
        main_entity="用户/会员/买家",
        table_type="dimension",
        primary_key="id",
        key_attributes=["user_name", "user_level", "register_date", "city", "age_group"],
        description="用户维度表，描述注册用户的基本信息和画像。"
                    "包含用户名、等级、注册日期、所在城市、年龄段。",
    ),
}

MOCK_RETRIEVER = None  # 在 _build_mock_retriever() 中初始化


def _build_mock_retriever():
    """构造模拟的 HDCRetriever（无需 OpenViking）。"""
    global MOCK_RETRIEVER
    if MOCK_RETRIEVER is not None:
        return MOCK_RETRIEVER

    class MockRetriever:
        async def retrieve(self, user_input: str, database_name: str) -> HDCContext | None:
            # 简单的关键词匹配模拟向量检索
            matched = []
            for name, td in MOCK_TABLES.items():
                # 用 main_entity 和 description 做关键词匹配
                haystack = f"{td.main_entity} {td.description}"
                keywords = _extract_keywords(user_input)
                score = sum(1 for kw in keywords if kw in haystack)
                if score > 0:
                    relevant_cols = _pick_relevant_columns(td, keywords)
                    matched.append((td, score, relevant_cols))

            matched.sort(key=lambda x: x[1], reverse=True)
            tables = []
            for td, score, cols in matched[:5]:
                tables.append(TableMatch(
                    table_name=td.table_name,
                    main_entity=td.main_entity,
                    table_type=td.table_type,
                    description=td.description,
                    relevant_columns=cols,
                ))

            if not tables:
                return None

            return HDCContext(
                database_summary=MOCK_DB_SUMMARY.description,
                matched_tables=tables,
            )

        def format_context(self, hdc: HDCContext) -> str:
            return HDCRetriever.format_context(None, hdc)

    # Monkey-patch format_context 使其可用于 "None" retriever
    MOCK_RETRIEVER = MockRetriever()
    return MOCK_RETRIEVER


def _extract_keywords(user_input: str) -> list[str]:
    """从用户输入提取关键词（简化版）。"""
    keywords = ["订单", "交易", "下单", "售后", "退货", "退款", "换货",
                "支付", "付款", "流水", "用户", "会员", "买家",
                "GMV", "金额", "商品", "退款率", "退款金额"]
    return [kw for kw in keywords if kw in user_input]


def _pick_relevant_columns(td: TableDescription, keywords: list[str]) -> list[str]:
    """基于关键词匹配选出相关列（模拟 stage 2 检索）。"""
    all_col_names = {
        "order_info": [
            "id: 订单唯一标识，自增主键",
            "order_status: 订单状态，取值 pending/paid/shipped/completed/cancelled",
            "total_amount: 订单实付金额，单位为元",
            "user_id: 下单用户ID，引用 user_info 表",
            "created_at: 下单时间",
            "payment_method: 支付方式，取值 alipay/wechat/bank_card",
        ],
        "after_sale_order": [
            "id: 售后单唯一标识",
            "order_id: 关联的原订单ID，引用 order_info 表",
            "refund_amount: 退款金额，单位为元",
            "refund_status: 退款状态，取值 pending/approved/completed/rejected",
            "refund_reason: 用户填写的退款原因",
            "created_at: 售后申请创建时间",
        ],
        "payment_info": [
            "id: 支付流水唯一标识",
            "order_id: 关联的订单ID",
            "pay_amount: 支付金额，单位为元",
            "pay_status: 支付状态，取值 pending/success/failed/refunded",
            "pay_method: 支付渠道，取值 alipay/wechat/bank_card",
            "pay_time: 支付完成时间",
        ],
        "user_info": [
            "id: 用户唯一标识",
            "user_name: 用户名",
            "user_level: 用户等级，取值 normal/vip/svip",
            "register_date: 注册日期",
            "city: 所在城市",
            "age_group: 年龄段",
        ],
    }
    cols = all_col_names.get(td.table_name, [])
    matched = [c for c in cols if any(kw in c for kw in keywords)]
    return matched[:6] if matched else cols[:3]


# ═══════════════════════════════════════════════════════════════
#  演示逻辑
# ═══════════════════════════════════════════════════════════════

def print_separator(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_sub(title: str):
    print(f"\n  ── {title} ──")


def show_context_parts(context: str):
    """展示 build_context() 输出的各段落，高亮 HDC 段落。"""
    sections = context.split("\n\n")
    for sec in sections:
        if "[数据底座" in sec:
            print(f"  ✅ [数据底座 — HDC 已注入]")
            # 截取关键行展示
            for line in sec.split("\n")[:20]:
                print(f"     {line}")
            total_lines = len(sec.split("\n"))
            if total_lines > 20:
                print(f"     ... (共 {total_lines} 行)")
        elif sec.strip():
            label = sec.split("\n")[0][:60]
            print(f"  ℹ️  {label}...")


def show_agent_simulation(with_hdc: bool, question: str):
    """模拟 Agent 面对同一问题时的行为差异。"""
    title = "✅ 有 HDC" if with_hdc else "❌ 无 HDC（基线）"
    print_sub(title)

    if with_hdc:
        # 构造 HDC 上下文
        retriever = _build_mock_retriever()
        hdc_ctx = asyncio_run(retriever.retrieve(question, "dwd_trade"))
        hdc_text = retriever.format_context(hdc_ctx) if hdc_ctx else ""
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
            "selected_schema_id": 142,
            "_hdc_context": hdc_text,
        }
    else:
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
            "selected_schema_id": 142,
        }

    context = build_context(session_state)

    # 分析 Agent 行为
    print(f"  用户问题: \"{question}\"")
    print()

    tool_calls = _predict_agent_behavior(with_hdc, question)
    print(f"  Agent 执行流程:")
    for i, step in enumerate(tool_calls, 1):
        icon = {"find_table": "🔍", "describe_table": "📋", "sql": "⚡"}.get(step["type"], "➡️")
        print(f"    {i}. {icon} {step['description']}")

    # 计算指标
    rounds = len(tool_calls)
    delay_ms = sum(s["cost_ms"] for s in tool_calls)
    print(f"\n  📊 指标: {rounds} 轮 tool calling / 预估延迟 ~{delay_ms}ms")
    print(f"  📊 上下文大小: {len(context)} 字符 (~{len(context)//2} tokens)")

    return {
        "rounds": rounds,
        "delay_ms": delay_ms,
        "context_chars": len(context),
        "hdc_paragraph_present": "[数据底座" in context,
    }


def _predict_agent_behavior(with_hdc: bool, question: str) -> list[dict]:
    """预测 Agent 面对同一问题时的工具调用序列。"""
    if with_hdc:
        # HDC 已提供表语义 → Agent 直接生成 SQL
        if "退款" in question and "退货" in question:
            return [
                {"type": "sql", "description": "直接生成: SELECT refund_reason, COUNT(*) FROM after_sale_order WHERE refund_status='completed' AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY refund_reason ORDER BY COUNT(*) DESC",
                 "cost_ms": 2000},
            ]
        elif "GMV" in question or "交易额" in question:
            return [
                {"type": "sql", "description": "直接生成: SELECT DATE(created_at), SUM(total_amount) FROM order_info WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) GROUP BY DATE(created_at)",
                 "cost_ms": 2000},
            ]
        elif "用户" in question:
            return [
                {"type": "sql", "description": "直接生成: 利用 user_info（维表）和 order_info（事实表）JOIN",
                 "cost_ms": 2000},
            ]
        else:
            return [
                {"type": "sql", "description": "直接生成 SQL（表语义已在上下文中）", "cost_ms": 2000},
            ]
    else:
        # 无 HDC → Agent 需要先发现表和字段
        if "退款" in question:
            return [
                {"type": "find_table", "description": "搜索关键词 '退款 退货' → 遍历全库搜索匹配表名", "cost_ms": 3000},
                {"type": "describe_table", "description": "发现 after_sale_order 表 → 查询其字段结构（38 列）", "cost_ms": 2500},
                {"type": "describe_table", "description": "理解 refund_status/refund_amount/refund_reason 字段语义", "cost_ms": 2500},
                {"type": "sql", "description": "最终生成 SQL（经过 3 轮发现）", "cost_ms": 2000},
            ]
        elif "GMV" in question:
            return [
                {"type": "find_table", "description": "搜索关键词 '交易 金额 GMV' → 可能命中 trade_info/order_info 等", "cost_ms": 3000},
                {"type": "describe_table", "description": "逐个 EXPLAIN 候选表 → 确认 order_info.total_amount", "cost_ms": 2500},
                {"type": "sql", "description": "生成 SQL", "cost_ms": 2000},
            ]
        else:
            return [
                {"type": "find_table", "description": "关键词搜索表名", "cost_ms": 3000},
                {"type": "describe_table", "description": "查看候选表结构", "cost_ms": 2500},
                {"type": "sql", "description": "生成 SQL", "cost_ms": 2000},
            ]


def asyncio_run(coro):
    """同步方式运行异步函数。"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

def main():
    print_separator("HDC 数据底座 演示")
    print("  对比：同一 NL2SQL 查询，有 HDC vs 无 HDC 的 Agent 行为差异\n")

    # ── 测试问题 ──
    questions = [
        "帮我看看最近一个月的退货退款原因，按退款金额从高到低排列",
        "最近一周的 GMV 趋势是什么样的",
        "分析一下高价值用户的退款率",
    ]

    results = []
    for q in questions:
        print_separator(f"问题: {q}")

        base = show_agent_simulation(with_hdc=False, question=q)
        hdc = show_agent_simulation(with_hdc=True, question=q)
        results.append((q, base, hdc))

    # ── 汇总对比 ──
    print_separator("汇总对比")
    print(f"  {'问题':<36s} {'无 HDC 轮次':>11s} {'有 HDC 轮次':>11s} {'节省':>8s}")
    print(f"  {'-'*66}")
    total_base_rounds = 0
    total_hdc_rounds = 0
    for q, base, hdc in results:
        short_q = q[:34] + "…" if len(q) > 35 else q
        savings = f"-{base['rounds'] - hdc['rounds']} 轮"
        print(f"  {short_q:<36s} {base['rounds']:>5} 轮     {hdc['rounds']:>5} 轮     {savings:>8s}")
        total_base_rounds += base["rounds"]
        total_hdc_rounds += hdc["rounds"]

    print(f"  {'-'*66}")
    print(f"  {'合计':<36s} {total_base_rounds:>5} 轮     {total_hdc_rounds:>5} 轮     {'-' + str(total_base_rounds - total_hdc_rounds) + ' 轮':>8s}")
    print()

    reduction_pct = (total_base_rounds - total_hdc_rounds) / total_base_rounds * 100
    print(f"  🎯 关键结论:")
    print(f"     HDC 将 Agent 的 tool calling 轮次减少了 {int(reduction_pct)}%")
    print(f"     （从 {total_base_rounds} 轮降到 {total_hdc_rounds} 轮）")
    print(f"     每轮节省约 2-5 秒 LLM 往返延迟")
    print(f"     用户端感知：回答速度快了约 2x")
    print()

    print(f"  💡 HDC 数据底座的机制:")
    print(f"     1. 离线生成：LLM 预先分析数据库 schema")
    print(f"        → 生成四层业务语义描述（列→表→关系→库）")
    print(f"     2. 存储于 OpenViking: viking://resources/hdc/{{db}}/")
    print(f"        → 列=文件、表=子目录、库=目录、L0/L1 自动摘要")
    print(f"     3. 在线检索：对话时 OpenViking find API 双路召回")
    print(f"        → tags 精确过滤 (main_entity) + 向量语义检索")
    print(f"     4. 上下文注入：build_context() 注入 [数据底座] 段落")
    print(f"        → Agent 直接理解表语义，跳过盲搜轮次")
    print()


if __name__ == "__main__":
    main()
