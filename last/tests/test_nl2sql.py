import json

import pytest

from app.nl2sql.generator import build_generate_sql_prompt
from app.nl2sql.intent import (
    DimensionSpec,
    FieldHint,
    MeasureSpec,
    NL2SQLIntent,
    TimeRangeSpec,
    intent_to_dict,
    normalize_identifier_hint,
    normalize_intent,
    operation_to_query_pattern,
    parse_nl2sql_intent,
    query_pattern_to_operation,
)
from app.nl2sql.resolver import format_database_candidates, resolve_database_candidate, resolve_table_candidate
from app.nl2sql.schema import ColumnSchema, parse_describe_result
from app.nl2sql.semantic_parser import build_semantic_parse_prompt, parse_custom_semantic_rule_with_llm
from app.nl2sql.semantics import (
    SANDBOX_SEMANTIC_RULES,
    SemanticContext,
    SemanticRule,
    SchemaInferenceSemanticProvider,
    StaticSandboxSemanticProvider,
    get_semantic_candidates,
    get_semantic_rules,
    parse_custom_semantic_rule,
    render_semantic_rules_for_prompt,
    save_user_semantic_rules,
)
from app.nl2sql.validator import validate_sql


class StubSemanticProvider:
    def __init__(self, rules):
        self.rules = rules

    async def get_rules(self, context):
        return self.rules


class StubLLMResponse:
    def __init__(self, content):
        self.content = content


class StubLLM:
    def __init__(self, content):
        self.content = content

    async def ainvoke(self, prompt):
        return StubLLMResponse(self.content)


def test_parse_nl2sql_intent_for_most_frequent_field():
    intent = parse_nl2sql_intent("帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么")

    assert intent.is_query
    assert intent.database_keyword == "dw-onedba-t1"
    assert intent.table_hint == "approval_template_node"
    assert intent.field_hints[0] == "nodeid"
    assert intent.query_pattern == "top_n_frequency"
    assert intent.dimensions == [DimensionSpec(field_hint="nodeid")]
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
    assert intent.query_pattern == "group_count_rank"
    assert intent.time_range == TimeRangeSpec(type="relative", value=30, unit="day")
    assert intent.time_days == 30
    assert intent.limit == 20


def test_operation_and_query_pattern_mapping_are_compatible():
    assert operation_to_query_pattern("most_frequent") == "top_n_frequency"
    assert operation_to_query_pattern("ranking_count") == "group_count_rank"
    assert query_pattern_to_operation("table_count_batch") == "table_counts"
    assert query_pattern_to_operation("single_table_count") == "count"


def test_normalize_intent_backfills_structured_fields_from_legacy_fields():
    intent = normalize_intent(
        NL2SQLIntent(
            is_query=True,
            user_input="查 nodeid 出现最多的两个",
            field_hints=["nodeid"],
            operation="most_frequent",
            limit=2,
        )
    )

    assert intent.query_pattern == "top_n_frequency"
    assert intent.structured_field_hints == [FieldHint(text="nodeid", role="dimension")]
    assert intent.dimensions == [DimensionSpec(field_hint="nodeid")]
    assert intent.measure == MeasureSpec(type="count", expression="COUNT(*)", alias="cnt")


def test_normalize_intent_backfills_legacy_operation_from_query_pattern():
    intent = normalize_intent(
        NL2SQLIntent(
            is_query=True,
            query_pattern="group_count_rank",
            field_hints=["metric_name"],
            operation="select",
        )
    )

    assert intent.operation == "ranking_count"
    assert intent.dimensions == [DimensionSpec(field_hint="metric_name")]


def test_intent_to_dict_serializes_nested_structured_fields():
    intent = normalize_intent(
        NL2SQLIntent(
            is_query=True,
            query_pattern="group_count_rank",
            field_hints=["metric_name"],
            time_range=TimeRangeSpec(type="relative", value=7, unit="day"),
        )
    )

    payload = intent_to_dict(intent)

    assert payload["dimensions"] == [{"field_hint": "metric_name", "resolved_field": ""}]
    assert payload["time_range"] == {
        "type": "relative",
        "value": 7,
        "unit": "day",
        "field_hint": "",
        "resolved_field": "",
    }


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
    assert "schemaName=`dw_onedba`" in result.question
    assert "instanceName=`dw-test-t1`" in result.question
    assert "schemaId=`1`" in result.question


def test_resolve_database_shows_candidates_when_no_high_confidence_match():
    result = resolve_database_candidate(
        [
            {"schemaId": 1, "schemaName": "dw_onedba", "instanceName": "dw-test-t1"},
            {"schemaId": 2, "schemaName": "app_metrics", "instanceName": "app-test-t1"},
        ],
        "missing",
    )

    assert result.needs_clarification
    assert result.candidates
    assert "可选候选" in result.question
    assert "schemaName=`dw_onedba`" in result.question
    assert "schemaName=`app_metrics`" in result.question


