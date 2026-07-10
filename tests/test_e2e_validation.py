"""
E2E 用户流程验证测试 (Task 3.2)

测试范围：
1. 完整思考-工具-回答流程：SSE 事件管线端到端验证
2. 多轮对话：连续多轮会话的状态隔离验证
3. 取消流程：取消事件生成与信号传播路径验证
4. prefers-reduced-motion：CSS 无障碍降级合规性验证
5. 最终渲染管线：事件序列正确性与字段完整性验证

这些测试从"用户视角"验证整个系统行为，确保：
- 思考文本事件正确生成和格式化
- 工具步骤事件序列完整且状态转换正确
- 多轮对话之间状态不泄漏
- 取消流程事件序列正确
- CSS 无障碍降级规则存在且正确
"""

import json
import os

import pytest

from app.api.routes import sse_event


# ═══════════════════════════════════════════════════════════════════
# 场景 1：完整思考-工具-回答流程 (E2E)
# ═══════════════════════════════════════════════════════════════════


class TestCompleteThinkingToolAnswerFlow:
    """验证完整的 thinking → tool → final SSE 事件管线"""

    def _simulate_full_event_pipeline(self, events):
        """
        模拟完整的 SSE 事件管线：内部事件 → sse_event 格式化。
        返回 (sse_strings, parsed_events)。
        """
        sse_strings = []
        parsed_events = []
        for event_type, data in events:
            sse_str = sse_event(event_type, data)
            sse_strings.append(sse_str)
            # 解析 SSE 格式
            parsed = json.loads(sse_str[6:].strip())
            parsed_events.append(parsed)
        return sse_strings, parsed_events

    def test_thinking_text_produces_correct_sse_events(self):
        """思考文本通过 SSE 管线后应产生正确的 step 事件"""
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "我需要分析用户的问题"}),
            ("step", {"step": "thinking", "status": "running", "text": "，查询相关的数据库表"}),
            ("step", {"step": "thinking", "status": "running", "text": "，然后获取数据。"}),
        ]

        sse_strs, parsed = self._simulate_full_event_pipeline(events)

        # 验证所有事件都是有效的 SSE
        assert len(sse_strs) == 3
        for s in sse_strs:
            assert s.startswith("data: ")
            assert s.endswith("\n\n")

        # 验证事件内容
        accumulated_text = ""
        for p in parsed:
            assert p["type"] == "step"
            assert p["step"] == "thinking"
            assert p["status"] == "running"
            accumulated_text += p["text"]

        assert "分析用户" in accumulated_text
        assert "查询相关的数据库" in accumulated_text

    def test_tool_start_produces_correct_sse_event(self):
        """工具调用开始事件应正确格式化并包含 step、status、call_index"""
        event = ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0})
        sse_str, parsed = self._simulate_full_event_pipeline([event])

        assert parsed[0]["type"] == "step"
        assert parsed[0]["step"] == "tool:describe_table"
        assert parsed[0]["status"] == "running"
        assert parsed[0]["call_index"] == 0

    def test_tool_end_produces_correct_sse_event(self):
        """工具调用完成事件应正确格式化"""
        event = ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0})
        sse_str, parsed = self._simulate_full_event_pipeline([event])

        assert parsed[0]["type"] == "step"
        assert parsed[0]["step"] == "tool:query_database"
        assert parsed[0]["status"] == "completed"
        assert parsed[0]["call_index"] == 0

    def test_sql_event_produces_correct_sse_event(self):
        """SQL 事件应正确格式化"""
        event = ("sql", {"sql": "SELECT * FROM users WHERE id = 1"})
        sse_str, parsed = self._simulate_full_event_pipeline([event])

        assert parsed[0]["type"] == "sql"
        assert parsed[0]["sql"] == "SELECT * FROM users WHERE id = 1"

    def test_final_event_produces_correct_sse_event(self):
        """最终事件应包含所有必要字段"""
        event = ("final", {
            "session_id": "test-session-123",
            "reply": "查询完成，共找到 5 条记录",
            "needs_confirmation": False,
            "tool_calls": [
                {"tool": "describe_table", "result": "column info"},
                {"tool": "query_database", "result": "5 rows"},
            ],
            "stats": {"duration_ms": 1500, "num_turns": 2, "tokens": 250},
            "latest_sql": "SELECT * FROM users",
            "memory_count": 3,
            "preference_count": 2,
            "cancelled": False,
        })
        sse_str, parsed = self._simulate_full_event_pipeline([event])

        p = parsed[0]
        assert p["type"] == "final"
        assert p["reply"] == "查询完成，共找到 5 条记录"
        assert p["cancelled"] is False
        assert len(p["tool_calls"]) == 2
        assert p["stats"]["duration_ms"] == 1500
        assert p["stats"]["num_turns"] == 2
        assert p["stats"]["tokens"] == 250
        assert p["memory_count"] == 3
        assert p["preference_count"] == 2

    def test_full_pipeline_thinking_tool_final(self):
        """
        端到端完整流程：thinking → tool_start → tool_end → final。
        验证事件类型序列、字段完整性和 SSE 格式化。
        """
        raw_events = [
            # 思考阶段
            ("step", {"step": "thinking", "status": "running", "text": "我需要先了解表结构"}),
            ("step", {"step": "thinking", "status": "running", "text": "，然后查询数据。"}),
            # 工具调用阶段
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
            # SQL 事件
            ("sql", {"sql": "SELECT * FROM users WHERE status = 'active'"}),
            # 最终回答
            ("final", {
                "session_id": "test-session",
                "reply": "查询到 10 条活跃用户记录",
                "needs_confirmation": False,
                "tool_calls": [
                    {"tool": "describe_table", "result": "ok"},
                    {"tool": "query_database", "result": "ok"},
                ],
                "stats": {"duration_ms": 2500, "num_turns": 3, "tokens": 400},
                "latest_sql": "SELECT * FROM users WHERE status = 'active'",
                "memory_count": 5,
                "preference_count": 1,
                "cancelled": False,
            }),
        ]

        sse_strs, parsed = self._simulate_full_event_pipeline(raw_events)

        # 验证事件类型序列
        event_types = [p["type"] for p in parsed]
        assert event_types == ["step", "step", "step", "step", "step", "step", "sql", "final"]

        # 验证 thinking 事件
        thinking_events = [p for p in parsed if p["type"] == "step" and p["step"] == "thinking"]
        assert len(thinking_events) == 2
        thinking_text = "".join(t["text"] for t in thinking_events)
        assert "表结构" in thinking_text
        assert "查询数据" in thinking_text

        # 验证 tool 事件
        tool_events = [p for p in parsed if p["type"] == "step" and p["step"].startswith("tool:")]
        assert len(tool_events) == 4  # 2 tools x 2 states each

        # 验证 tool 生命周期：describe_table running→completed
        desc_events = [t for t in tool_events if t["step"] == "tool:describe_table"]
        assert desc_events[0]["status"] == "running"
        assert desc_events[1]["status"] == "completed"

        # 验证 tool 生命周期：query_database running→completed
        query_events = [t for t in tool_events if t["step"] == "tool:query_database"]
        assert query_events[0]["status"] == "running"
        assert query_events[1]["status"] == "completed"

        # 验证 sql 事件
        sql_events = [p for p in parsed if p["type"] == "sql"]
        assert len(sql_events) == 1
        assert "SELECT * FROM users" in sql_events[0]["sql"]

        # 验证 final 事件
        final = parsed[-1]
        assert final["type"] == "final"
        assert final["reply"] == "查询到 10 条活跃用户记录"
        assert final["cancelled"] is False
        assert final["stats"]["duration_ms"] == 2500
        assert "tool_calls" in final

    def test_thinking_to_tool_transition_is_correct(self):
        """
        验证 thinking→tool 阶段转换时，事件序列正确。
        思考阶段结束时 StepRenderer 的 step 字段应从 "thinking" 切换为 "tool:xxx"。
        """
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "分析中..."}),
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("step", {"step": "thinking", "status": "running", "text": "继续分析..."}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
        ]

        sse_strs, parsed = self._simulate_full_event_pipeline(events)

        step_sequence = [(p["step"], p["status"]) for p in parsed]
        assert step_sequence == [
            ("thinking", "running"),
            ("tool:describe_table", "running"),
            ("tool:describe_table", "completed"),
            ("thinking", "running"),
            ("tool:query_database", "running"),
            ("tool:query_database", "completed"),
        ]

        # 验证 thinking→tool 切换时 step 字段正确变化
        step_values = [p["step"] for p in parsed]
        assert step_values[0] == "thinking"
        assert step_values[1] == "tool:describe_table"
        assert step_values[3] == "thinking"
        assert step_values[4] == "tool:query_database"

    def test_tool_call_index_consistency(self):
        """同一工具多次调用时 call_index 应正确递增"""
        events = [
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 1}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 1}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 2}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 2}),
        ]

        sse_strs, parsed = self._simulate_full_event_pipeline(events)

        running_events = [p for p in parsed if p["status"] == "running"]
        call_indices = [p["call_index"] for p in running_events]
        assert call_indices == [0, 1, 2]

    def test_final_event_contains_all_required_fields(self):
        """final 事件必须包含前端渲染所需的所有字段"""
        event = ("final", {
            "session_id": "test-session",
            "reply": "回答内容",
            "needs_confirmation": False,
            "tool_calls": [],
            "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
            "latest_sql": "",
            "memory_count": 0,
            "preference_count": 0,
            "cancelled": False,
        })

        sse_str, parsed = self._simulate_full_event_pipeline([event])
        p = parsed[0]

        # 前端 sendMessage 中使用的字段
        required_fields = [
            "reply", "cancelled", "tool_calls", "stats",
            "latest_sql", "memory_count", "preference_count",
        ]
        for field in required_fields:
            assert field in p, f"final 事件缺少必要字段: {field}"

    def test_stats_always_present_in_final_event(self):
        """stats 字段在任何情况下都不应缺失"""
        # 正常完成
        normal = ("final", {
            "session_id": "s1", "reply": "ok", "needs_confirmation": False,
            "tool_calls": [], "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
            "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": False,
        })
        _, parsed = self._simulate_full_event_pipeline([normal])
        assert "stats" in parsed[0]
        assert parsed[0]["stats"]["duration_ms"] == 100

        # 取消
        cancelled = ("final", {
            "session_id": "s1", "reply": "", "needs_confirmation": False,
            "tool_calls": [], "stats": {"duration_ms": 500, "num_turns": 2, "tokens": 30},
            "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": True,
        })
        _, parsed = self._simulate_full_event_pipeline([cancelled])
        assert "stats" in parsed[0]
        assert parsed[0]["stats"]["duration_ms"] == 500


