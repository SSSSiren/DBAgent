import pytest

from app.agent.nodes import (
    extract_json,
    fallback_intent,
    fallback_plan,
    infer_keyword,
    infer_sql,
    infer_table_name,
    normalize_plan,
    plan_node,
    infer_select_database_keyword,
    infer_followup_database_keyword,
)
from app.agent.graph import should_continue_after_act


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
