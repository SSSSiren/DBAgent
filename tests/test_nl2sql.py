from app.nl2sql.intent import normalize_identifier_hint, parse_nl2sql_intent
from app.nl2sql.resolver import resolve_database_candidate, resolve_table_candidate
from app.nl2sql.schema import parse_describe_result
from app.nl2sql.validator import validate_sql


def test_parse_nl2sql_intent_for_most_frequent_field():
    intent = parse_nl2sql_intent("帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么")

    assert intent.is_query
    assert intent.database_keyword == "dw-onedba-t1"
    assert intent.table_hint == "approval_template_node"
    assert intent.field_hints[0] == "nodeid"
    assert intent.operation == "most_frequent"
    assert intent.limit == 1


def test_parse_nl2sql_intent_for_top_two_most_frequent_field():
    intent = parse_nl2sql_intent("帮我查查dw-onedba-t1数据库中approval template node表中出现最多的两个nodeid是什么")

    assert intent.operation == "most_frequent"
    assert intent.limit == 2


def test_parse_nl2sql_intent_for_table_counts_by_prefix():
    intent = parse_nl2sql_intent("帮我查查dw-onedba-t1数据库中approval 各个表中分别有多少条数据")

    assert intent.is_query
    assert intent.database_keyword == "dw-onedba-t1"
    assert intent.operation == "table_counts"
    assert intent.table_prefix == "approval"


def test_parse_nl2sql_intent_for_field_count():
    intent = parse_nl2sql_intent("dw onedba t1数据库 找找alert history表中有多少个字段")

    assert intent.operation == "field_count"
    assert intent.table_hint == "alert_history"


def test_parse_nl2sql_intent_does_not_treat_table_as_database():
    intent = parse_nl2sql_intent("帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行")

    assert intent.database_keyword == ""
    assert intent.table_hint == "db_alert_history"
    assert intent.operation == "ranking_count"
    assert intent.time_days == 30
    assert intent.limit == 20


def test_normalize_identifier_hint_handles_spaces_and_camel_case():
    assert normalize_identifier_hint("approval template node") == "approval_template_node"
    assert normalize_identifier_hint("approvalTemplateNode") == "approval_template_node"


def test_resolve_database_requires_clarification_for_tied_candidates():
    result = resolve_database_candidate(
        [
            {"schemaId": 1, "schemaName": "dw_onedba", "instanceName": "dw-test-t1"},
            {"schemaId": 2, "schemaName": "dw_onedba", "instanceName": "dw-test-t2"},
        ],
        "dw_onedba",
    )

    assert result.needs_clarification
    assert result.value is None
    assert len(result.candidates) == 2


def test_resolve_database_selects_exact_instance_match():
    result = resolve_database_candidate(
        [
            {"schemaId": 1, "schemaName": "dw_onedba", "instanceName": "dw-test-t1"},
            {"schemaId": 2, "schemaName": "dw_onedba", "instanceName": "dw-onedba-t1"},
        ],
        "dw-onedba-t1",
    )

    assert not result.needs_clarification
    assert result.value == 2


def test_resolve_table_normalizes_hint():
    result = resolve_table_candidate(["approval_template_node", "approval_node"], "approval template node")

    assert result.value == "approval_template_node"


def test_resolve_table_by_unique_suffix_match():
    result = resolve_table_candidate(["db_alert_history", "db_alert_metric"], "alert history")

    assert result.value == "db_alert_history"


def test_parse_describe_result_from_onedba_shape():
    raw = {
        "columnNames": [
            {"key": "col_1", "title": "Field"},
            {"key": "col_2", "title": "Type"},
            {"key": "col_3", "title": "Null"},
            {"key": "col_4", "title": "Key"},
            {"key": "col_5", "title": "Default"},
            {"key": "col_6", "title": "Extra"},
        ],
        "columnDatas": [{"col_1": "nodeid", "col_2": "bigint(20)", "col_3": "YES", "col_4": "", "col_5": None, "col_6": ""}],
    }

    columns = parse_describe_result(raw)

    assert columns[0].name == "nodeid"
    assert columns[0].type == "bigint(20)"


def test_validate_sql_appends_limit_and_checks_columns():
    columns = parse_describe_result(
        {
            "columnNames": [{"key": "col_1", "title": "Field"}, {"key": "col_2", "title": "Type"}],
            "columnDatas": [{"col_1": "nodeid", "col_2": "bigint(20)"}],
        }
    )

    result = validate_sql("SELECT nodeid FROM approval_template_node", "approval_template_node", columns)

    assert result.passed
    assert result.sql.endswith("LIMIT 100")
    assert "已自动追加 LIMIT 100" in result.assumptions


def test_validate_sql_rejects_unknown_column():
    columns = parse_describe_result(
        {
            "columnNames": [{"key": "col_1", "title": "Field"}, {"key": "col_2", "title": "Type"}],
            "columnDatas": [{"col_1": "nodeid", "col_2": "bigint(20)"}],
        }
    )

    result = validate_sql("SELECT missing_col FROM approval_template_node", "approval_template_node", columns)

    assert not result.passed
    assert "字段不存在：missing_col" in result.errors


def test_validate_sql_allows_order_by_alias():
    columns = parse_describe_result(
        {
            "columnNames": [{"key": "col_1", "title": "Field"}, {"key": "col_2", "title": "Type"}],
            "columnDatas": [{"col_1": "nodeid", "col_2": "bigint(20)"}],
        }
    )

    result = validate_sql(
        "SELECT nodeid, COUNT(*) AS freq FROM approval_template_node GROUP BY nodeid ORDER BY freq DESC",
        "approval_template_node",
        columns,
        default_limit=1,
    )

    assert result.passed
    assert result.sql.endswith("LIMIT 1")


def test_validate_sql_rewrites_limit_to_requested_limit():
    columns = parse_describe_result(
        {
            "columnNames": [{"key": "col_1", "title": "Field"}, {"key": "col_2", "title": "Type"}],
            "columnDatas": [{"col_1": "node_id", "col_2": "bigint(20)"}],
        }
    )

    result = validate_sql(
        "SELECT node_id, COUNT(*) AS cnt FROM approval_template_node GROUP BY node_id ORDER BY cnt DESC LIMIT 1",
        "approval_template_node",
        columns,
        default_limit=2,
    )

    assert result.passed
    assert result.sql.endswith("LIMIT 2")
    assert "已按用户要求将 LIMIT 1 调整为 LIMIT 2" in result.assumptions


def test_validate_sql_allows_schema_qualified_table_name():
    columns = parse_describe_result(
        {
            "columnNames": [{"key": "col_1", "title": "Field"}, {"key": "col_2", "title": "Type"}],
            "columnDatas": [{"col_1": "metric_name", "col_2": "varchar(200)"}],
        }
    )

    result = validate_sql(
        "SELECT metric_name, COUNT(*) AS cnt FROM dw_onedba.db_alert_history GROUP BY metric_name ORDER BY cnt DESC",
        "db_alert_history",
        columns,
        default_limit=20,
    )

    assert result.passed
    assert result.sql.endswith("LIMIT 20")
