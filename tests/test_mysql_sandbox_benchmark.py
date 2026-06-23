from app.benchmark.mysql_sandbox import (
    BenchmarkCase,
    ResultCheck,
    classify_failure_categories,
    evaluate_cases,
    is_readonly_sql,
    load_cases,
    result_hash,
    static_score,
)


def test_load_mysql_sandbox_cases():
    cases = load_cases("benchmarks/mysql_sandbox/cases.jsonl")

    assert len(cases) >= 20
    assert cases[0].id == "ecom_single_001"


def test_static_score_accepts_reference_sql():
    case = load_cases("benchmarks/mysql_sandbox/cases.jsonl")[0]

    static_passed, safety_passed, schema_passed, errors = static_score(case, case.reference_sql)

    assert static_passed
    assert safety_passed
    assert schema_passed
    assert errors == []


def test_static_score_rejects_write_sql():
    case = load_cases("benchmarks/mysql_sandbox/cases.jsonl")[0]

    static_passed, safety_passed, schema_passed, errors = static_score(case, "DELETE FROM users WHERE status = 'inactive'")

    assert not static_passed
    assert not safety_passed
    assert not schema_passed
    assert "SQL must be a single read-only SELECT/WITH statement" in errors


def test_is_readonly_sql_rejects_multi_statement():
    assert not is_readonly_sql("SELECT * FROM users; DROP TABLE users")


def test_result_hash_is_order_insensitive_by_default():
    left = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    right = [{"id": 2, "name": "b"}, {"id": 1, "name": "a"}]

    assert result_hash(left) == result_hash(right)
    assert result_hash(left, order_sensitive=True) != result_hash(right, order_sensitive=True)


def test_evaluate_cases_with_reference_static_only():
    cases = load_cases("benchmarks/mysql_sandbox/cases.jsonl")[:3]
    report = evaluate_cases(cases, {}, use_reference=True)
    summary = report.summary()

    assert summary["total"] == 3
    assert summary["static_pass_rate"] == 1.0
    assert summary["safety_pass_rate"] == 1.0
    assert summary["schema_pass_rate"] == 1.0
    assert summary["execution_pass_rate"] is None
    assert summary["result_accuracy"] is None
    assert summary["failure_category_counts"] == {}


def test_classify_enum_value_error_for_translated_value():
    case = BenchmarkCase(
        id="enum",
        difficulty="medium",
        task_type="single_table_filter",
        user_question="查询库存小于 20 的在售商品",
        expected_tables=["products"],
        expected_columns=["status"],
        reference_sql="SELECT id FROM products WHERE status = 'active'",
    )

    categories = classify_failure_categories(
        case,
        "SELECT id FROM products WHERE status = '在售'",
        case.reference_sql,
        [{"id": 1}],
        [{"id": 2}],
    )

    assert "enum_value_error" in categories
    assert "business_rule_error" in categories


def test_classify_business_rule_error_when_valid_order_filter_missing():
    case = BenchmarkCase(
        id="business",
        difficulty="medium",
        task_type="aggregation",
        user_question="统计有效订单 GMV",
        expected_tables=["orders"],
        expected_columns=["order_status", "total_amount"],
        reference_sql="SELECT SUM(total_amount) AS gmv FROM orders WHERE order_status IN ('paid', 'completed')",
    )

    categories = classify_failure_categories(
        case,
        "SELECT SUM(total_amount) AS gmv FROM orders",
        case.reference_sql,
        [{"gmv": "100.00"}],
        [{"gmv": "80.00"}],
    )

    assert "business_rule_error" in categories


def test_classify_order_mismatch_when_only_row_order_differs():
    case = BenchmarkCase(
        id="order",
        difficulty="easy",
        task_type="aggregation",
        user_question="统计每个订单状态的订单数。",
        expected_tables=["orders"],
        expected_columns=["order_status"],
        reference_sql="SELECT order_status, COUNT(id) AS order_count FROM orders GROUP BY order_status ORDER BY order_status",
        result_check=ResultCheck(order_sensitive=True),
    )

    categories = classify_failure_categories(
        case,
        "SELECT order_status, COUNT(id) AS order_count FROM orders GROUP BY order_status",
        case.reference_sql,
        [{"order_status": "paid", "order_count": 1}, {"order_status": "completed", "order_count": 2}],
        [{"order_status": "completed", "order_count": 2}, {"order_status": "paid", "order_count": 1}],
    )

    assert "order_mismatch" in categories


def test_classify_output_shape_mismatch_when_columns_differ():
    case = BenchmarkCase(
        id="shape",
        difficulty="easy",
        task_type="single_table_filter",
        user_question="返回用户ID、用户名",
        expected_tables=["users"],
        expected_columns=["id", "user_name"],
        reference_sql="SELECT id, user_name FROM users",
    )

    categories = classify_failure_categories(
        case,
        "SELECT id, user_name, city FROM users",
        case.reference_sql,
        [{"id": 1, "user_name": "a", "city": "sh"}],
        [{"id": 1, "user_name": "a"}],
    )

    assert "output_shape_mismatch" in categories


def test_classify_mysql_dialect_error_from_execution_error():
    case = BenchmarkCase(
        id="dialect",
        difficulty="hard",
        task_type="time_window",
        user_question="按月统计 GMV",
        expected_tables=["orders"],
        expected_columns=["paid_at"],
        reference_sql="SELECT DATE_FORMAT(paid_at, '%Y-%m') FROM orders",
    )

    categories = classify_failure_categories(
        case,
        "SELECT DATE_TRUNC('month', paid_at) FROM orders",
        case.reference_sql,
        execution_error="You have an error in your SQL syntax",
    )

    assert "execution_error" in categories
    assert "mysql_dialect_error" in categories
