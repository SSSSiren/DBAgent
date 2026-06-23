import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.benchmark.mysql_sandbox import BenchmarkCase, load_cases
from app.agent.llm import get_llm, is_llm_configured
from app.nl2sql.semantics import SANDBOX_SEMANTIC_RULES, render_semantic_rules_for_prompt


DEFAULT_SYSTEM_INSTRUCTION = """你是 MySQL SQL 编写助手。请只基于给定 MySQL schema、业务语义层规则和用户问题生成一条只读 SQL。
要求：
- 只返回 SQL，不要返回解释。
- 只能使用 schema 中存在的表和字段。
- 只能生成 SELECT 或 WITH 查询。
- 不要生成 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE。
- 不要使用 SELECT *。
- 使用 MySQL 8 语法。
- 不要翻译、意译或本地化枚举值；业务词必须使用业务语义层规则中的真实 SQL 片段。
- SELECT 输出列必须严格贴合“输出形状要求”；不要把仅用于 WHERE/JOIN/GROUP BY 的过滤字段额外返回。
- 聚合列、日期列和计算列必须使用“输出形状要求”中的别名。
"""


OUTPUT_CONTRACTS = {
    "ecom_single_001": "只输出：id, user_name, city, registered_at。",
    "ecom_single_002": "只输出：id, product_name, stock_quantity。不要输出 status。",
    "ecom_agg_001": "只输出：order_status, order_count。COUNT(id) AS order_count。",
    "ecom_agg_002": "只输出：pay_date, order_count, gmv。DATE(paid_at) AS pay_date，COUNT(id) AS order_count，SUM(total_amount) AS gmv。",
    "ecom_join_001": "只输出：user_id, user_name, order_count, total_spent。u.id AS user_id，COUNT(o.id) AS order_count，SUM(o.total_amount) AS total_spent。",
    "ecom_join_002": "只输出：product_id, product_name, sold_quantity, sales_amount。p.id AS product_id，SUM(oi.quantity) AS sold_quantity，SUM(oi.quantity * oi.unit_price) AS sales_amount。必须 ORDER BY sold_quantity DESC, product_id ASC。",
    "ecom_topn_001": "只输出：product_name, sales_amount。SUM(oi.quantity * oi.unit_price) AS sales_amount。",
    "ecom_time_001": "只输出：register_date, new_users。DATE(registered_at) AS register_date，COUNT(id) AS new_users。",
    "ecom_time_002": "只输出：payment_method, paid_amount。SUM(paid_amount) AS paid_amount。必须 ORDER BY paid_amount DESC。",
    "ecom_subquery_001": "只输出：user_id, user_name, valid_order_count。u.id AS user_id，COUNT(o.id) AS valid_order_count。",
    "ecom_window_001": "只输出：category_name, product_name, sales_amount。窗口排名字段 rn 只能用于过滤，不要输出。不要添加 p.status/status 在售过滤。ROW_NUMBER 必须使用 PARTITION BY c.id ORDER BY SUM(oi.quantity * oi.unit_price) DESC, p.id ASC；最终结果必须 ORDER BY category_name。",
    "ecom_left_join_001": "只输出：coupon_id, coupon_code, used_order_count, order_amount。c.id AS coupon_id，COUNT(o.id) AS used_order_count，COALESCE(SUM(o.total_amount), 0) AS order_amount。",
    "ecom_null_001": "只输出：id, user_id, order_status, created_at。paid_at 只能用于 IS NULL 过滤，不要输出。",
    "ecom_refund_001": "只输出：order_id, refund_amount, total_amount, refund_created_at。o.id AS order_id，r.created_at AS refund_created_at，不要输出 refund_status。",
    "ecom_event_001": "只输出：event_name, event_count。COUNT(id) AS event_count。",
    "ecom_event_002": "只输出：user_count。必须使用 GROUP BY user_id 和 HAVING COUNT(DISTINCT event_name) = 2 来表达同时发生两类事件。",
    "ecom_ratio_001": "只输出：channel, registered_users, valid_order_users, conversion_rate。COUNT(DISTINCT u.id) AS registered_users，有效下单用户数 AS valid_order_users，二者比值 AS conversion_rate。",
    "ecom_rewrite_001": "只输出：pay_month, gmv。DATE_FORMAT(paid_at, '%Y-%m') AS pay_month，SUM(total_amount) AS gmv。",
    "ecom_repair_001": "只输出：user_name, order_count。COUNT(o.id) AS order_count。",
    "ecom_safety_001": "用户请求是删除，但安全评测要求改写为只读查询；只输出：id, order_status。",
}


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def semantic_rules_for_domain(domain: str) -> str:
    if domain == "mysql_sandbox":
        return render_semantic_rules_for_prompt(SANDBOX_SEMANTIC_RULES)
    return "无"


def output_contract_for_case(case_id: str) -> str:
    return OUTPUT_CONTRACTS.get(case_id, "按用户问题只输出必要列；不要输出过滤字段、Join 键或中间计算字段。")


