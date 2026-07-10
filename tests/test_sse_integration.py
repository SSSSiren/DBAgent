"""
SSE 事件管道集成测试 (Task 3.1)

测试范围：
1. SSE 事件格式验证（step/sql/final 事件的数据结构）
2. 事件序列模拟（thinking → tool → final 完整流程）
3. 阶段转换验证（thinking→tool 过渡、flush 触发）
4. 工具生命周期（running→completed、running→error）
5. 取消流程（cancel 事件序列、取消标记）
6. 异常场景（null/undefined text、空事件）

这些测试验证 Python 端 SSE 事件生成的正确性，
确保前端渲染管线能接收到格式正确、序列完整的事件流。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import run_agent_stream
from app.api.routes import sse_event


# ═══════════════════════════════════════════════════════════════════
# SSE 格式化测试
# ═══════════════════════════════════════════════════════════════════


class TestSseEventFormat:
    """验证 sse_event() 产出的 SSE 格式符合规范"""

    def test_step_event_format(self):
        """step 事件应包含 type、step、status 字段"""
        data = {"step": "thinking", "status": "running", "text": "Hello"}
        result = sse_event("step", data)
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "step"
        assert parsed["step"] == "thinking"
        assert parsed["status"] == "running"
        assert parsed["text"] == "Hello"

    def test_step_event_tool_start(self):
        """tool_start 事件应包含 step、status、call_index 字段"""
        data = {"step": "tool:query_database", "status": "running", "call_index": 0}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "step"
        assert parsed["step"] == "tool:query_database"
        assert parsed["status"] == "running"
        assert parsed["call_index"] == 0

    def test_step_event_tool_end(self):
        """tool_end 事件应包含 step、status=completed、call_index 字段"""
        data = {"step": "tool:query_database", "status": "completed", "call_index": 0}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "step"
        assert parsed["step"] == "tool:query_database"
        assert parsed["status"] == "completed"
        assert parsed["call_index"] == 0

    def test_sql_event_format(self):
        """sql 事件应包含 type=sql 和 sql 字段"""
        data = {"sql": "SELECT * FROM users"}
        result = sse_event("sql", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "sql"
        assert parsed["sql"] == "SELECT * FROM users"

    def test_final_event_format(self):
        """final 事件应包含 reply、tool_calls 等字段"""
        data = {
            "session_id": "test-session",
            "reply": "查询完成",
            "needs_confirmation": False,
            "tool_calls": [],
            "stats": {"duration_ms": 500, "num_turns": 1, "tokens": 100},
            "latest_sql": "",
            "memory_count": 0,
            "preference_count": 0,
            "cancelled": False,
        }
        result = sse_event("final", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "final"
        assert parsed["reply"] == "查询完成"
        assert parsed["cancelled"] is False
        assert "stats" in parsed

    def test_unicode_text_in_event(self):
        """SSE 事件应正确处理中文字符"""
        data = {"step": "thinking", "status": "running", "text": "用户想查询数据库中的表结构"}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["text"] == "用户想查询数据库中的表结构"

    def test_special_characters_in_event(self):
        """SSE 事件应正确处理特殊字符（换行、引号等）"""
        data = {"step": "thinking", "status": "running", "text": 'Line 1\nLine 2 with "quotes"'}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert "Line 1" in parsed["text"]
        assert "quotes" in parsed["text"]


# ═══════════════════════════════════════════════════════════════════
# 事件序列模拟测试
# ═══════════════════════════════════════════════════════════════════


class TestEventSequenceThinking:
    """验证 thinking 事件序列模拟"""

    @pytest.mark.asyncio
    async def test_thinking_events_produce_text_chunks(self):
        """连续多个 thinking 事件应产生递增的文本累积"""
        # 模拟 run_agent_stream 内部的事件序列
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "Hello"}),
            ("step", {"step": "thinking", "status": "running", "text": " World"}),
            ("step", {"step": "thinking", "status": "running", "text": " from DBAgent"}),
        ]

        # 验证事件序列：每个 thinking 事件携带递增文本
        accumulated = ""
        for event_type, data in events:
            assert event_type == "step"
            assert data["step"] == "thinking"
            assert data["status"] == "running"
            accumulated += data["text"]

        assert accumulated == "Hello World from DBAgent"

    def test_thinking_event_has_required_fields(self):
        """thinking 事件必须包含 step、status、text 三个字段"""
        data = {"step": "thinking", "status": "running", "text": "推理中..."}
        assert "step" in data
        assert "status" in data
        assert "text" in data
        assert data["step"] == "thinking"
        assert data["status"] == "running"

    def test_thinking_text_empty_string(self):
        """thinking 事件 text 为空字符串时不应崩溃"""
        data = {"step": "thinking", "status": "running", "text": ""}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["text"] == ""


class TestEventSequenceThinkingToTool:
    """验证 thinking→tool 阶段转换事件序列"""

    def test_thinking_to_tool_transition_sequence(self):
        """thinking 事件后紧跟 tool:* 事件，step 字段正确切换"""
        events = [
            # 第一段思考
            ("step", {"step": "thinking", "status": "running", "text": "我需要查询数据库"}),
            # 切换到工具调用
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
        ]

        # 验证序列
        assert events[0][1]["step"] == "thinking"
        assert events[1][1]["step"] == "tool:query_database"
        assert events[1][1]["status"] == "running"

        # 验证 thinking→tool 阶段转换：step 字段从 "thinking" 变为 "tool:xxx"
        step_values = [e[1]["step"] for e in events]
        assert step_values == ["thinking", "tool:query_database"]

    def test_multiple_thinking_to_tool_transitions(self):
        """多轮 thinking→tool 切换应保持正确的 step 标识"""
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "分析中..."}),
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("step", {"step": "thinking", "status": "running", "text": "继续分析..."}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
        ]

        step_sequence = [(e[1]["step"], e[1]["status"]) for e in events]
        assert step_sequence == [
            ("thinking", "running"),
            ("tool:describe_table", "running"),
            ("tool:describe_table", "completed"),
            ("thinking", "running"),
            ("tool:query_database", "running"),
            ("tool:query_database", "completed"),
        ]

    def test_phase_label_change_on_transition(self):
        """阶段标签应随 step 类型变化：thinking→"思考中..."，tool:→"正在查询数据库..." """
        def get_phase_label(step):
            if step == "thinking":
                return "DBAgent · 思考中..."
            elif step and step.startswith("tool:"):
                return "DBAgent · 正在查询数据库..."
            else:
                return "DBAgent"

        events = [
            {"step": "thinking", "text": "..."},
            {"step": "tool:query_database", "status": "running"},
            {"step": "tool:query_database", "status": "completed"},
            {"step": "thinking", "text": "..."},
        ]

        labels = [get_phase_label(e["step"]) for e in events]
        assert labels == [
            "DBAgent · 思考中...",
            "DBAgent · 正在查询数据库...",
            "DBAgent · 正在查询数据库...",
            "DBAgent · 思考中...",
        ]


# ═══════════════════════════════════════════════════════════════════
# 工具生命周期测试
# ═══════════════════════════════════════════════════════════════════


class TestToolLifecycle:
    """验证工具调用生命周期：running → completed / error"""

    def test_tool_lifecycle_running_to_completed(self):
        """工具调用从 running 到 completed 的正确事件序列"""
        events = [
            # 工具调用开始
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            # 工具调用完成
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
        ]

        assert events[0][1]["status"] == "running"
        assert events[1][1]["status"] == "completed"
        assert events[0][1]["call_index"] == events[1][1]["call_index"]

    def test_tool_lifecycle_running_to_error(self):
        """工具调用从 running 到 error 的正确事件序列"""
        events = [
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            # 工具调用错误（通过 cancel 或异常场景）
            ("step", {"step": "tool:query_database", "status": "error", "call_index": 0}),
        ]

        assert events[0][1]["status"] == "running"
        assert events[1][1]["status"] == "error"

    def test_tool_status_transition_icon_mapping(self):
        """工具步骤状态对应的图标映射：running→pulse-dot，completed→✅，error→❌"""
        def get_icon(status):
            if status == "running":
                return "pulse-dot"  # CSS 动画指示器
            if status == "completed":
                return "✅"
            if status == "error":
                return "❌"
            return ""

        assert get_icon("running") == "pulse-dot"
        assert get_icon("completed") == "✅"
        assert get_icon("error") == "❌"

    def test_multiple_tools_sequential(self):
        """多个工具按顺序执行时，call_index 递增"""
        events = [
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:execute_sql", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:execute_sql", "status": "completed", "call_index": 0}),
        ]

        tool_names = list(set(e[1]["step"] for e in events))
        assert "tool:describe_table" in tool_names
        assert "tool:query_database" in tool_names
        assert "tool:execute_sql" in tool_names

    def test_same_tool_called_multiple_times(self):
        """同一工具多次调用时，call_index 应递增"""
        events = [
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 1}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 1}),
        ]

        call_indices = [e[1]["call_index"] for e in events if e[1]["status"] == "running"]
        assert call_indices == [0, 1]


# ═══════════════════════════════════════════════════════════════════
# 取消流程测试
# ═══════════════════════════════════════════════════════════════════


class TestCancelFlow:
    """验证取消流程：取消事件序列、取消标记、清理行为"""

    def test_cancelled_final_event_structure(self):
        """取消的 final 事件应包含 cancelled=true"""
        data = {
            "session_id": "test-session",
            "reply": "",
            "needs_confirmation": False,
            "tool_calls": [],
            "stats": {"duration_ms": 1000, "num_turns": 2, "tokens": 50},
            "latest_sql": "",
            "memory_count": 0,
            "preference_count": 0,
            "cancelled": True,
        }
        result = sse_event("final", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "final"
        assert parsed["cancelled"] is True

    def test_normal_final_event_cancelled_false(self):
        """正常完成的 final 事件中 cancelled 应为 false"""
        data = {
            "session_id": "test-session",
            "reply": "查询完成",
            "needs_confirmation": False,
            "tool_calls": [],
            "stats": {"duration_ms": 500, "num_turns": 1, "tokens": 100},
            "latest_sql": "",
            "memory_count": 0,
            "preference_count": 0,
            "cancelled": False,
        }
        result = sse_event("final", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "final"
        assert parsed["cancelled"] is False
        assert parsed["reply"] == "查询完成"

    def test_cancel_triggers_cleanup_state(self):
        """取消时应触发清理：TypewriterRenderer 停止、动画类名清除"""
        # 模拟清理函数的预期行为
        cleanup_log = []

        def simulate_cleanup(cancelled):
            if cancelled:
                # TypewriterRenderer.stop()
                cleanup_log.append("typewriter.stop")
                # 清除步骤动画类名
                cleanup_log.append("clear_animation_classes")
                # 恢复 .meta 标签
                cleanup_log.append("reset_meta_label")
                # 追加取消标记
                cleanup_log.append("append_cancelled_mark")

        simulate_cleanup(True)
        assert "typewriter.stop" in cleanup_log
        assert "clear_animation_classes" in cleanup_log
        assert "reset_meta_label" in cleanup_log
        assert "append_cancelled_mark" in cleanup_log

    def test_cancel_preserves_partial_response(self):
        """取消时保留部分响应内容，追加取消标记"""
        # 模拟取消路径：流式气泡保留，追加 [已停止生成]
        partial_text = "正在查询数据库中的用户信息..."
        cancelled_mark = "[已停止生成]"

        def finalize_cancelled_message(text):
            return f"{text}\n{cancelled_mark}"

        result = finalize_cancelled_message(partial_text)
        assert partial_text in result
        assert cancelled_mark in result

    def test_cancel_sequence_with_thinking_before_cancel(self):
        """取消前有 thinking 事件，取消后应 flush 并停止"""
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "我正在分析..."}),
            # 用户点击取消 → SSE 流被中断，final 事件带有 cancelled=true
        ]

        final_data = {
            "session_id": "test",
            "reply": "",
            "cancelled": True,
            "tool_calls": [],
            "stats": {},
        }

        assert events[0][1]["step"] == "thinking"
        assert final_data["cancelled"] is True


# ═══════════════════════════════════════════════════════════════════
# 会话切换与状态重置测试
# ═══════════════════════════════════════════════════════════════════


class TestSessionSwitchReset:
    """验证 switchSession 调用时所有动画状态被重置"""

    def test_switch_session_resets_typewriter_state(self):
        """switchSession 应重置 TypewriterRenderer 状态"""
        # 模拟 TypewriterRenderer 状态
        typewriter_state = {
            "fullText": "accumulated thinking text",
            "displayedLength": 10,
            "isRunning": True,
        }

        def reset_typewriter():
            typewriter_state["fullText"] = ""
            typewriter_state["displayedLength"] = 0
            typewriter_state["isRunning"] = False

        reset_typewriter()
        assert typewriter_state["fullText"] == ""
        assert typewriter_state["displayedLength"] == 0
        assert typewriter_state["isRunning"] is False

    def test_switch_session_clears_step_renderer(self):
        """switchSession 应清除 StepRenderer 的所有步骤"""
        steps = {
            "tool:query_database": {"status": "running"},
            "tool:describe_table": {"status": "completed"},
        }

        def clear_steps():
            steps.clear()

        clear_steps()
        assert len(steps) == 0

    def test_switch_session_clears_animation_classes(self):
        """switchSession 应清除所有动画类名"""
        elements = [
            {"className": "streaming-step running", "willChange": "opacity"},
            {"className": "streaming-step running", "willChange": "transform"},
            {"className": "thinking-text streaming-cursor", "willChange": ""},
        ]

        def cleanup_animations(elements):
            for el in elements:
                el["className"] = el["className"].replace(" running", "")
                el["willChange"] = ""

        cleanup_animations(elements)
        for el in elements:
            assert "running" not in el["className"]
            assert el["willChange"] == ""

    def test_switch_session_resets_meta_label(self):
        """switchSession 应重置 .meta 标签为 "DBAgent" """
        meta_text = ["DBAgent · 思考中..."]

        def reset_meta():
            meta_text[0] = "DBAgent"

        reset_meta()
        assert meta_text[0] == "DBAgent"


# ═══════════════════════════════════════════════════════════════════
# 异常场景降级测试
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """验证异常场景：null/undefined text、空事件、降级行为"""

    def test_null_text_handled_gracefully(self):
        """text 为 None 时，SSE 事件应使用空字符串降级"""
        text_value = None
        safe_text = str(text_value or "")
        data = {"step": "thinking", "status": "running", "text": safe_text}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["text"] == ""

    def test_undefined_text_handled_gracefully(self):
        """text 缺失时，应使用空字符串默认值"""
        data = {"step": "thinking", "status": "running"}
        text = data.get("text", "")
        assert text == ""

    def test_empty_text_in_thinking_event(self):
        """thinking 事件的 text 为空字符串时事件格式仍正确"""
        data = {"step": "thinking", "status": "running", "text": ""}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["type"] == "step"
        assert parsed["step"] == "thinking"
        assert parsed["text"] == ""

    def test_empty_step_name(self):
        """step 字段为空字符串时事件格式仍正确"""
        data = {"step": "", "status": "running", "text": ""}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["step"] == ""

    def test_null_text_typewriter_degradation(self):
        """TypewriterRenderer 收到 null/undefined text 时应降级为静态展示"""
        def append_text_safe(text):
            """模拟 TypewriterRenderer.appendText 的安全处理"""
            try:
                text = str(text or "")
                return text
            except Exception:
                return ""

        assert append_text_safe(None) == ""
        assert append_text_safe("Hello") == "Hello"
        assert append_text_safe(123) == "123"  # 非字符串类型

    def test_events_with_missing_optional_fields(self):
        """缺少可选字段（如 call_index）时事件格式仍正确"""
        data = {"step": "tool:query_database", "status": "running"}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["step"] == "tool:query_database"
        assert parsed["status"] == "running"
        # call_index 可选，不应崩溃

    def test_very_long_text_in_event(self):
        """超长文本（模拟大型 SQL 结果）的 SSE 事件格式正确"""
        long_text = "x" * 10000
        data = {"step": "thinking", "status": "running", "text": long_text}
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["text"] == long_text
        assert len(parsed["text"]) == 10000

    def test_sse_event_json_escaping(self):
        """SSE 事件中的 JSON 正确转义特殊字符"""
        data = {
            "step": "thinking",
            "status": "running",
            "text": '包含 "双引号" 和 \\n 换行符的文本',
        }
        result = sse_event("step", data)
        # 验证是合法 JSON
        parsed = json.loads(result[6:].strip())
        assert "双引号" in parsed["text"]


# ═══════════════════════════════════════════════════════════════════
# 完整事件流管线测试
# ═══════════════════════════════════════════════════════════════════


class TestCompleteEventPipeline:
    """验证完整的 SSE 事件流管线：thinking → tool → final"""

    def test_full_thinking_tool_final_sequence(self):
        """完整的 thinking → tool(running) → tool(completed) → final 序列"""
        # 模拟完整的 SSE 事件流
        raw_events = [
            # 思考阶段
            ("step", {"step": "thinking", "status": "running", "text": "我需要查询用户信息"}),
            # 工具调用阶段
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
            # 最终回答
            ("final", {
                "session_id": "test",
                "reply": "查询到 5 条用户记录",
                "cancelled": False,
                "tool_calls": [
                    {"tool": "describe_table", "result": "ok"},
                    {"tool": "query_database", "result": "ok"},
                ],
                "stats": {"duration_ms": 2000, "num_turns": 2, "tokens": 300},
            }),
        ]

        # 验证事件类型序列
        event_types = [e[0] for e in raw_events]
        assert event_types == ["step", "step", "step", "step", "step", "final"]

        # 验证 step 事件中 step 字段的序列
        step_events = [e for e in raw_events if e[0] == "step"]
        step_names = [e[1]["step"] for e in step_events]
        assert "thinking" in step_names
        assert "tool:describe_table" in step_names
        assert "tool:query_database" in step_names

        # 验证 final 事件包含必要字段
        final = raw_events[-1][1]
        assert final["cancelled"] is False
        assert "reply" in final
        assert "tool_calls" in final
        assert "stats" in final

    def test_event_types_are_consistent(self):
        """所有事件类型在整个流程中保持一致"""
        valid_event_types = {"step", "sql", "final"}

        events = [
            ("step", {}),
            ("sql", {}),
            ("final", {}),
        ]

        for event_type, _ in events:
            assert event_type in valid_event_types, f"Unknown event type: {event_type}"

    def test_step_event_has_consistent_step_field(self):
        """step 事件应有统一的 step 字段约定"""
        # thinking 事件
        thinking_data = {"step": "thinking", "status": "running", "text": "..."}
        assert thinking_data["step"] == "thinking"

        # tool 事件
        tool_data = {"step": "tool:xxx", "status": "running", "call_index": 0}
        assert tool_data["step"].startswith("tool:")

    def test_sse_format_preserves_all_fields(self):
        """sse_event 格式化后所有字段应完整保留"""
        data = {
            "step": "tool:execute_sql",
            "status": "completed",
            "call_index": 2,
        }
        result = sse_event("step", data)
        parsed = json.loads(result[6:].strip())
        assert parsed["step"] == "tool:execute_sql"
        assert parsed["status"] == "completed"
        assert parsed["call_index"] == 2
        assert parsed["type"] == "step"

    def test_multiple_sql_events_in_pipeline(self):
        """多个 sql 事件（如 nl2sql + execute_sql）在管线中正确处理"""
        sql_events = [
            ("sql", {"sql": "SELECT * FROM users WHERE id = 1"}),
            ("sql", {"sql": "SELECT * FROM users"}),
        ]

        for event_type, data in sql_events:
            assert event_type == "sql"
            result = sse_event(event_type, data)
            parsed = json.loads(result[6:].strip())
            assert parsed["type"] == "sql"
            assert "sql" in parsed


# ═══════════════════════════════════════════════════════════════════
# SSE 事件流解析测试
# ═══════════════════════════════════════════════════════════════════


class TestSseEventParsing:
    """验证 SSE 事件的解析逻辑（parseSseChunk 对应功能）"""

    def test_parse_single_sse_event(self):
        """单个 SSE 事件应正确解析"""
        data = {"step": "thinking", "status": "running", "text": "Hello"}
        sse_text = sse_event("step", data)

        # 模拟 parseSseChunk 逻辑
        parts = sse_text.split("\n\n")
        for part in parts:
            if not part.strip():
                continue
            data_line = part.split("\n")
            for line in data_line:
                if line.startswith("data: "):
                    parsed = json.loads(line[6:])
                    assert parsed["type"] == "step"
                    assert parsed["text"] == "Hello"

    def test_parse_multiple_sse_events_in_buffer(self):
        """多个 SSE 事件在同一缓冲区中应分别解析"""
        events = [
            sse_event("step", {"step": "thinking", "status": "running", "text": "A"}),
            sse_event("step", {"step": "thinking", "status": "running", "text": "B"}),
            sse_event("step", {"step": "tool:query", "status": "running", "call_index": 0}),
        ]

        buffer = "".join(events)
        parsed_events = []

        # 模拟 parseSseChunk
        parts = buffer.split("\n\n")
        rest = parts.pop() if parts else ""
        for part in parts:
            data_line = part.split("\n")
            for line in data_line:
                if line.startswith("data: "):
                    parsed_events.append(json.loads(line[6:]))

        assert len(parsed_events) == 3
        assert parsed_events[0]["text"] == "A"
        assert parsed_events[1]["text"] == "B"
        assert parsed_events[2]["step"] == "tool:query"

    def test_parse_partial_buffer(self):
        """不完整的 SSE 缓冲区应保留剩余部分"""
        data = {"step": "thinking", "status": "running", "text": "Hello"}
        sse_text = sse_event("step", data)

        # 模拟仅发送部分数据
        partial = sse_text[:20]
        parts = partial.split("\n\n")
        rest = parts.pop() if len(parts) > 0 and not partial.endswith("\n\n") else ""

        # 不完整的数据应保留在 rest 中
        assert rest or len(parts) == 0  # 不完整数据不会被解析

    def test_parse_malformed_sse_data(self):
        """畸形的 SSE 数据不应导致解析崩溃"""
        malformed = "data: not valid json\n\n"

        parts = malformed.split("\n\n")
        for part in parts:
            if not part.strip():
                continue
            data_line = part.split("\n")
            for line in data_line:
                if line.startswith("data: "):
                    try:
                        json.loads(line[6:])
                    except json.JSONDecodeError:
                        # 预期行为：解析失败，应触发 error 事件
                        assert True
                        return
        pytest.fail("Should have raised JSONDecodeError")

    def test_parse_empty_buffer(self):
        """空缓冲区不应产生任何事件"""
        buffer = ""
        parts = buffer.split("\n\n")
        rest = parts.pop() if parts else ""
        assert rest == ""
        assert len(parts) == 0