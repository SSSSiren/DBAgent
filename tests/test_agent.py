import pytest

from app.agent.nodes import (
    _build_last_nl2sql_task,
    _result_summary,
    act_node,
    classify_followup,
    extract_json,
    fallback_intent,
    fallback_plan,
    infer_keyword,
    infer_sql,
    infer_table_name,
    normalize_plan,
    plan_node,
    run_followup_query,
    summarize_node,
    infer_select_database_keyword,
    infer_followup_database_keyword,
)
from app.agent.graph import should_continue_after_act
from app.agent.state import ToolCall
from app.api.routes import (
    SESSION_STORE,
    build_initial_state,
    build_confirmed_execution_plan,
    is_custom_semantic_rule,
    is_semantic_confirmation,
    latest_sql_from_state,
    looks_like_natural_language_semantic_rule,
    save_session,
    _tool_call_to_dict,
)
from app.nl2sql.generator import GeneratedSQL
from app.nl2sql.intent import parse_nl2sql_intent
from app.nl2sql.schema import ColumnSchema


def test_extract_json_from_fenced_block():
    assert extract_json("```json\n{\"a\": 1}\n```", {}) == {"a": 1}


def test_fallback_intent_detects_analysis():
    assert fallback_intent("帮我分析最近工单趋势")["intent"] == "analyze"


def test_graph_condition_confirmation_wins():
    assert should_continue_after_act({"needs_confirmation": True, "execution_plan": []}) == "confirm"


def test_infer_keyword_from_mixed_chinese_input():
    assert infer_keyword("帮我看看 onedba 相关的数据库") == "onedba"


def test_normalize_plan_fills_database_keyword():
    state = {
        "user_input": "帮我看看 onedba 相关的数据库",
        "parsed_intent": {"intent": "explore", "entities": {}},
    }
    plan = [{"tool": "list_databases", "args": {"keyword": "", "env_type": "test"}}]
    assert normalize_plan(state, plan)[0]["args"]["keyword"] == "onedba"


def test_infer_table_name_with_spaces_before_table_suffix():
    assert infer_table_name("帮我查查dw-onedba-t1数据库中approval template node表中出现最多的id是什么") == (
        "approval_template_node"
    )


def test_infer_sql_for_most_frequent_id():
    assert infer_sql("帮我查查dw-onedba-t1数据库中approval template node表中出现最多的id是什么") == (
        "SELECT id, COUNT(*) AS cnt FROM approval_template_node GROUP BY id ORDER BY cnt DESC LIMIT 1"
    )


def test_fallback_plan_chains_database_lookup_and_sql():
    state = {
        "user_input": "帮我查查dw-onedba-t1数据库中approval template node表中出现最多的id是什么",
        "parsed_intent": {"intent": "query", "entities": {}},
        "selected_schema_id": None,
    }

    plan = fallback_plan(state)

    assert plan == [
        {"tool": "list_databases", "args": {"keyword": "dw-onedba-t1", "env_type": "test"}},
        {
            "tool": "execute_sql",
            "args": {
                "sql": "SELECT id, COUNT(*) AS cnt FROM approval_template_node GROUP BY id ORDER BY cnt DESC LIMIT 1"
            },
        },
    ]


def test_infer_select_database_keyword():
    assert infer_select_database_keyword("使用 dw-onedba-t1") == "dw-onedba-t1"
    assert infer_select_database_keyword("选择 dw-onedba-t1 数据库") == "dw-onedba-t1"


def test_infer_followup_database_keyword():
    assert infer_followup_database_keyword("在onedba-t1实例上找") == "onedba-t1"


def test_classify_followup_requires_previous_query_context():
    result = classify_followup("把 SQL 给我", {})

    assert result == {"is_followup": False, "type": "not_follow_up", "confidence": 0.0}