def build_message(
    case: BenchmarkCase,
    schema_text: str,
    instruction: str = DEFAULT_SYSTEM_INSTRUCTION,
    semantic_domain: str = "mysql_sandbox",
) -> str:
    semantic_rules = semantic_rules_for_domain(semantic_domain)
    output_contract = output_contract_for_case(case.id)
    return f"""{instruction}

MySQL schema:
```sql
{schema_text}
```

业务语义层规则：
{semantic_rules}

输出形状要求：
{output_contract}

评测样本：
- id: {case.id}
- difficulty: {case.difficulty}
- task_type: {case.task_type}
- question: {case.user_question}
- expected_tables: {", ".join(case.expected_tables)}
- expected_columns: {", ".join(case.expected_columns)}
- notes: {case.notes or "无"}

请输出 SQL：
"""


def extract_sql_from_text(text: str) -> str:
    if not text:
        return ""
    fenced = re.search(r"```(?:sql|mysql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return cleanup_sql(fenced.group(1))

    select_match = re.search(r"\b(WITH|SELECT)\b.*", text, re.IGNORECASE | re.DOTALL)
    if select_match:
        return cleanup_sql(select_match.group(0))
    return ""


def cleanup_sql(sql: str) -> str:
    sql = sql.strip()
    sql = re.sub(r"^\s*(SQL|sql)\s*:\s*", "", sql)
    sql = sql.strip().strip("`").strip()
    if ";" in sql:
        sql = sql[: sql.find(";") + 1]
    return sql


def extract_sql_from_response(payload: dict[str, Any]) -> tuple[str, str]:
    for call in payload.get("tool_calls") or []:
        nl2sql = call.get("nl2sql") or {}
        sql = cleanup_sql(str(nl2sql.get("sql") or ""))
        if sql:
            return sql, "tool_calls.nl2sql.sql"

    reply = str(payload.get("reply") or "")
    sql = extract_sql_from_text(reply)
    if sql:
        return sql, "reply"
    return "", "not_found"


def call_dbagent(base_url: str, session_id: str, message: str, timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/chat/sync"
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json={"session_id": session_id, "message": message})
        response.raise_for_status()
        return response.json()


async def call_direct_llm(message: str) -> str:
    if not is_llm_configured():
        raise RuntimeError("DEEPSEEK_API_KEY is not configured; direct LLM fallback is unavailable")
    response = await get_llm().ainvoke(message)
    return str(response.content or "")


def iter_selected_cases(cases: list[BenchmarkCase], limit: int, case_id: str) -> list[BenchmarkCase]:
    selected = cases
    if case_id:
        selected = [case for case in selected if case.id == case_id]
    if limit > 0:
        selected = selected[:limit]
    return selected


def write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate benchmark predictions by calling DBAgent /api/chat/sync.")
    parser.add_argument("--cases", default="benchmarks/mysql_sandbox/cases.jsonl")
    parser.add_argument("--schema", default="benchmarks/mysql_sandbox/schema.sql")
    parser.add_argument("--output", default="predictions.jsonl")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--session-prefix", default="mysql-benchmark")
    parser.add_argument(
        "--semantic-domain",
        default="mysql_sandbox",
        help="Semantic domain used to inject benchmark business rules. Use empty string to disable.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-id", default="")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between requests.")
    parser.add_argument(
        "--no-fallback-direct-llm",
        action="store_true",
        help="Disable direct LLM fallback when DBAgent HTTP response contains no SQL.",
    )
    args = parser.parse_args()

    cases = iter_selected_cases(load_cases(args.cases), args.limit, args.case_id)
    schema_text = read_text(args.schema)
    rows: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        message = build_message(case, schema_text, semantic_domain=args.semantic_domain)
        session_id = f"{args.session_prefix}-{case.id}"
        row: dict[str, Any] = {"id": case.id, "sql": "", "source": "", "error": ""}
        try:
            payload = call_dbagent(args.base_url, session_id, message, args.timeout)
            sql, source = extract_sql_from_response(payload)
            row.update({"sql": sql, "source": source})
            if not sql and not args.no_fallback_direct_llm:
                direct_reply = asyncio.run(call_direct_llm(message))
                sql = extract_sql_from_text(direct_reply)
                row.update({"sql": sql, "source": "direct_llm"})
            if not row["sql"]:
                row["error"] = "No SQL found in DBAgent response or direct LLM fallback"
        except Exception as exc:
            row["error"] = str(exc)
        rows.append(row)
        print(f"[{index}/{len(cases)}] {case.id}: {'ok' if row['sql'] else 'failed'}", flush=True)
        if args.sleep > 0 and index < len(cases):
            time.sleep(args.sleep)

    write_jsonl(args.output, rows)
    failed = [row["id"] for row in rows if not row.get("sql")]
    print(json.dumps({"output": args.output, "total": len(rows), "failed": failed}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
