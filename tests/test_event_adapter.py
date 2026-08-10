from app.agent.event_adapter import translate_event


def test_translate_thinking_text():
    # 模拟 deepagents messages 流中的文本增量
    raw = {"kind": "text_delta", "text": "我需要先查表"}
    events = translate_event(raw)
    assert events == [("text", {"text": "我需要先查表"})]


def test_translate_tool_start():
    raw = {"kind": "tool_call", "name": "find_table", "input": {"keyword": "order"}}
    events = translate_event(raw)
    assert events == [("tool_start", {"name": "find_table", "input": {"keyword": "order"}})]


def test_translate_tool_end():
    raw = {"kind": "tool_result", "name": "find_table", "content": "找到 3 张表", "elapsed_ms": 12.5}
    events = translate_event(raw)
    assert events == [("tool_end", {"name": "find_table", "content": "找到 3 张表", "elapsed_ms": 12.5})]