def test_tool_call_to_dict_exposes_sql_for_followup_query():
    payload = _tool_call_to_dict(
        ToolCall(
            tool="followup_query",
            args={},
            status="completed",
            result={
                "content": "done",
                "steps": [{"name": "show_sql", "status": "completed"}],
                "sql": "SELECT 1",
                "table_name": "demo",
                "assumptions": [],
            },
        )
    )

    assert payload["nl2sql"]["sql"] == "SELECT 1"
    assert payload["nl2sql"]["steps"] == [{"name": "show_sql", "status": "completed"}]


@pytest.mark.asyncio
async def test_summarize_node_returns_database_candidates_directly(monkeypatch):
    async def fake_update_summary(old_summary, user_input, assistant_response):
        return assistant_response[:200]

    monkeypatch.setattr("app.agent.nodes.update_summary", fake_update_summary)
    content = (
        "找到多个匹配数据库，请选择一个：\n\n"
        "1. schemaName=`dw_onedba`，instanceName=`dw-onedba-t1`，schemaId=`1`"
    )
    result = await summarize_node(
        {
            "session_id": "s1",
            "user_input": "查询 dw-onedba-t1",
            "tool_calls": [
                ToolCall(
                    tool="nl2sql_query",
                    args={},
                    result={"content": content, "pending_nl2sql": {"user_input": "查询 dw-onedba-t1"}},
                    status="completed",
                )
            ],
        }
    )

    assert result["response"] == content
    assert "schemaName=`dw_onedba`" in result["response"]


def test_latest_sql_from_state_prefers_validated_sql():
    assert latest_sql_from_state({"last_generated_sql": "SELECT raw", "last_validated_sql": "SELECT checked"}) == (
        "SELECT checked"
    )
    assert latest_sql_from_state({"last_generated_sql": "SELECT raw"}) == "SELECT raw"


def test_classify_followup_show_sql_uses_last_sql_context():
    result = classify_followup("把 SQL 给我", {"last_validated_sql": "SELECT 1"})

    assert result["is_followup"]
    assert result["type"] == "show_sql"
    assert result["patch"] == {"op": "show_sql"}
    assert not result["needs_clarification"]


def test_classify_followup_change_limit_patch():
    result = classify_followup(
        "只看前 5 个",
        {"last_nl2sql_task": {"table": {"name": "db_alert_history"}, "limit": 20}},
    )

    assert result["is_followup"]
    assert result["type"] == "change_limit"
    assert result["patch"] == {"op": "replace_limit", "limit": 5}
    assert not result["needs_clarification"]


def test_classify_followup_change_time_range_patch():
    result = classify_followup(
        "改成最近 7 天",
        {"last_nl2sql_task": {"table": {"name": "db_alert_history"}, "time_field": "alert_time"}},
    )

    assert result["is_followup"]
    assert result["type"] == "change_time_range"
    assert result["patch"] == {"op": "replace_time_range", "time_range": {"type": "relative_days", "value": 7}}
    assert not result["needs_clarification"]


def test_classify_followup_change_time_range_requires_time_field():
    result = classify_followup(
        "改成最近 7 天",
        {"last_nl2sql_task": {"table": {"name": "db_alert_history"}}},
    )

    assert result["is_followup"]
    assert result["type"] == "change_time_range"
    assert result["needs_clarification"]
    assert "时间字段" in result["clarification_question"]


def test_semantic_confirmation_phrases_are_distinct_from_write_confirmation():
    assert is_semantic_confirmation("确认")
    assert is_semantic_confirmation("记住")
    assert not is_semantic_confirmation("确认执行")


def test_semantic_confirmation_plan_saves_rule_then_resumes_query():
    pending = {
        "rules": [{"name": "有效订单", "sql": "order_status IN ('paid', 'completed')"}],
        "resume": {
            "user_input": "统计 orders 表有效订单数",
            "selected_schema_id": 1,
            "selected_database": {"schemaName": "demo"},
        },
    }

    assert build_confirmed_execution_plan(None, pending) == [
        {"tool": "confirm_semantic_rules", "args": {"pending": pending}},
        {
            "tool": "nl2sql_query",
            "args": {
                "user_input": "统计 orders 表有效订单数",
                "selected_schema_id": 1,
                "selected_database": {"schemaName": "demo"},
            },
        },
    ]


