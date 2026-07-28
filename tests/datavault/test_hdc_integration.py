"""Integration tests for HDC context injection and admin API."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.context import build_context


class TestBuildContextHDC:
    """Tests for HDC [数据底座] paragraph injection in build_context()."""

    def test_hdc_context_injected(self):
        """HDC context from session_state is included in output."""
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
            "selected_schema_id": 142,
            "_hdc_context": "[数据底座 — 数据库知识]\n**数据库概览**: 电商交易核心库\n\n**匹配的业务表**:\n- **after_sale_order**（售后/退货/退款）: 售后订单表",
        }

        result, _ = build_context(session_state)

        assert "[数据底座 — 数据库知识]" in result
        assert "after_sale_order" in result
        assert "售后/退货/退款" in result

    def test_hdc_context_empty_skipped(self):
        """Empty _hdc_context is skipped (no empty paragraph)."""
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
            "_hdc_context": "",
        }

        result, _ = build_context(session_state)

        assert "[数据底座 — 数据库知识]" not in result

    def test_hdc_context_missing_skipped(self):
        """Missing _hdc_context key is skipped."""
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
        }

        result, _ = build_context(session_state)

        assert "[数据底座 — 数据库知识]" not in result

    def test_hdc_context_alongside_other_sections(self):
        """HDC paragraph coexists with memory and preferences paragraphs."""
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
            "_memories": [{"abstract": "用户关注订单数据"}],
            "_preferences": [{"database_name": "dwd_trade", "table_name": "order_info", "query_count": 5}],
            "_hdc_context": "[数据底座 — 数据库知识]\n测试 HDC 内容",
        }

        result, _ = build_context(session_state)

        assert "[数据底座 — 数据库知识]" in result
        assert "[长期记忆 — 来自之前的对话]" in result
        assert "[操作记忆 — 查询偏好]" in result

    def test_hdc_context_position(self):
        """HDC paragraph appears after preferences (last section)."""
        session_state = {
            "selected_database": {"schemaName": "dwd_trade"},
            "_preferences": [{"database_name": "dwd_trade", "table_name": "t", "query_count": 1}],
            "_hdc_context": "[数据底座 — 数据库知识]\nHDC 内容",
        }

        result, _ = build_context(session_state)

        pref_pos = result.find("[操作记忆 — 查询偏好]")
        hdc_pos = result.find("[数据底座 — 数据库知识]")
        assert hdc_pos > pref_pos, "HDC should come after preferences"
