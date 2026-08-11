"""测试 translate_event 将 deepagents 消息对象翻译为内部事件。"""

from app.agent.event_adapter import translate_event, _normalize_message


# ── _normalize_message 测试 ──

class TestNormalizeMessage:
    """验证 _normalize_message 对各类消息格式的规范化。"""

    def test_normalize_dict_ai_message(self):
        """dict 格式的 AI 消息（FakeAgent 风格）"""
        msg = {"content": "先查一下表", "tool_calls": [
            {"name": "find_table", "input": {"keyword": "order"}}
        ]}
        result = _normalize_message(msg)
        assert result["role"] == ""
        assert result["content"] == "先查一下表"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "find_table"
        assert result["tool_calls"][0]["arguments"] == {"keyword": "order"}

    def test_normalize_dict_tool_message(self):
        """dict 格式的工具结果消息"""
        msg = {"role": "tool", "name": "find_table", "content": "找到 3 张表",
               "tool_call_id": "call_123"}
        result = _normalize_message(msg)
        assert result["role"] == "tool"
        assert result["name"] == "find_table"
        assert result["content"] == "找到 3 张表"
        assert result["tool_call_id"] == "call_123"

    def test_normalize_dict_with_type_field(self):
        """dict 格式使用 type 字段（LangChain 风格）"""
        msg = {"type": "ai", "content": "思考中", "tool_calls": []}
        result = _normalize_message(msg)
        assert result["role"] == "ai"
        assert result["content"] == "思考中"

    def test_normalize_dict_with_tool_call_id(self):
        """仅有 tool_call_id 的 dict 应识别为 tool 角色"""
        msg = {"tool_call_id": "call_456", "name": "query_db", "content": "result"}
        result = _normalize_message(msg)
        assert result["role"] == "tool"

    def test_normalize_dict_tool_calls_args_variants(self):
        """兼容 arguments/args/input 三种参数字段名"""
        msg1 = {"tool_calls": [{"name": "t1", "arguments": {"x": 1}}]}
        assert _normalize_message(msg1)["tool_calls"][0]["arguments"] == {"x": 1}

        msg2 = {"tool_calls": [{"name": "t2", "args": {"y": 2}}]}
        assert _normalize_message(msg2)["tool_calls"][0]["arguments"] == {"y": 2}

        msg3 = {"tool_calls": [{"name": "t3", "input": {"z": 3}}]}
        assert _normalize_message(msg3)["tool_calls"][0]["arguments"] == {"z": 3}

    def test_normalize_empty_content(self):
        """content 为 None 或空字符串时返回空字符串"""
        assert _normalize_message({"content": None})["content"] == ""
        assert _normalize_message({"content": ""})["content"] == ""
        assert _normalize_message({})["content"] == ""


# ── translate_event 测试 ──

class TestTranslateEvent:
    """验证 translate_event 将消息翻译为内部事件元组。"""

    def test_translate_ai_message_with_text(self):
        """AIMessage 含文本 → text 事件"""
        msg = {"type": "ai", "content": "我需要先查表", "tool_calls": []}
        events = translate_event(msg)
        assert events == [("text", {"text": "我需要先查表"})]

    def test_translate_ai_message_with_text_and_tool_calls(self):
        """AIMessage 含文本 + tool_calls → text + tool_start 事件"""
        msg = {"type": "ai", "content": "先查一下表", "tool_calls": [
            {"name": "find_table", "input": {"keyword": "order"}}
        ]}
        events = translate_event(msg)
        assert events == [
            ("text", {"text": "先查一下表"}),
            ("tool_start", {"name": "find_table", "input": {"keyword": "order"}}),
        ]

    def test_translate_ai_message_with_multiple_tool_calls(self):
        """AIMessage 含多个 tool_calls → 多个 tool_start 事件"""
        msg = {"type": "ai", "content": "", "tool_calls": [
            {"name": "find_table", "input": {"keyword": "order"}},
            {"name": "describe_table", "input": {"table_name": "orders"}},
        ]}
        events = translate_event(msg)
        # 无文本内容，不产出 text
        assert events == [
            ("tool_start", {"name": "find_table", "input": {"keyword": "order"}}),
            ("tool_start", {"name": "describe_table", "input": {"table_name": "orders"}}),
        ]

    def test_translate_ai_message_without_content(self):
        """AIMessage 无文本内容且无 tool_calls → 空列表"""
        msg = {"type": "ai", "content": "", "tool_calls": []}
        events = translate_event(msg)
        assert events == []

    def test_translate_tool_message(self):
        """ToolMessage → tool_end 事件"""
        msg = {"role": "tool", "name": "find_table", "content": "找到 3 张表",
               "tool_call_id": "call_123"}
        events = translate_event(msg)
        assert events == [("tool_end", {
            "name": "find_table",
            "content": "找到 3 张表",
            "elapsed_ms": 0,
        })]

    def test_translate_tool_message_elapsed_ms_zero(self):
        """ToolMessage 的 elapsed_ms 固定为 0（deepagents 引擎不携带耗时）"""
        msg = {"role": "tool", "name": "slow_tool", "content": "done"}
        events = translate_event(msg)
        assert events[0][0] == "tool_end"
        assert events[0][1]["elapsed_ms"] == 0

    def test_translate_unknown_message(self):
        """无法识别的消息类型 → 空列表"""
        msg = {"type": "system", "content": "system prompt"}
        events = translate_event(msg)
        assert events == []

    def test_translate_fakeagent_dict(self):
        """FakeAgent 风格的 dict 消息（无 role/type 但有 tool_calls）"""
        msg = {"content": "先查一下表", "tool_calls": [
            {"name": "find_table", "input": {"keyword": "order"}}
        ]}
        events = translate_event(msg)
        # 有 tool_calls 所以被识别为 AI 消息
        assert ("text", {"text": "先查一下表"}) in events
        assert ("tool_start", {"name": "find_table", "input": {"keyword": "order"}}) in events

    def test_translate_langchain_aimessage_object(self):
        """LangChain AIMessage 对象 → 正确的内部事件"""
        from unittest.mock import MagicMock

        mock_tool_call = MagicMock()
        mock_tool_call.name = "find_table"
        mock_tool_call.args = {"keyword": "order"}

        msg = MagicMock()
        msg.type = "ai"
        msg.content = "我需要查一下"
        msg.tool_calls = [mock_tool_call]
        msg.name = ""

        events = translate_event(msg)
        assert events == [
            ("text", {"text": "我需要查一下"}),
            ("tool_start", {"name": "find_table", "input": {"keyword": "order"}}),
        ]

    def test_translate_langchain_toolmessage_object(self):
        """LangChain ToolMessage 对象 → tool_end 事件"""
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.type = "tool"
        msg.content = "查询结果"
        msg.name = "query_database"
        msg.tool_calls = []
        msg.tool_call_id = "call_789"

        events = translate_event(msg)
        assert events == [("tool_end", {
            "name": "query_database",
            "content": "查询结果",
            "elapsed_ms": 0,
        })]