def test_custom_semantic_rule_plan_saves_custom_rule_then_resumes_query():
    pending = {
        "context": {
            "schema_id": 1,
            "database": "demo",
            "tables": ["orders"],
            "columns": [{"name": "order_status", "type": "varchar(20)"}],
        },
        "rules": [{"name": "有效订单", "sql": "order_status IN ('paid', 'completed')"}],
        "resume": {"user_input": "统计 orders 表有效订单数"},
    }

    assert is_custom_semantic_rule("有效订单其实是 order_status = 'success'", pending)
    assert build_confirmed_execution_plan(None, pending, message="有效订单其实是 order_status = 'success'") == [
        {
            "tool": "save_custom_semantic_rule",
            "args": {"pending": pending, "message": "有效订单其实是 order_status = 'success'"},
        },
        {"tool": "nl2sql_query", "args": {"user_input": "统计 orders 表有效订单数"}},
    ]


def test_custom_semantic_rule_with_unknown_column_enters_validation_flow():
    pending = {
        "context": {
            "tables": ["orders"],
            "columns": [{"name": "order_status", "type": "varchar(20)"}],
        }
    }

    assert is_custom_semantic_rule("有效订单其实是 missing_status = 'success'", pending)


def test_natural_language_semantic_rule_can_enter_custom_rule_flow():
    pending = {
        "context": {
            "tables": ["orders"],
            "columns": [{"name": "order_status", "type": "varchar(20)"}],
        }
    }

    assert looks_like_natural_language_semantic_rule("有效订单就是已支付和已完成订单")
    assert is_custom_semantic_rule("有效订单就是已支付和已完成订单", pending)


def test_followup_memory_fields_round_trip_through_session_store():
    session_id = "followup-memory-round-trip"
    SESSION_STORE.pop(session_id, None)
    final_state = {
        "session_id": session_id,
        "user_input": "帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行",
        "response": "done",
        "last_nl2sql_task": {"table": {"name": "db_alert_history"}, "limit": 20},
        "nl2sql_task_stack": {"active_task_id": "t1"},
        "last_generated_sql": "SELECT metric_name FROM db_alert_history",
        "last_validated_sql": "SELECT metric_name FROM db_alert_history LIMIT 20",
        "last_result_preview": [{"metric_name": "cpu_usage", "cnt": 128}],
        "last_result_summary": {
            "row_count": 1,
            "columns": ["metric_name", "cnt"],
            "top_rows": [{"metric_name": "cpu_usage", "cnt": 128}],
            "empty": False,
        },
        "last_query_topic": "alert metric rank",
        "followup_patch": {"op": "replace_limit", "limit": 20},
        "long_term_memory_hints": [{"type": "schema_hint", "key": "default_time_field"}],
    }

    save_session(final_state)
    restored = build_initial_state(session_id, "把 SQL 给我")

    assert restored["last_nl2sql_task"] == final_state["last_nl2sql_task"]
    assert restored["nl2sql_task_stack"] == final_state["nl2sql_task_stack"]
    assert restored["last_generated_sql"] == final_state["last_generated_sql"]
    assert restored["last_validated_sql"] == final_state["last_validated_sql"]
    assert restored["last_result_preview"] == final_state["last_result_preview"]
    assert restored["last_result_summary"] == final_state["last_result_summary"]
    assert restored["last_query_topic"] == final_state["last_query_topic"]
    assert restored["followup_patch"] == final_state["followup_patch"]
    assert restored["long_term_memory_hints"] == final_state["long_term_memory_hints"]

    SESSION_STORE.pop(session_id, None)