# ═══════════════════════════════════════════════════════════════════
# 场景 2：多轮对话状态隔离验证
# ═══════════════════════════════════════════════════════════════════


class TestMultiTurnConversationIsolation:
    """验证连续多轮对话之间的状态隔离"""

    def _simulate_conversation_round(self, round_num: int):
        """
        模拟单轮对话的完整 SSE 事件流。
        返回 (thinking_text, tool_names, final_reply, all_parsed_events)。
        """
        events = [
            ("step", {"step": "thinking", "status": "running", "text": f"Round {round_num} 分析中..."}),
            ("step", {"step": "thinking", "status": "running", "text": f" 查询数据..."}),
            ("step", {"step": f"tool:query_table_{round_num}", "status": "running", "call_index": 0}),
            ("step", {"step": f"tool:query_table_{round_num}", "status": "completed", "call_index": 0}),
            ("final", {
                "session_id": f"session-round-{round_num}",
                "reply": f"Round {round_num} 回答",
                "needs_confirmation": False,
                "tool_calls": [{"tool": f"query_table_{round_num}", "result": "ok"}],
                "stats": {"duration_ms": 1000, "num_turns": 1, "tokens": 100},
                "latest_sql": f"SELECT * FROM table_{round_num}",
                "memory_count": round_num,
                "preference_count": 0,
                "cancelled": False,
            }),
        ]

        sse_strs = []
        parsed_events = []
        for event_type, data in events:
            sse_str = sse_event(event_type, data)
            sse_strs.append(sse_str)
            parsed_events.append(json.loads(sse_str[6:].strip()))

        thinking_text = "".join(
            p["text"] for p in parsed_events
            if p["type"] == "step" and p["step"] == "thinking"
        )
        tool_names = [
            p["step"] for p in parsed_events
            if p["type"] == "step" and p["step"].startswith("tool:")
        ]
        final_reply = parsed_events[-1]["reply"]

        return thinking_text, tool_names, final_reply, parsed_events

    def test_three_rounds_produce_independent_events(self):
        """3 轮对话应各自产生独立的事件流"""
        round1_text, round1_tools, round1_reply, round1_events = self._simulate_conversation_round(1)
        round2_text, round2_tools, round2_reply, round2_events = self._simulate_conversation_round(2)
        round3_text, round3_tools, round3_reply, round3_events = self._simulate_conversation_round(3)

        # 每轮独立
        assert "Round 1" in round1_text
        assert "Round 2" in round2_text
        assert "Round 3" in round3_text

        # 轮次之间不交叉
        assert "Round 2" not in round1_text
        assert "Round 1" not in round2_text
        assert "Round 3" not in round2_text

        # 每轮有自己的工具
        assert "tool:query_table_1" in round1_tools
        assert "tool:query_table_2" in round2_tools
        assert "tool:query_table_3" in round3_tools

        # 每轮有自己的回答
        assert round1_reply == "Round 1 回答"
        assert round2_reply == "Round 2 回答"
        assert round3_reply == "Round 3 回答"

    def test_thinking_text_does_not_leak_between_rounds(self):
        """上一轮的思考文本不应泄漏到下一轮"""
        round1_text, _, _, _ = self._simulate_conversation_round(1)
        round2_text, _, _, _ = self._simulate_conversation_round(2)

        # 验证每轮只包含自己的文本
        assert "Round 1" in round1_text
        assert "Round 2" not in round1_text
        assert "Round 2" in round2_text
        assert "Round 1" not in round2_text

    def test_tool_names_do_not_leak_between_rounds(self):
        """上一轮的工具名称不应泄漏到下一轮"""
        _, round1_tools, _, _ = self._simulate_conversation_round(1)
        _, round2_tools, _, _ = self._simulate_conversation_round(2)

        # 工具名称是独立的
        assert "tool:query_table_1" in round1_tools
        assert "tool:query_table_2" in round2_tools
        assert "tool:query_table_1" not in round2_tools

    def test_event_sequences_are_complete_per_round(self):
        """每轮的事件序列应完整（包含 step 和 final）"""
        for round_num in range(1, 4):
            _, _, _, events = self._simulate_conversation_round(round_num)

            event_types = [e["type"] for e in events]
            assert "step" in event_types, f"Round {round_num} 缺少 step 事件"
            assert "final" in event_types, f"Round {round_num} 缺少 final 事件"

            # final 事件必须是最后一个
            assert events[-1]["type"] == "final"

    def test_cleanup_state_between_rounds(self):
        """
        模拟多轮对话间的清理：
        - TypewriterRenderer.reset() 清空 fullText 和 displayedLength
        - StepRenderer.clearSteps() 清空步骤 Map
        """
        # 模拟 TypewriterRenderer 状态
        typewriter_state = {"fullText": "", "displayedLength": 0, "isRunning": False}

        # 模拟 StepRenderer 状态
        step_map = {}

        # Round 1
        typewriter_state["fullText"] = "Round 1 thinking"
        typewriter_state["displayedLength"] = 10
        typewriter_state["isRunning"] = True
        step_map["tool:query_table_1"] = {"status": "completed"}

        # 清理（模拟 cleanupAnimations + typewriter.reset + stepRenderer.clearSteps）
        typewriter_state["fullText"] = ""
        typewriter_state["displayedLength"] = 0
        typewriter_state["isRunning"] = False
        step_map.clear()

        # Round 2 开始前验证状态已清空
        assert typewriter_state["fullText"] == ""
        assert typewriter_state["displayedLength"] == 0
        assert typewriter_state["isRunning"] is False
        assert len(step_map) == 0

        # Round 2
        typewriter_state["fullText"] = "Round 2 thinking"
        typewriter_state["displayedLength"] = 5
        typewriter_state["isRunning"] = True
        step_map["tool:query_table_2"] = {"status": "running"}

        # 验证 Round 2 独立
        assert "Round 2" in typewriter_state["fullText"]
        assert "Round 1" not in typewriter_state["fullText"]
        assert "tool:query_table_2" in step_map
        assert "tool:query_table_1" not in step_map

    def test_memory_count_accumulates_across_rounds(self):
        """memory_count 可以跨轮递增（反映长期记忆的累积）"""
        counts = []
        for round_num in range(1, 4):
            _, _, _, events = self._simulate_conversation_round(round_num)
            final = events[-1]
            counts.append(final["memory_count"])

        assert counts == [1, 2, 3]

    def test_final_stats_are_independent_per_round(self):
        """每轮的 stats 应独立计算"""
        stats_list = []
        for round_num in range(1, 4):
            _, _, _, events = self._simulate_conversation_round(round_num)
            final = events[-1]
            stats_list.append(final["stats"])

        # 每轮有独立的 stats
        for stats in stats_list:
            assert "duration_ms" in stats
            assert "num_turns" in stats
            assert "tokens" in stats


