"""
build_context 单元测试 — 偏好信息注入验证

测试覆盖：
- 非空偏好生成正确段落格式
- 空偏好不生成段落
- 与长期记忆并列顺序
- 偏好信息格式正确性
"""

import pytest

from app.agent.context import build_context


class TestBuildContextPreferences:
    """测试 build_context() 中偏好信息注入逻辑（需求 3.1, 3.2, 3.3）"""

    # ── 需求 3.1：非空偏好注入 Agent 上下文 ──

    def test_preferences_injected_when_non_empty(self):
        """当 _preferences 非空时，应生成 [操作记忆 — 查询偏好] 段落"""
        session_state = {
            "_preferences": [
                {
                    "database_name": "test_db",
                    "table_name": "users",
                    "query_count": 5,
                    "schema_id": 100,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "[操作记忆 — 查询偏好]" in result
        assert "- test_db.users（查询 5 次）" in result

    def test_preferences_multiple_entries(self):
        """当有多个偏好记录时，每行一条格式正确"""
        session_state = {
            "_preferences": [
                {
                    "database_name": "db_a",
                    "table_name": "orders",
                    "query_count": 10,
                    "schema_id": 200,
                },
                {
                    "database_name": "db_b",
                    "table_name": "products",
                    "query_count": 3,
                    "schema_id": 300,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "[操作记忆 — 查询偏好]" in result
        assert "- db_a.orders（查询 10 次）" in result
        assert "- db_b.products（查询 3 次）" in result

    def test_preferences_single_entry(self):
        """单条偏好记录的格式验证"""
        session_state = {
            "_preferences": [
                {
                    "database_name": "prod_db",
                    "table_name": "inventory",
                    "query_count": 1,
                    "schema_id": 42,
                },
            ],
        }
        result, _ = build_context(session_state)
        lines = result.split("\n")
        pref_lines = [l for l in lines if "操作记忆" in l or "prod_db" in l]
        assert len(pref_lines) == 2
        assert pref_lines[0] == "[操作记忆 — 查询偏好]"
        assert pref_lines[1] == "- prod_db.inventory（查询 1 次）"

    # ── 需求 3.3：空偏好不注入 ──

    def test_no_preference_section_when_empty_list(self):
        """_preferences 为空列表时，不添加偏好段落"""
        session_state = {
            "_preferences": [],
        }
        result, _ = build_context(session_state)
        assert "[操作记忆 — 查询偏好]" not in result

    def test_no_preference_section_when_missing(self):
        """session_state 中没有 _preferences 字段时，不添加偏好段落"""
        session_state = {}
        result, _ = build_context(session_state)
        assert "[操作记忆 — 查询偏好]" not in result

    def test_no_preference_section_when_none(self):
        """_preferences 为 None 时，不添加偏好段落（防御性）"""
        session_state = {
            "_preferences": None,
        }
        result, _ = build_context(session_state)
        assert "[操作记忆 — 查询偏好]" not in result

    # ── 需求 3.2：与长期记忆并列展示 ──

    def test_preferences_after_long_term_memory(self):
        """偏好段落应位于长期记忆段落之后"""
        session_state = {
            "_memories": [
                {"abstract": "用户关注告警领域"},
            ],
            "_preferences": [
                {
                    "database_name": "test_db",
                    "table_name": "users",
                    "query_count": 5,
                    "schema_id": 100,
                },
            ],
        }
        result, _ = build_context(session_state)
        long_term_idx = result.find("[长期记忆 — 来自之前的对话]")
        pref_idx = result.find("[操作记忆 — 查询偏好]")
        assert long_term_idx >= 0, "应有长期记忆段落"
        assert pref_idx >= 0, "应有偏好段落"
        assert long_term_idx < pref_idx, (
            f"偏好段落应在长期记忆之后，但长期记忆在 {long_term_idx}，偏好段落在 {pref_idx}"
        )

    def test_preferences_parallel_to_memories_both_present(self):
        """当长期记忆和偏好同时存在时，两者并列展示"""
        session_state = {
            "_memories": [
                {"abstract": "用户关注告警领域"},
                {"abstract": "用户经常查询订单数据"},
            ],
            "_preferences": [
                {
                    "database_name": "prod_db",
                    "table_name": "orders",
                    "query_count": 8,
                    "schema_id": 500,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "[长期记忆 — 来自之前的对话]" in result
        assert "[操作记忆 — 查询偏好]" in result
        assert "- 用户关注告警领域" in result
        assert "- 用户经常查询订单数据" in result
        assert "- prod_db.orders（查询 8 次）" in result

    def test_preferences_without_memories(self):
        """当只有偏好没有长期记忆时，偏好段落正常展示"""
        session_state = {
            "_preferences": [
                {
                    "database_name": "db_x",
                    "table_name": "table_y",
                    "query_count": 2,
                    "schema_id": 999,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "[长期记忆 — 来自之前的对话]" not in result
        assert "[操作记忆 — 查询偏好]" in result
        assert "- db_x.table_y（查询 2 次）" in result

    def test_memories_without_preferences(self):
        """当只有长期记忆没有偏好时，只展示长期记忆"""
        session_state = {
            "_memories": [
                {"abstract": "用户关注告警领域"},
            ],
        }
        result, _ = build_context(session_state)
        assert "[长期记忆 — 来自之前的对话]" in result
        assert "[操作记忆 — 查询偏好]" not in result

    def test_empty_state_returns_empty_string(self):
        """空 session_state 返回空字符串"""
        result, _ = build_context({})
        assert result == ""

    # ── 格式边界测试 ──

    def test_preference_format_with_special_chars(self):
        """数据库名和表名中包含特殊字符时格式正确"""
        session_state = {
            "_preferences": [
                {
                    "database_name": "test-db_v2",
                    "table_name": "user_orders",
                    "query_count": 7,
                    "schema_id": 1,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "- test-db_v2.user_orders（查询 7 次）" in result

    def test_preference_query_count_large(self):
        """大查询次数的格式正确"""
        session_state = {
            "_preferences": [
                {
                    "database_name": "db",
                    "table_name": "tbl",
                    "query_count": 99999,
                    "schema_id": 1,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "- db.tbl（查询 99999 次）" in result

    def test_context_includes_other_sections_with_preferences(self):
        """偏好段落与其它上下文段落共存"""
        session_state = {
            "summary": "之前讨论了告警系统",
            "chat_history": [
                {"role": "user", "content": "查一下用户表"},
                {"role": "assistant", "content": "好的，正在查询..."},
            ],
            "selected_database": {"schemaName": "my_db"},
            "selected_schema_id": 10,
            "_memories": [
                {"abstract": "用户经常查询告警数据"},
            ],
            "_preferences": [
                {
                    "database_name": "my_db",
                    "table_name": "users",
                    "query_count": 3,
                    "schema_id": 10,
                },
            ],
        }
        result, _ = build_context(session_state)
        assert "[之前的对话摘要]" in result
        assert "[对话历史]" in result
        assert "当前选择的数据库: my_db" in result
        assert "[长期记忆 — 来自之前的对话]" in result
        assert "[操作记忆 — 查询偏好]" in result
        assert "- my_db.users（查询 3 次）" in result


# New tests for build_context token estimation return type
class TestBuildContextTokenEstimation:
    """Test build_context() token estimation in return value."""

    def test_returns_tuple_of_str_and_dict(self):
        """build_context 返回 (str, dict) 元组"""
        result = build_context({})
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], dict)

    def test_ctx_tokens_has_8_section_keys(self):
        """ctx_tokens 包含 8 个上下文段键（排除 _method 标记键）"""
        _, tokens = build_context({"summary": "test", "chat_history": [{"role": "user", "content": "hello"}]})
        section_keys = {k for k in tokens if k != "_method"}
        assert len(section_keys) == 8, f"Expected 8 section keys, got {len(section_keys)}: {sorted(section_keys)}"

    def test_ctx_tokens_keys_match_context_sections(self):
        """ctx_tokens 键名与 8 段上下文名称一致（排除 _method）"""
        expected_keys = {
            "summary",
            "chat_history",
            "selected_database",
            "memories",
            "rag_reference",
            "preferences",
            "hdc_context",
            "sql_memories",
        }
        _, tokens = build_context({})
        section_keys = {k for k in tokens if k != "_method"}
        assert section_keys == expected_keys

    def test_ctx_tokens_values_are_positive_integers(self):
        """ctx_tokens 值全部为正整数（排除 _method 字符串标记）"""
        _, tokens = build_context({})
        for key, val in tokens.items():
            if key == "_method":
                continue
            assert isinstance(val, int), f"{key} should be int, got {type(val)}: {val}"
            assert val >= 0, f"{key} should be >= 0, got {val}"

    def test_ctx_tokens_with_content(self):
        """当上下文有内容时，token 估算值 > 0"""
        state = {
            "summary": "之前讨论了订单查询系统",
            "chat_history": [
                {"role": "user", "content": "查一下最近的订单"},
                {"role": "assistant", "content": "好的，正在为您查询..."},
            ],
            "selected_database": {"schemaName": "test_db"},
            "selected_schema_id": 42,
        }
        _, tokens = build_context(state)
        assert tokens["summary"] > 0, "summary 非空应有 token"
        assert tokens["chat_history"] > 0, "chat_history 非空应有 token"
        assert tokens["selected_database"] > 0, "selected_database 非空应有 token"

    def test_char_estimate_fallback(self):
        """当 tiktoken 不可用时，_method 标记为 char_estimate"""
        import builtins
        import importlib
        from app.agent import context as ctx_module

        # Simulate tiktoken unavailable by patching _estimate_tokens
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("Mock: tiktoken not available")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            importlib.reload(ctx_module)
            _, tokens = ctx_module.build_context({"summary": "test"})
            assert tokens.get("_method") == "char_estimate", (
                f"Expected 'char_estimate' marker, got {tokens.get('_method')}"
            )
        finally:
            builtins.__import__ = original_import
            importlib.reload(ctx_module)

    def test_no_char_estimate_when_tiktoken_available(self):
        """当 tiktoken 可用时，_method 应不存在"""
        _, tokens = build_context({"summary": "test"})
        assert "_method" not in tokens, "Should not have _method when tiktoken is available"