def test_format_database_candidates_handles_empty_list():
    assert format_database_candidates([]) == "- 无候选"


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


def test_semantic_rules_include_benchmark_business_metrics():
    rendered = render_semantic_rules_for_prompt(SANDBOX_SEMANTIC_RULES)

    assert "有效订单" in rendered
    assert "order_status IN ('paid', 'completed')" in rendered
    assert "支付成功" in rendered
    assert "payment_status = 'success'" in rendered
    assert "退款成功" in rendered
    assert "refund_status = 'approved'" in rendered
    assert "在售商品" in rendered
    assert "products.status = 'active'" in rendered
    assert "GMV" in rendered
    assert "SUM(orders.total_amount)" in rendered


@pytest.mark.asyncio
async def test_static_sandbox_semantic_rules_require_matching_domain():
    rules = await get_semantic_rules(
        SemanticContext(
            domain="mysql_sandbox",
            tables=("payments",),
            columns=(ColumnSchema("payment_status", "varchar(20)"),),
        ),
        provider=StaticSandboxSemanticProvider(),
    )

    assert [rule.name for rule in rules] == ["支付成功"]


@pytest.mark.asyncio
async def test_semantic_rules_are_empty_for_unconfigured_real_database():
    rules = await get_semantic_rules(
        SemanticContext(
            schema_id=123,
            database="dw_real",
            tables=("orders",),
            columns=(ColumnSchema("order_status", "varchar(20)"),),
        )
    )

    assert rules == []


@pytest.mark.asyncio
async def test_external_semantic_rules_are_filtered_by_current_schema():
    provider = StubSemanticProvider(
        [
            SemanticRule(
                name="有效订单",
                sql="order_status IN ('paid', 'completed')",
                tables=("orders",),
                required_columns=("order_status",),
                source="metadata_service",
            ),
            SemanticRule(
                name="GMV",
                sql="SUM(orders.total_amount)",
                tables=("orders",),
                required_columns=("total_amount",),
                source="metadata_service",
            ),
        ]
    )

    rules = await get_semantic_rules(
        SemanticContext(
            schema_id=123,
            database="dw_real",
            tables=("orders",),
            columns=(ColumnSchema("order_status", "varchar(20)"),),
        ),
        provider=provider,
    )

    assert [rule.name for rule in rules] == ["有效订单"]


@pytest.mark.asyncio
async def test_schema_inference_returns_candidates_not_injectable_rules():
    context = SemanticContext(
        tables=("orders",),
        columns=(ColumnSchema("order_status", "varchar(20)"), ColumnSchema("total_amount", "decimal(10,2)")),
        user_input="统计有效订单 GMV",
        sample_values={"order_status": ("paid", "completed", "cancelled")},
    )
    provider = SchemaInferenceSemanticProvider()

    injectable = await get_semantic_rules(context, provider=provider)
    candidates = await get_semantic_candidates(context, provider=provider)

    assert injectable == []
    assert {rule.name for rule in candidates} == {"有效订单", "GMV"}
    assert all(rule.requires_confirmation for rule in candidates)


@pytest.mark.asyncio
async def test_confirmed_user_semantic_rules_are_saved_and_reloaded(tmp_path):
    path = tmp_path / "user_semantic_rules.json"
    rule = SemanticRule(
        name="有效订单",
        sql="order_status IN ('paid', 'completed')",
        tables=("orders",),
        required_columns=("order_status",),
        source="user_confirmed",
        status="confirmed",
        requires_confirmation=False,
    )

    save_user_semantic_rules([rule], path=str(path))

    rules = await get_semantic_rules(
        SemanticContext(
            tables=("orders",),
            columns=(ColumnSchema("order_status", "varchar(20)"),),
        ),
        provider=StubSemanticProvider([SemanticRule.from_dict(json.loads(path.read_text())["rules"][0])]),
    )

    assert [loaded.name for loaded in rules] == ["有效订单"]
    assert rules[0].status == "confirmed"


def test_parse_custom_semantic_rule_validates_current_columns():
    context = SemanticContext(
        schema_id=1,
        tables=("orders",),
        columns=(ColumnSchema("order_status", "varchar(20)"),),
    )

    rule = parse_custom_semantic_rule("有效订单其实是 order_status IN ('paid', 'completed')", context)

    assert rule is not None
    assert rule.name == "有效订单"
    assert rule.sql == "order_status IN ('paid', 'completed')"
    assert rule.status == "confirmed"
    assert rule.source == "user_confirmed"
    assert rule.required_columns == ("order_status",)


