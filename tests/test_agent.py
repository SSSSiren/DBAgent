from app.agent.nodes import extract_json, fallback_intent
from app.agent.graph import should_continue_after_act


def test_extract_json_from_fenced_block():
    assert extract_json("```json\n{\"a\": 1}\n```", {}) == {"a": 1}


def test_fallback_intent_detects_analysis():
    assert fallback_intent("帮我分析最近工单趋势")["intent"] == "analyze"


def test_graph_condition_confirmation_wins():
    assert should_continue_after_act({"needs_confirmation": True, "execution_plan": []}) == "confirm"