def test_result_summary_uses_structured_onedba_result():
    summary = _result_summary(
        {
            "columnNames": [{"key": "col_1", "title": "metric_name"}, {"key": "col_2", "title": "cnt"}],
            "columnDatas": [
                {"col_1": "cpu_usage", "col_2": 128},
                {"col_1": "disk_usage", "col_2": 95},
            ],
        }
    )

    assert summary == {
        "row_count": 2,
        "columns": ["metric_name", "cnt"],
        "top_rows": [{"metric_name": "cpu_usage", "cnt": 128}, {"metric_name": "disk_usage", "cnt": 95}],
        "empty": False,
    }


def test_build_last_nl2sql_task_captures_patchable_query_shape():
    intent = parse_nl2sql_intent("帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行")
    columns = [
        ColumnSchema(name="metric_name", type="varchar(128)"),
        ColumnSchema(name="alert_time", type="datetime"),
    ]
    sql = (
        "SELECT metric_name, COUNT(*) AS cnt FROM db_alert_history "
        "WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
        "GROUP BY metric_name ORDER BY cnt DESC LIMIT 20"
    )

    task = _build_last_nl2sql_task(
        intent,
        65938636,
        {"schemaName": "dw_onedba", "instanceName": "dw-onedba-t1"},
        "db_alert_history",
        columns,
        GeneratedSQL(sql=sql, explanation="rank", used_columns=["metric_name"]),
        sql,
        ["使用 alert_time 作为最近 30 天的时间字段"],
    )

    assert task["table"]["name"] == "db_alert_history"
    assert task["operation"] == "ranking_count"
    assert task["group_by"] == ["metric_name"]
    assert task["time_field"] == "alert_time"
    assert task["where"] == [
        {"field": "alert_time", "operator": ">=", "value_type": "relative_days", "value": 30}
    ]
    assert task["limit"] == 20
    assert task["sql"] == sql


def followup_task_fixture() -> dict:
    return {
        "task_id": "t1",
        "user_question": "最近 30 天 metric_name 告警次数排行",
        "database": {"schema_id": 65938636, "schema_name": "dw_onedba", "instance_name": "dw-onedba-t1"},
        "table": {"name": "db_alert_history", "hint": "db_alert_history"},
        "operation": "ranking_count",
        "select_fields": [
            {"name": "metric_name", "role": "dimension"},
            {"name": "cnt", "role": "metric", "expression": "COUNT(*)"},
        ],
        "where": [{"field": "alert_time", "operator": ">=", "value_type": "relative_days", "value": 30}],
        "filters": [],
        "group_by": ["metric_name"],
        "order_by": [{"field": "cnt", "direction": "DESC"}],
        "limit": 20,
        "time_field": "alert_time",
        "table_schema": [
            {"name": "metric_name", "type": "varchar(128)"},
            {"name": "alert_time", "type": "datetime"},
        ],
        "sql": (
            "SELECT metric_name, COUNT(*) AS cnt FROM `db_alert_history` "
            "WHERE alert_time >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
            "GROUP BY metric_name ORDER BY cnt DESC LIMIT 20"
        ),
        "assumptions": ["最近 30 天使用字段 alert_time 过滤。"],
    }


@pytest.mark.asyncio
async def test_plan_node_routes_show_sql_followup():
    state = {
        "user_input": "把 SQL 给我",
        "parsed_intent": {"intent": "query", "entities": {}},
        "last_validated_sql": "SELECT 1",
    }

    result = await plan_node(state)

    assert result["execution_plan"][0]["tool"] == "followup_query"
    assert result["execution_plan"][0]["args"]["followup"]["type"] == "show_sql"


@pytest.mark.asyncio
async def test_run_followup_query_show_sql_returns_last_sql():
    result = await run_followup_query(
        "把 SQL 给我",
        {"is_followup": True, "type": "show_sql", "patch": {"op": "show_sql"}},
        last_validated_sql="SELECT 1",
    )

    assert "```sql\nSELECT 1\n```" in result["content"]
    assert result["followup_patch"] == {"op": "show_sql"}