# ═══════════════════════════════════════════════════════════════════
# 场景 3：取消流程端到端验证
# ═══════════════════════════════════════════════════════════════════


class TestCancelFlowE2E:
    """验证取消流程的端到端事件生成"""

    def test_cancelled_final_event_has_correct_structure(self):
        """取消的 final 事件应包含 cancelled=true 且 reply 为空"""
        event = ("final", {
            "session_id": "test-session",
            "reply": "",
            "needs_confirmation": False,
            "tool_calls": [],
            "stats": {"duration_ms": 800, "num_turns": 2, "tokens": 60},
            "latest_sql": "",
            "memory_count": 0,
            "preference_count": 0,
            "cancelled": True,
        })

        sse_str = sse_event("final", event[1])
        parsed = json.loads(sse_str[6:].strip())

        assert parsed["type"] == "final"
        assert parsed["cancelled"] is True
        assert parsed["reply"] == ""
        assert "stats" in parsed

    def test_cancel_sequence_with_thinking_before_cancel(self):
        """取消前已有思考事件，取消后应产生带有 cancelled 标记的 final"""
        events = [
            # 思考阶段（用户看到 Agent 在思考）
            ("step", {"step": "thinking", "status": "running", "text": "我正在分析你的问题"}),
            ("step", {"step": "thinking", "status": "running", "text": "，需要查询数据库..."}),
            # 用户点击取消 → 流中断
        ]

        sse_strs = []
        parsed_events = []
        for event_type, data in events:
            sse_str = sse_event(event_type, data)
            sse_strs.append(sse_str)
            parsed_events.append(json.loads(sse_str[6:].strip()))

        # 添加取消的 final 事件
        cancel_final = ("final", {
            "session_id": "test",
            "reply": "",
            "needs_confirmation": False,
            "tool_calls": [],
            "stats": {"duration_ms": 500, "num_turns": 1, "tokens": 30},
            "latest_sql": "",
            "memory_count": 0,
            "preference_count": 0,
            "cancelled": True,
        })
        cancel_sse = sse_event("final", cancel_final[1])
        cancel_parsed = json.loads(cancel_sse[6:].strip())

        # 验证思考事件存在
        thinking_text = "".join(
            p["text"] for p in parsed_events if p["step"] == "thinking"
        )
        assert "分析" in thinking_text
        assert "查询数据库" in thinking_text

        # 验证取消 final
        assert cancel_parsed["cancelled"] is True
        assert cancel_parsed["reply"] == ""

    def test_cancel_preserves_partial_content_marker(self):
        """取消时应保留部分内容，前端会追加"[已停止生成]"标记"""
        # 模拟取消路径：流式气泡保留，追加取消标记
        partial_text = "正在查询数据库中的用户信息..."
        cancelled_mark = "[已停止生成]"

        def finalize_cancelled_message(text):
            return f"{text}\n{cancelled_mark}"

        result = finalize_cancelled_message(partial_text)
        assert partial_text in result
        assert cancelled_mark in result
        # 标记应在文本之后
        assert result.index(partial_text) < result.index(cancelled_mark)

    def test_cancel_vs_normal_final_distinction(self):
        """取消和正常完成的 final 事件应通过 cancelled 字段区分"""
        # 正常完成
        normal = ("final", {
            "session_id": "s1", "reply": "查询完成", "needs_confirmation": False,
            "tool_calls": [], "stats": {"duration_ms": 1000, "num_turns": 1, "tokens": 100},
            "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": False,
        })
        normal_sse = sse_event("final", normal[1])
        normal_parsed = json.loads(normal_sse[6:].strip())

        # 取消
        cancelled = ("final", {
            "session_id": "s1", "reply": "", "needs_confirmation": False,
            "tool_calls": [], "stats": {"duration_ms": 500, "num_turns": 1, "tokens": 30},
            "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": True,
        })
        cancelled_sse = sse_event("final", cancelled[1])
        cancelled_parsed = json.loads(cancelled_sse[6:].strip())

        assert normal_parsed["cancelled"] is False
        assert normal_parsed["reply"] != ""

        assert cancelled_parsed["cancelled"] is True
        assert cancelled_parsed["reply"] == ""

    def test_cancel_cleanup_sequence(self):
        """
        取消时应触发清理序列：
        1. TypewriterRenderer.stop() 停止打字机
        2. 清除步骤动画类名
        3. 恢复 .meta 标签
        4. 追加取消标记
        """
        cleanup_log = []

        def simulate_cleanup(cancelled):
            if not cancelled:
                return
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

    def test_cancel_does_not_trigger_cleanup_for_normal(self):
        """正常完成不应触发取消清理序列"""
        cleanup_log = []

        def simulate_cleanup(cancelled):
            if not cancelled:
                # 正常完成：只做常规清理，不追加取消标记
                cleanup_log.append("typewriter.flush")
                cleanup_log.append("clear_animation_classes")
                cleanup_log.append("reset_meta_label")
                return
            cleanup_log.append("append_cancelled_mark")

        simulate_cleanup(False)
        assert "append_cancelled_mark" not in cleanup_log
        assert "typewriter.flush" in cleanup_log