def test_parse_custom_semantic_rule_rejects_unsafe_or_unknown_columns():
    context = SemanticContext(
        tables=("orders",),
        columns=(ColumnSchema("order_status", "varchar(20)"),),
    )

    assert parse_custom_semantic_rule("有效订单其实是 missing_status = 'paid'", context) is None
    assert parse_custom_semantic_rule("有效订单其实是 DELETE FROM orders", context) is None


def test_semantic_parse_prompt_constrains_llm_to_sql_fragment():
    prompt = build_semantic_parse_prompt(
        "有效订单就是已支付和已完成订单",
        SemanticContext(
            tables=("orders",),
            columns=(ColumnSchema("order_status", "varchar(20)"),),
            sample_values={"order_status": ("paid", "completed", "cancelled")},
        ),
    )

    assert "不生成完整 SQL" in prompt
    assert "不得返回 SELECT/INSERT/UPDATE/DELETE/DDL" in prompt
    assert "只能使用给定表结构中的字段" in prompt
    assert "paid" in prompt


@pytest.mark.asyncio
async def test_llm_semantic_parser_returns_confirmed_rule(monkeypatch):
    import app.nl2sql.semantic_parser as parser

    monkeypatch.setattr(parser, "is_llm_configured", lambda: True)
    monkeypatch.setattr(
        parser,
        "get_llm",
        lambda: StubLLM(
            json.dumps(
                {
                    "name": "有效订单",
                    "sql": "order_status IN ('paid', 'completed')",
                    "required_columns": ["order_status"],
                    "confidence": 0.92,
                    "needs_clarification": False,
                },
                ensure_ascii=False,
            )
        ),
    )

    rule = await parse_custom_semantic_rule_with_llm(
        "有效订单就是已支付和已完成订单",
        SemanticContext(
            schema_id=1,
            tables=("orders",),
            columns=(ColumnSchema("order_status", "varchar(20)"),),
            sample_values={"order_status": ("paid", "completed", "cancelled")},
        ),
    )

    assert rule is not None
    assert rule.name == "有效订单"
    assert rule.sql == "order_status IN ('paid', 'completed')"
    assert rule.source == "user_confirmed_llm_parsed"


@pytest.mark.asyncio
async def test_llm_semantic_parser_rejects_unknown_column(monkeypatch):
    import app.nl2sql.semantic_parser as parser

    monkeypatch.setattr(parser, "is_llm_configured", lambda: True)
    monkeypatch.setattr(
        parser,
        "get_llm",
        lambda: StubLLM(
            json.dumps(
                {
                    "name": "有效订单",
                    "sql": "missing_status = 'paid'",
                    "required_columns": ["missing_status"],
                    "confidence": 0.95,
                    "needs_clarification": False,
                },
                ensure_ascii=False,
            )
        ),
    )

    rule = await parse_custom_semantic_rule_with_llm(
        "有效订单就是已支付订单",
        SemanticContext(tables=("orders",), columns=(ColumnSchema("order_status", "varchar(20)"),)),
    )

    assert rule is None


def test_generate_sql_prompt_contains_mysql_and_business_constraints():
    prompt = build_generate_sql_prompt(
        NL2SQLIntent(is_query=True, user_input="查询每天有效订单 GMV", table_hint="orders"),
        "orders",
        [
            ColumnSchema("id", "bigint"),
            ColumnSchema("order_status", "varchar(20)"),
            ColumnSchema("total_amount", "decimal(10,2)"),
            ColumnSchema("paid_at", "datetime"),
        ],
        semantic_rules=[
            SemanticRule(name="有效订单", sql="order_status IN ('paid', 'completed')", tables=("orders",)),
            SemanticRule(name="GMV", sql="SUM(orders.total_amount)", tables=("orders",)),
        ],
        semantic_candidates=[
            SemanticRule(
                name="支付成功",
                sql="payment_status = 'success'",
                tables=("orders",),
                confidence=0.7,
                status="candidate",
                requires_confirmation=True,
            )
        ],
    )

    assert "不得翻译、意译或本地化枚举值" in prompt
    assert "过滤值只能来自三类来源" in prompt
    assert "业务语义层规则" in prompt
    assert "order_status IN ('paid', 'completed')" in prompt
    assert "SUM(orders.total_amount)" in prompt
    assert "MySQL 8" in prompt
    assert "窗口函数" in prompt
    assert "确定性 ORDER BY" in prompt
    assert "不要使用 SELECT *" in prompt
    assert "候选语义（未确认，不能直接用于 SQL）" in prompt
    assert "需用户确认，不能直接用于 SQL" in prompt