@pytest.mark.asyncio
async def test_run_followup_query_change_limit_executes_patched_task(monkeypatch):
    executed = {}

    async def fake_execute_sql(schema_id, sql):
        executed["schema_id"] = schema_id
        executed["sql"] = sql
        return {
            "columnNames": [{"key": "col_1", "title": "metric_name"}, {"key": "col_2", "title": "cnt"}],
            "columnDatas": [{"col_1": "cpu_usage", "col_2": 128}],
        }

    monkeypatch.setattr("app.agent.nodes.onedba_client.execute_sql", fake_execute_sql)

    result = await run_followup_query(
        "只看前 5 个",
        {"is_followup": True, "type": "change_limit", "patch": {"op": "replace_limit", "limit": 5}},
        last_nl2sql_task=followup_task_fixture(),
    )

    assert executed["schema_id"] == 65938636
    assert executed["sql"].endswith("LIMIT 5")
    assert result["last_nl2sql_task"]["limit"] == 5
    assert result["last_validated_sql"].endswith("LIMIT 5")
    assert result["last_result_summary"]["top_rows"] == [{"metric_name": "cpu_usage", "cnt": 128}]


@pytest.mark.asyncio
async def test_run_followup_query_change_time_range_executes_patched_task(monkeypatch):
    executed = {}

    async def fake_execute_sql(schema_id, sql):
        executed["sql"] = sql
        return {"columnNames": [{"key": "col_1", "title": "metric_name"}], "columnDatas": []}

    monkeypatch.setattr("app.agent.nodes.onedba_client.execute_sql", fake_execute_sql)

    result = await run_followup_query(
        "改成最近 7 天",
        {
            "is_followup": True,
            "type": "change_time_range",
            "patch": {"op": "replace_time_range", "time_range": {"type": "relative_days", "value": 7}},
        },
        last_nl2sql_task=followup_task_fixture(),
    )

    assert "INTERVAL 7 DAY" in executed["sql"]
    assert result["last_nl2sql_task"]["where"] == [
        {"field": "alert_time", "operator": ">=", "value_type": "relative_days", "value": 7}
    ]


@pytest.mark.asyncio
async def test_act_node_stores_nl2sql_followup_memory(monkeypatch):
    async def fake_invoke_tool(tool_name, args):
        return {
            "content": "done",
            "selected_schema_id": 1,
            "selected_database": {"schemaName": "demo"},
            "last_nl2sql_task": {"table": {"name": "orders"}},
            "last_generated_sql": "SELECT status FROM orders",
            "last_validated_sql": "SELECT status FROM orders LIMIT 20",
            "last_result_preview": [{"status": "paid"}],
            "last_result_summary": {
                "row_count": 1,
                "columns": ["status"],
                "top_rows": [{"status": "paid"}],
                "empty": False,
            },
        }

    monkeypatch.setattr("app.agent.nodes._invoke_tool", fake_invoke_tool)

    updates = await act_node(
        {
            "execution_plan": [{"tool": "nl2sql_query", "args": {"user_input": "统计 orders 表"}}],
            "tool_calls": [],
        }
    )

    assert updates["last_nl2sql_task"] == {"table": {"name": "orders"}}
    assert updates["last_generated_sql"] == "SELECT status FROM orders"
    assert updates["last_validated_sql"] == "SELECT status FROM orders LIMIT 20"
    assert updates["last_result_preview"] == [{"status": "paid"}]
    assert updates["last_result_summary"]["top_rows"] == [{"status": "paid"}]


def test_infer_sql_for_most_frequent_nodeid():
    assert infer_sql("帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么") == (
        "SELECT nodeid, COUNT(*) AS cnt FROM approval_template_node GROUP BY nodeid ORDER BY cnt DESC LIMIT 1"
    )