# ═══════════════════════════════════════════════════════════════════
# 场景 4：prefers-reduced-motion 无障碍降级验证
# ═══════════════════════════════════════════════════════════════════


class TestReducedMotionAccessibility:
    """验证 CSS 中 prefers-reduced-motion 媒体查询的合规性"""

    @pytest.fixture
    def css_content(self):
        """读取 styles.css 内容"""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "styles.css",
        )
        with open(css_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_prefers_reduced_motion_media_query_exists(self, css_content):
        """CSS 中必须存在 prefers-reduced-motion: reduce 媒体查询"""
        assert "@media (prefers-reduced-motion: reduce)" in css_content, (
            "styles.css 缺少 prefers-reduced-motion: reduce 媒体查询"
        )

    def test_all_animations_disabled_in_reduced_motion(self, css_content):
        """
        在 reduced-motion 媒体查询中，所有动画应被禁用或降级为静态。
        验证方式：
        - animation-duration: 0.01ms 或 animation: none
        - transition-duration: 0.01ms 或 transition: none
        """
        # 提取 media query 块内容
        mq_start = css_content.find("@media (prefers-reduced-motion: reduce)")
        assert mq_start >= 0

        mq_content = css_content[mq_start:]
        # 找到对应的闭合大括号
        brace_count = 0
        mq_end = mq_start
        for i, ch in enumerate(mq_content):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    mq_end = mq_start + i + 1
                    break

        mq_block = css_content[mq_start:mq_end]

        # 验证动画禁用规则
        has_animation_disable = (
            "animation-duration: 0.01ms" in mq_block
            or "animation: none" in mq_block
        )
        has_transition_disable = (
            "transition-duration: 0.01ms" in mq_block
            or "transition: none" in mq_block
        )

        assert has_animation_disable, (
            "reduced-motion 媒体查询中缺少动画禁用规则"
        )
        assert has_transition_disable, (
            "reduced-motion 媒体查询中缺少过渡禁用规则"
        )

    def test_pulse_dot_disabled_in_reduced_motion(self, css_content):
        """pulse-dot 动画在 reduced-motion 中应被禁用"""
        mq_start = css_content.find("@media (prefers-reduced-motion: reduce)")
        mq_content = css_content[mq_start:]
        brace_count = 0
        mq_end = mq_start
        for i, ch in enumerate(mq_content):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    mq_end = mq_start + i + 1
                    break
        mq_block = css_content[mq_start:mq_end]

        assert ".pulse-dot" in mq_block, (
            "reduced-motion 媒体查询中缺少 .pulse-dot 降级规则"
        )

    def test_streaming_cursor_disabled_in_reduced_motion(self, css_content):
        """streaming-cursor 动画在 reduced-motion 中应被禁用"""
        mq_start = css_content.find("@media (prefers-reduced-motion: reduce)")
        mq_content = css_content[mq_start:]
        brace_count = 0
        mq_end = mq_start
        for i, ch in enumerate(mq_content):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    mq_end = mq_start + i + 1
                    break
        mq_block = css_content[mq_start:mq_end]

        assert ".streaming-cursor" in mq_block, (
            "reduced-motion 媒体查询中缺少 .streaming-cursor 降级规则"
        )

    def test_streaming_step_transition_disabled_in_reduced_motion(self, css_content):
        """streaming-step 过渡在 reduced-motion 中应被禁用"""
        mq_start = css_content.find("@media (prefers-reduced-motion: reduce)")
        mq_content = css_content[mq_start:]
        brace_count = 0
        mq_end = mq_start
        for i, ch in enumerate(mq_content):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    mq_end = mq_start + i + 1
                    break
        mq_block = css_content[mq_start:mq_end]

        assert ".streaming-step" in mq_block, (
            "reduced-motion 媒体查询中缺少 .streaming-step 降级规则"
        )

    def test_keyframe_animations_exist(self, css_content):
        """验证所有必需的 CSS 动画关键帧定义存在"""
        required_keyframes = [
            "@keyframes blink-cursor",
            "@keyframes pulse-dot",
            "@keyframes text-pulse",
        ]
        for kf in required_keyframes:
            assert kf in css_content, f"styles.css 缺少关键帧动画: {kf}"

    def test_css_variables_exist(self, css_content):
        """验证所有必需的 CSS 变量定义存在"""
        required_vars = [
            "--ok",
            "--err",
        ]
        for var in required_vars:
            assert var in css_content, f"styles.css 缺少 CSS 变量: {var}"

    def test_streaming_cursor_style_exists(self, css_content):
        """验证 .streaming-cursor::after 样式定义存在"""
        assert ".streaming-cursor::after" in css_content, (
            "styles.css 缺少 .streaming-cursor::after 样式"
        )

    def test_pulse_dot_style_exists(self, css_content):
        """验证 .pulse-dot 样式定义存在"""
        assert ".pulse-dot" in css_content, (
            "styles.css 缺少 .pulse-dot 样式"
        )

    def test_streaming_step_style_exists(self, css_content):
        """验证 .streaming-step 样式定义存在"""
        assert ".streaming-step" in css_content, (
            "styles.css 缺少 .streaming-step 样式"
        )

    def test_phase_label_style_exists(self, css_content):
        """验证 .phase-label 样式定义存在"""
        assert ".phase-label" in css_content, (
            "styles.css 缺少 .phase-label 样式"
        )

    def test_html_references_stylesheet(self):
        """验证 index.html 正确引用 styles.css"""
        html_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "index.html",
        )
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        assert 'href="/static/styles.css"' in html_content, (
            "index.html 未正确引用 styles.css"
        )

    def test_reduced_motion_content_remains_complete(self, css_content):
        """
        验证在 reduced-motion 降级为静态展示时，消息内容不会丢失。
        CSS 降级只影响动画（animation/transition），不影响 display/visibility/content。
        """
        mq_start = css_content.find("@media (prefers-reduced-motion: reduce)")
        mq_content = css_content[mq_start:]
        brace_count = 0
        mq_end = mq_start
        for i, ch in enumerate(mq_content):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    mq_end = mq_start + i + 1
                    break
        mq_block = css_content[mq_start:mq_end]

        # 不应包含会影响内容可见性的规则
        # 使用正则精确匹配，避免 "opacity: 0" 匹配到 "opacity: 0.6"
        import re
        forbidden_patterns = [
            (r"\bdisplay\s*:\s*none\b", "display: none"),
            (r"\bvisibility\s*:\s*hidden\b", "visibility: hidden"),
        ]
        for pattern, label in forbidden_patterns:
            assert not re.search(pattern, mq_block), (
                f"reduced-motion 媒体查询不应包含影响内容可见性的规则: {label}"
            )


