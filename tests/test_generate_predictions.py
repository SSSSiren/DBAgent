from scripts.generate_predictions import (
    build_message,
    extract_sql_from_response,
    extract_sql_from_text,
    output_contract_for_case,
    semantic_rules_for_domain,
)
from app.benchmark.mysql_sandbox import load_cases


def test_extract_sql_from_tool_call_response():
    payload = {
        "tool_calls": [
            {
                "tool": "nl2sql_query",
                "nl2sql": {"sql": "SELECT id FROM users;"},
            }
        ],
        "reply": "",
    }

    sql, source = extract_sql_from_response(payload)

    assert sql == "SELECT id FROM users;"
    assert source == "tool_calls.nl2sql.sql"


def test_extract_sql_from_fenced_reply():
    sql = extract_sql_from_text("```sql\nSELECT id FROM users;\n```")

    assert sql == "SELECT id FROM users;"


def test_extract_sql_from_plain_reply():
    sql = extract_sql_from_text("SELECT id FROM users ORDER BY id; explanation should be ignored")

    assert sql == "SELECT id FROM users ORDER BY id;"


def test_build_message_contains_schema_and_case_context():
    case = load_cases("benchmarks/mysql_sandbox/cases.jsonl")[0]
    message = build_message(case, "CREATE TABLE users (id BIGINT);")

    assert "CREATE TABLE users" in message
    assert case.id in message
    assert case.user_question in message
    assert "只返回 SQL" in message


def test_build_message_injects_mysql_sandbox_semantics_by_default():
    case = load_cases("benchmarks/mysql_sandbox/cases.jsonl")[0]
    message = build_message(case, "CREATE TABLE orders (order_status VARCHAR(20), total_amount DECIMAL(10,2));")

    assert "业务语义层规则" in message
    assert "有效订单" in message
    assert "order_status IN ('paid', 'completed')" in message
    assert "支付成功" in message
    assert "payment_status = 'success'" in message
    assert "退款成功" in message
    assert "refund_status = 'approved'" in message
    assert "在售商品" in message
    assert "products.status = 'active'" in message
    assert "GMV" in message
    assert "SUM(orders.total_amount)" in message


def test_semantic_rules_can_be_disabled_for_other_domains():
    assert semantic_rules_for_domain("") == "无"


def test_build_message_injects_output_contract():
    cases = {case.id: case for case in load_cases("benchmarks/mysql_sandbox/cases.jsonl")}

    single_message = build_message(cases["ecom_single_002"], "CREATE TABLE products (status VARCHAR(20));")
    assert "输出形状要求" in single_message
    assert "只输出：id, product_name, stock_quantity" in single_message
    assert "不要输出 status" in single_message

    event_message = build_message(cases["ecom_event_002"], "CREATE TABLE user_events (event_name VARCHAR(64));")
    assert "只输出：user_count" in event_message
    assert "HAVING COUNT(DISTINCT event_name) = 2" in event_message

    join_message = build_message(cases["ecom_join_002"], "CREATE TABLE products (id BIGINT);")
    assert "ORDER BY sold_quantity DESC, product_id ASC" in join_message

    payment_message = build_message(cases["ecom_time_002"], "CREATE TABLE payments (paid_amount DECIMAL(10,2));")
    assert "ORDER BY paid_amount DESC" in payment_message

    window_message = build_message(cases["ecom_window_001"], "CREATE TABLE products (status VARCHAR(20));")
    assert "不要添加 p.status/status 在售过滤" in window_message
    assert "p.id ASC" in window_message
    assert "ORDER BY category_name" in window_message


def test_output_contract_falls_back_for_unknown_case():
    assert "只输出必要列" in output_contract_for_case("unknown")


def test_extract_sql_from_chinese_prefixed_reply():
    sql = extract_sql_from_text("生成的 SQL 如下：\nSELECT order_status, COUNT(id) FROM orders GROUP BY order_status;")

    assert sql == "SELECT order_status, COUNT(id) FROM orders GROUP BY order_status;"