def test_normalize_plan_fills_missing_execute_sql_sql():
    state = {
        "user_input": "帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么",
        "parsed_intent": {"intent": "query", "entities": {}},
        "selected_schema_id": 65938636,
    }
    plan = [{"tool": "execute_sql", "args": {"schema_id": 65938636}}]

    normalized = normalize_plan(state, plan)

    assert normalized == [
        {
            "tool": "execute_sql",
            "args": {
                "schema_id": 65938636,
                "sql": "SELECT nodeid, COUNT(*) AS cnt FROM approval_template_node GROUP BY nodeid ORDER BY cnt DESC LIMIT 1",
            },
        }
    ]


def test_normalize_plan_replaces_missing_describe_table_with_sql():
    state = {
        "user_input": "帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么",
        "parsed_intent": {"intent": "query", "entities": {}},
        "selected_schema_id": 65938636,
    }
    plan = [{"tool": "describe_table", "args": {"schema_id": 65938636}}]

    normalized = normalize_plan(state, plan)

    assert normalized == [
        {
            "tool": "execute_sql",
            "args": {
                "sql": "SELECT nodeid, COUNT(*) AS cnt FROM approval_template_node GROUP BY nodeid ORDER BY cnt DESC LIMIT 1",
                "schema_id": 65938636,
            },
        }
    ]


@pytest.mark.asyncio
async def test_plan_node_routes_table_query_to_nl2sql_workflow():
    state = {
        "user_input": "帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么",
        "parsed_intent": {"intent": "query", "entities": {}},
        "selected_schema_id": None,
    }

    result = await plan_node(state)

    assert result["execution_plan"] == [
        {
            "tool": "nl2sql_query",
            "args": {
                "user_input": "帮我查查dw-onedba-t1数据库中approval template node表中出现最多的nodeid是什么",
                "summary": "",
                "selected_schema_id": None,
                "selected_database": None,
                "database_keyword": "",
            },
        }
    ]


@pytest.mark.asyncio
async def test_plan_node_passes_selected_database_to_nl2sql_workflow():
    state = {
        "user_input": "帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行",
        "parsed_intent": {"intent": "query", "entities": {}},
        "selected_schema_id": 65938636,
        "selected_database": {"schemaName": "dw_onedba", "instanceName": "dw-onedba-t1"},
        "summary": "当前选择 dw-onedba-t1",
    }

    result = await plan_node(state)

    assert result["execution_plan"] == [
        {
            "tool": "nl2sql_query",
            "args": {
                "user_input": "帮我分析 db_alert_history 表中最近 30 天不同 metric_name 的告警次数排行",
                "summary": "当前选择 dw-onedba-t1",
                "selected_schema_id": 65938636,
                "selected_database": {"schemaName": "dw_onedba", "instanceName": "dw-onedba-t1"},
                "database_keyword": "",
            },
        }
    ]


@pytest.mark.asyncio
async def test_plan_node_routes_select_database_command():
    state = {
        "user_input": "使用 dw-onedba-t1",
        "parsed_intent": {"intent": "query", "entities": {}},
    }

    result = await plan_node(state)

    assert result["execution_plan"] == [{"tool": "select_database", "args": {"keyword": "dw-onedba-t1"}}]


@pytest.mark.asyncio
async def test_plan_node_continues_pending_nl2sql_with_followup_database():
    state = {
        "user_input": "在onedba-t1实例上找",
        "pending_nl2sql": {"user_input": "dw onedba t1数据库 找找alert history表中有多少个字段"},
        "summary": "",
    }

    result = await plan_node(state)

    assert result["execution_plan"] == [
        {
            "tool": "nl2sql_query",
            "args": {
                "user_input": "dw onedba t1数据库 找找alert history表中有多少个字段",
                "summary": "",
                "selected_schema_id": None,
                "selected_database": None,
                "database_keyword": "onedba-t1",
            },
        }
    ]