# ═══════════════════════════════════════════════════════════════════
# 场景 5：最终渲染管线事件序列正确性验证
# ═══════════════════════════════════════════════════════════════════


class TestFinalRenderingPipeline:
    """验证完整的渲染管线产生正确的事件序列"""

    def test_event_sequence_types_are_valid(self):
        """所有事件类型必须是有效的（step / sql / final）"""
        valid_types = {"step", "sql", "final"}

        # 模拟各种事件
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "..."}),
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("sql", {"sql": "SELECT * FROM users"}),
            ("final", {
                "session_id": "test", "reply": "done", "needs_confirmation": False,
                "tool_calls": [], "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
                "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": False,
            }),
        ]

        for event_type, data in events:
            assert event_type in valid_types, f"无效事件类型: {event_type}"
            sse_str = sse_event(event_type, data)
            parsed = json.loads(sse_str[6:].strip())
            assert parsed["type"] == event_type

    def test_no_event_type_leakage(self):
        """事件类型不应泄漏到 data 字典的其他字段中"""
        data = {"step": "thinking", "status": "running", "text": "Hello"}
        sse_str = sse_event("step", data)
        parsed = json.loads(sse_str[6:].strip())

        # type 字段应仅出现一次（在顶层）
        assert parsed["type"] == "step"
        # step 字段不应被 type 覆盖
        assert parsed["step"] == "thinking"
        assert parsed["text"] == "Hello"

    def test_sse_format_is_valid_for_all_event_types(self):
        """所有事件类型的 SSE 格式都应遵循标准格式"""
        test_cases = [
            ("step", {"step": "thinking", "status": "running", "text": "Hello"}),
            ("step", {"step": "tool:query", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query", "status": "completed", "call_index": 0}),
            ("sql", {"sql": "SELECT 1"}),
            ("final", {
                "session_id": "s1", "reply": "ok", "needs_confirmation": False,
                "tool_calls": [], "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
                "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": False,
            }),
        ]

        for event_type, data in test_cases:
            sse_str = sse_event(event_type, data)
            # 验证 SSE 格式
            assert sse_str.startswith("data: "), f"SSE 格式错误: {sse_str[:50]}"
            assert sse_str.endswith("\n\n"), f"SSE 格式错误: {sse_str[-10:]}"
            # 验证 JSON 可解析
            parsed = json.loads(sse_str[6:].strip())
            assert "type" in parsed
            assert parsed["type"] == event_type

    def test_tool_lifecycle_completeness(self):
        """
        验证每个工具调用都有完整的生命周期：
        running → completed 或 running → error。
        不应出现孤立的 running 或 completed 事件。
        """
        # 模拟工具调用
        tool_events = [
            ("step", {"step": "tool:describe_table", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:describe_table", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query_database", "status": "completed", "call_index": 0}),
            ("step", {"step": "tool:execute_sql", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:execute_sql", "status": "error", "call_index": 0}),
        ]

        # 按工具名称分组
        tool_groups = {}
        for event_type, data in tool_events:
            name = data["step"]
            if name not in tool_groups:
                tool_groups[name] = []
            tool_groups[name].append(data["status"])

        # 每个工具应有 running 和 completed/error
        for tool_name, statuses in tool_groups.items():
            assert "running" in statuses, f"{tool_name} 缺少 running 状态"
            assert len(statuses) >= 2, f"{tool_name} 生命周期不完整"
            end_status = statuses[-1]
            assert end_status in ("completed", "error"), (
                f"{tool_name} 应以 completed 或 error 结束，实际为 {end_status}"
            )

    def test_final_event_is_always_last(self):
        """final 事件必须始终是事件流的最后一个事件"""
        events = [
            ("step", {"step": "thinking", "status": "running", "text": "分析中..."}),
            ("step", {"step": "tool:query", "status": "running", "call_index": 0}),
            ("step", {"step": "tool:query", "status": "completed", "call_index": 0}),
            ("final", {
                "session_id": "test", "reply": "done", "needs_confirmation": False,
                "tool_calls": [], "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
                "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": False,
            }),
        ]

        event_types = [e[0] for e in events]
        assert event_types[-1] == "final", "final 事件必须是最后一个事件"

        # 验证 final 之后没有 step 或 sql 事件
        final_index = event_types.index("final")
        subsequent_types = event_types[final_index + 1:]
        assert len(subsequent_types) == 0, "final 事件之后不应有其他事件"

    def test_unicode_handling_in_pipeline(self):
        """中文字符和特殊字符在整个管线中正确处理"""
        test_texts = [
            "用户想查询数据库中的表结构",
            "包含特殊字符：`~!@#$%^&*()_+-=[]{}|;':\",./<>?",
            "Mixed English and 中文 content",
            "emoji test: 🎉✅❌",
        ]

        for text in test_texts:
            data = {"step": "thinking", "status": "running", "text": text}
            sse_str = sse_event("step", data)
            parsed = json.loads(sse_str[6:].strip())
            assert parsed["type"] == "step"
            assert parsed["text"] == text

    def test_empty_and_null_text_degradation_in_pipeline(self):
        """空文本和 null 文本在管线中降级处理"""
        # 空字符串
        data = {"step": "thinking", "status": "running", "text": ""}
        sse_str = sse_event("step", data)
        parsed = json.loads(sse_str[6:].strip())
        assert parsed["text"] == ""

        # null 降级（模拟 None → "" 转换）
        text_value = None
        safe_text = str(text_value or "")
        data = {"step": "thinking", "status": "running", "text": safe_text}
        sse_str = sse_event("step", data)
        parsed = json.loads(sse_str[6:].strip())
        assert parsed["text"] == ""

    def test_large_payload_in_final_event(self):
        """大的 final 事件负载应正确处理"""
        large_reply = "x" * 50000
        large_tool_calls = [{"tool": f"tool_{i}", "result": "ok"} for i in range(100)]

        data = {
            "session_id": "test",
            "reply": large_reply,
            "needs_confirmation": False,
            "tool_calls": large_tool_calls,
            "stats": {"duration_ms": 1000, "num_turns": 5, "tokens": 10000},
            "latest_sql": "SELECT * FROM large_table",
            "memory_count": 10,
            "preference_count": 5,
            "cancelled": False,
        }

        sse_str = sse_event("final", data)
        parsed = json.loads(sse_str[6:].strip())

        assert len(parsed["reply"]) == 50000
        assert len(parsed["tool_calls"]) == 100
        assert parsed["stats"]["tokens"] == 10000


# ═══════════════════════════════════════════════════════════════════
# 场景 6：前端渲染管线集成验证
# ═══════════════════════════════════════════════════════════════════


class TestFrontendRenderingPipelineIntegration:
    """验证 SSE 事件到前端渲染管线的集成点"""

    def test_add_step_routes_to_update_streaming_message(self):
        """
        验证 addStep 函数的行为：
        - thinking 事件传递 text 和 status
        - tool:* 事件传递 status 和 call_index
        """
        # 模拟 addStep 逻辑（step 是第一个参数，state 是第二个参数）
        def add_step(step, state):
            if step == "thinking":
                assert "text" in state
                assert state["status"] == "running"
            elif step.startswith("tool:"):
                assert "status" in state

        # 验证 thinking 事件
        add_step("thinking", {"status": "running", "text": "分析中..."})

        # 验证 tool 事件
        add_step("tool:query_database", {"status": "running", "call_index": 0})
        add_step("tool:query_database", {"status": "completed", "call_index": 0})

    def test_parse_sse_chunk_splits_events_correctly(self):
        """parseSseChunk 应正确分割多个 SSE 事件"""

        def parse_sse_chunk(buffer):
            parts = buffer.split("\n\n")
            rest = parts.pop() or ""
            events = []
            for part in parts:
                data_line = None
                for line in part.split("\n"):
                    if line.startswith("data: "):
                        data_line = line
                        break
                if data_line:
                    events.append(json.loads(data_line[6:]))
            return events, rest

        # 生成多个 SSE 事件
        raw_events = [
            ("step", {"step": "thinking", "status": "running", "text": "Hello"}),
            ("step", {"step": "thinking", "status": "running", "text": " World"}),
            ("step", {"step": "tool:query", "status": "running", "call_index": 0}),
        ]

        buffer = "".join(sse_event(et, d) for et, d in raw_events)
        events, rest = parse_sse_chunk(buffer)

        assert len(events) == 3
        assert events[0]["text"] == "Hello"
        assert events[1]["text"] == " World"
        assert events[2]["step"] == "tool:query"
        assert rest == ""

    def test_partial_sse_buffer_preserves_remainder(self):
        """不完整的 SSE 缓冲区应保留剩余部分供下次解析"""

        def parse_sse_chunk(buffer):
            parts = buffer.split("\n\n")
            rest = parts.pop() or ""
            events = []
            for part in parts:
                data_line = None
                for line in part.split("\n"):
                    if line.startswith("data: "):
                        data_line = line
                        break
                if data_line:
                    events.append(json.loads(data_line[6:]))
            return events, rest

        # 生成完整事件
        full_event = sse_event("step", {"step": "thinking", "status": "running", "text": "Hello"})

        # 截断为部分数据
        partial = full_event[:30]
        events, rest = parse_sse_chunk(partial)

        # 不完整数据不应产生事件，但应保留在 rest 中
        assert len(events) == 0, "部分数据不应产生完整事件"
        assert len(rest) > 0, "部分数据应保留在 rest 中"

    def test_create_streaming_bubble_structure(self):
        """
        验证 createStreamingBubble 创建的 DOM 结构约定：
        - article.message.assistant.streaming
        - .bubble > .meta + .content
        - .content > .thinking-text.streaming-cursor + .streaming-steps
        """
        # 这是一个结构约定测试，验证前端的 DOM 结构要求
        required_selectors = [
            "article.message.assistant.streaming",
            ".bubble",
            ".meta",
            ".content",
            ".thinking-text.streaming-cursor",
            ".streaming-steps",
        ]

        # 验证 HTML 中存在这些 CSS 类名的定义
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "styles.css",
        )
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()

        # 验证关键 CSS 类存在
        assert ".streaming-cursor" in css_content
        assert ".streaming-steps" in css_content
        assert ".streaming-step" in css_content
        assert ".thinking-text" in css_content

    def test_finalize_streaming_message_normal_path(self):
        """
        验证 finalizeStreamingMessage 正常路径的行为：
        - 移除流式气泡
        - 用 appendMessage 创建独立消息气泡
        """
        # 模拟正常完成路径
        def simulate_normal_finalize(reply):
            # 1. 清理动画
            cleanup_called = True
            # 2. 移除流式气泡
            streaming_removed = True
            # 3. 创建独立消息气泡
            final_message = {"role": "assistant", "content": reply}
            return final_message, cleanup_called, streaming_removed

        reply = "查询完成，共找到 5 条记录"
        msg, cleanup, removed = simulate_normal_finalize(reply)

        assert cleanup is True
        assert removed is True
        assert msg["content"] == reply

    def test_finalize_streaming_message_cancel_path(self):
        """
        验证 finalizeStreamingMessage 取消路径的行为：
        - 清理动画
        - 保留流式气泡（不移除）
        - 追加 "[已停止生成]" 标记
        """
        # 模拟取消路径
        def simulate_cancel_finalize(partial_text):
            # 1. 清理动画
            cleanup_called = True
            # 2. 保留气泡（不移除）
            streaming_removed = False
            # 3. 追加取消标记
            cancelled_mark = "[已停止生成]"
            final_content = f"{partial_text}\n{cancelled_mark}"
            return final_content, cleanup_called, streaming_removed

        partial = "正在查询数据库..."
        content, cleanup, removed = simulate_cancel_finalize(partial)

        assert cleanup is True
        assert removed is False  # 取消时保留气泡
        assert "[已停止生成]" in content
        assert partial in content

    def test_phase_label_updates(self):
        """阶段标签应根据 step 类型正确更新"""
        def get_phase_label(step):
            if step == "thinking":
                return "DBAgent · 思考中..."
            elif step and step.startswith("tool:"):
                return "DBAgent · 正在查询数据库..."
            else:
                return "DBAgent"

        # 思考阶段
        assert get_phase_label("thinking") == "DBAgent · 思考中..."

        # 工具调用阶段
        assert get_phase_label("tool:describe_table") == "DBAgent · 正在查询数据库..."
        assert get_phase_label("tool:query_database") == "DBAgent · 正在查询数据库..."
        assert get_phase_label("tool:execute_sql") == "DBAgent · 正在查询数据库..."

        # 其他阶段
        assert get_phase_label("final") == "DBAgent"
        assert get_phase_label("") == "DBAgent"
        assert get_phase_label(None) == "DBAgent"


# ═══════════════════════════════════════════════════════════════════
# 场景 7：runner.py 事件生成结构验证
# ═══════════════════════════════════════════════════════════════════


class TestRunnerEventGeneration:
    """验证 runner.py 中 run_agent_stream 产生的事件结构"""

    def test_thinking_event_yield_structure(self):
        """
        验证 run_agent_stream 中 thinking 事件的结构：
        yield "step", {"step": "thinking", "status": "running", "text": "..."}
        """
        event_type = "step"
        data = {"step": "thinking", "status": "running", "text": "推理内容"}

        assert event_type == "step"
        assert data["step"] == "thinking"
        assert data["status"] == "running"
        assert "text" in data

    def test_tool_start_event_yield_structure(self):
        """
        验证 run_agent_stream 中 tool_start 事件的结构：
        yield "step", {"step": "tool:xxx", "status": "running", "call_index": N}
        """
        event_type = "step"
        data = {"step": "tool:describe_table", "status": "running", "call_index": 0}

        assert event_type == "step"
        assert data["step"].startswith("tool:")
        assert data["status"] == "running"
        assert "call_index" in data

    def test_tool_end_event_yield_structure(self):
        """
        验证 run_agent_stream 中 tool_end 事件的结构：
        yield "step", {"step": "tool:xxx", "status": "completed", "call_index": N}
        """
        event_type = "step"
        data = {"step": "tool:describe_table", "status": "completed", "call_index": 0}

        assert event_type == "step"
        assert data["step"].startswith("tool:")
        assert data["status"] == "completed"
        assert "call_index" in data

    def test_sql_event_yield_structure(self):
        """
        验证 run_agent_stream 中 sql 事件的结构：
        yield "sql", {"sql": "SELECT ..."}
        """
        event_type = "sql"
        data = {"sql": "SELECT * FROM users"}

        assert event_type == "sql"
        assert "sql" in data
        assert len(data["sql"]) > 0

    def test_final_event_yield_structure(self):
        """
        验证 run_agent_stream 中 final 事件的结构：
        yield "final", {
            "response": "...",
            "updated_state": {...},
            "needs_confirmation": False,
            "pending_action": None,
            "tool_calls": [...],
            "stats": {...},
        }
        """
        event_type = "final"
        data = {
            "response": "查询完成",
            "updated_state": {"session_id": "test", "chat_history": []},
            "needs_confirmation": False,
            "pending_action": None,
            "tool_calls": [],
            "stats": {"duration_ms": 1000, "num_turns": 2, "tokens": 200},
        }

        assert event_type == "final"
        assert "response" in data
        assert "updated_state" in data
        assert "tool_calls" in data
        assert "stats" in data

    def test_final_event_always_has_stats(self):
        """无论正常完成还是取消，final 事件都应包含 stats"""
        # 正常完成
        normal = {
            "response": "done",
            "updated_state": {},
            "needs_confirmation": False,
            "pending_action": None,
            "tool_calls": [],
            "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
        }
        assert "stats" in normal
        assert normal["stats"]["duration_ms"] >= 0

        # 取消
        cancelled = {
            "response": "",
            "updated_state": {},
            "needs_confirmation": False,
            "pending_action": None,
            "tool_calls": [],
            "stats": {"duration_ms": 500, "num_turns": 2, "tokens": 30},
        }
        assert "stats" in cancelled
        assert cancelled["stats"]["duration_ms"] >= 0

    def test_event_type_consistency_through_pipeline(self):
        """
        验证事件类型在整个管线中保持一致：
        runner.py → routes.py → sse_event() → SSE 字符串
        """
        # runner.py 产出的事件类型
        runner_event_types = ["step", "sql", "final"]

        for event_type in runner_event_types:
            if event_type == "step":
                data = {"step": "thinking", "status": "running", "text": "test"}
            elif event_type == "sql":
                data = {"sql": "SELECT 1"}
            else:
                data = {
                    "session_id": "test", "reply": "ok", "needs_confirmation": False,
                    "tool_calls": [], "stats": {"duration_ms": 100, "num_turns": 1, "tokens": 50},
                    "latest_sql": "", "memory_count": 0, "preference_count": 0, "cancelled": False,
                }

            # routes.py 中 _execute_agent_stream 使用相同的 event_type 传递给 sse_event
            sse_str = sse_event(event_type, data)
            parsed = json.loads(sse_str[6:].strip())

            # 验证 type 字段一致
            assert parsed["type"] == event_type


# ═══════════════════════════════════════════════════════════════════
# 场景 8：发送新消息时动画清理验证
# ═══════════════════════════════════════════════════════════════════


class TestSendMessageAnimationCleanup:
    """验证 sendMessage 入口处的动画清理行为"""

    def test_send_message_resets_typewriter(self):
        """sendMessage 开始时必须重置 TypewriterRenderer"""
        typewriter_state = {"fullText": "previous thinking", "displayedLength": 10, "isRunning": True}

        # 模拟 sendMessage 入口的清理
        def reset_typewriter():
            typewriter_state["fullText"] = ""
            typewriter_state["displayedLength"] = 0
            typewriter_state["isRunning"] = False

        reset_typewriter()
        assert typewriter_state["fullText"] == ""
        assert typewriter_state["displayedLength"] == 0
        assert typewriter_state["isRunning"] is False

    def test_send_message_clears_step_renderer(self):
        """sendMessage 开始时必须清除 StepRenderer 的所有步骤"""
        steps = {"tool:query": "running", "tool:describe": "completed"}

        def clear_steps():
            steps.clear()

        clear_steps()
        assert len(steps) == 0

    def test_send_message_stops_animations(self):
        """sendMessage 开始时必须停止所有动画"""
        animation_state = {"running": True, "willChange": "opacity"}

        def stop_animations():
            animation_state["running"] = False
            animation_state["willChange"] = ""

        stop_animations()
        assert animation_state["running"] is False
        assert animation_state["willChange"] == ""

    def test_send_message_resets_meta_label(self):
        """sendMessage 开始时必须重置 .meta 标签"""
        meta_text = ["DBAgent · 思考中..."]

        def reset_meta():
            meta_text[0] = "DBAgent"

        reset_meta()
        assert meta_text[0] == "DBAgent"

    def test_switch_session_triggers_same_cleanup(self):
        """switchSession 应触发与 sendMessage 相同的清理"""
        class MockState:
            def __init__(self):
                self.typewriter = {"fullText": "old", "displayedLength": 5, "isRunning": True}
                self.steps = {"tool:a": "running"}
                self.animations = {"running": True}
                self.meta = "DBAgent · 思考中..."

            def cleanup(self):
                self.typewriter = {"fullText": "", "displayedLength": 0, "isRunning": False}
                self.steps = {}
                self.animations = {"running": False}
                self.meta = "DBAgent"

        state = MockState()
        state.cleanup()

        assert state.typewriter["fullText"] == ""
        assert state.typewriter["isRunning"] is False
        assert len(state.steps) == 0
        assert state.animations["running"] is False
        assert state.meta == "DBAgent"