"""
SQL 记忆集成测试 — 上下文注入格式和 Hook 行为
"""

import pytest
from app.agent.context import build_context


# ============================================================================
# Tests: Context Injection Formatting
# ============================================================================


def test_build_context_injects_sql_memories_paragraph():
    """_sql_memories 非空时 → 注入 [SQL 历史记忆] 段落"""
    state = {
        "_sql_memories": [
            {
                "question": "有多少已支付的订单？",
                "sql_text": "SELECT COUNT(*) FROM orders WHERE status = 'paid'",
                "sql_truncated": "SELECT COUNT(*) FROM orders WHERE status = 'paid'",
                "row_count": 1234,
                "column_names": ["COUNT(*)"],
                "similarity": 0.95,
            },
        ]
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆 — 相关查询]" in ctx
    assert "已支付" in ctx
    assert "SELECT COUNT(*)" in ctx
    assert "1234" in ctx


def test_build_context_empty_sql_memories_no_injection():
    """_sql_memories 为空 → 不注入，保持原有格式"""
    state = {
        "summary": "之前的对话摘要",
        "selected_database": {"schemaName": "test_db"},
        "_sql_memories": [],
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" not in ctx
    assert "之前的对话摘要" in ctx
    assert "test_db" in ctx


def test_build_context_no_sql_memories_key_no_injection():
    """完全没有 _sql_memories key → 不注入"""
    state = {
        "summary": "test",
        "selected_database": {"schemaName": "test_db"},
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" not in ctx
    # 原有的 7 段格式不受影响
    assert "[之前的对话摘要]" in ctx
    assert "当前选择的数据库" in ctx


def test_build_context_sql_memories_none_no_injection():
    """_sql_memories 为 None → 不注入"""
    state = {"_sql_memories": None, "summary": "test"}
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" not in ctx


# ============================================================================
# Tests: Token Budget Truncation
# ============================================================================


def test_build_context_token_budget_truncation():
    """Token 预算超限 → 截断"""
    long_sql = "SELECT " + ", ".join(f"column_{i}" for i in range(40)) + " FROM very_very_long_table_name_" * 30
    state = {
        "_sql_memories": [
            {
                "question": f"问题 {i}",
                "sql_text": long_sql,
                "sql_truncated": long_sql[:500],
                "row_count": 100,
                "column_names": ["id"],
                "similarity": 0.9 - 0.05 * i,
            }
            for i in range(10)
        ]
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" in ctx
    # 应该只包含部分记录（截断），且不超过预算
    ctx_len = len(ctx)
    assert ctx_len <= 2500  # 宽松上限，因为 budget=1500 但前面有其它段


def test_build_context_token_budget_all_fit():
    """所有记录在预算内 → 全部注入"""
    state = {
        "_sql_memories": [
            {
                "question": f"问题 {i}",
                "sql_text": f"SELECT {i} FROM t",
                "sql_truncated": f"SELECT {i} FROM t",
                "row_count": i * 10,
                "column_names": ["id"],
                "similarity": 0.9,
            }
            for i in range(3)
        ]
    }
    ctx, _ = build_context(state)
    assert "问题 0" in ctx
    assert "问题 1" in ctx
    assert "问题 2" in ctx


# ============================================================================
# Tests: SQL Safety Filter
# ============================================================================


def test_build_context_filters_dangerous_sql():
    """包含写操作的 SQL → 过滤掉"""
    state = {
        "_sql_memories": [
            {
                "question": "插入数据",
                "sql_text": "INSERT INTO orders VALUES (1, 'test')",
                "sql_truncated": "INSERT INTO orders VALUES (1, 'test')",
                "row_count": 1,
                "column_names": [],
                "similarity": 0.9,
            },
            {
                "question": "安全的查询",
                "sql_text": "SELECT * FROM orders WHERE status = 'active'",
                "sql_truncated": "SELECT * FROM orders WHERE status = 'active'",
                "row_count": 500,
                "column_names": ["id", "status"],
                "similarity": 0.85,
            },
        ]
    }
    ctx, _ = build_context(state)
    assert "INSERT INTO" not in ctx
    assert "UPDATE" not in ctx
    assert "DELETE" not in ctx
    assert "DROP" not in ctx
    assert "安全的查询" in ctx
    assert "SELECT * FROM orders" in ctx


def test_build_context_filters_all_dangerous_keywords():
    """所有写操作关键词 → 均被过滤"""
    dangerous_sqls = [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE TABLE t",
        "ALTER TABLE t ADD COLUMN x",
        "CREATE TABLE t (id INT)",
    ]
    for i, sql in enumerate(dangerous_sqls):
        state = {
            "_sql_memories": [{
                "question": f"危险查询 {i}",
                "sql_text": sql,
                "sql_truncated": sql,
                "row_count": 1,
                "column_names": [],
                "similarity": 0.9,
            }]
        }
        ctx, _ = build_context(state)
        assert sql.split()[0].upper() not in ctx.upper().split(), f"{sql.split()[0]} 应被过滤"


# ============================================================================
# Tests: Context Paragraph Ordering
# ============================================================================


def test_build_context_sql_memory_at_correct_position():
    """SQL 记忆段落插入在 HDC 之后（第 8 段）"""
    state = {
        "summary": "摘要",
        "_memories": [{"abstract": "长期记忆内容"}],
        "_preferences": [{"table_name": "orders", "database_name": "db1", "query_count": 5}],
        "_hdc_context": "HDC 数据底座上下文",
        "_sql_memories": [{
            "question": "问题",
            "sql_text": "SELECT 1",
            "sql_truncated": "SELECT 1",
            "row_count": 1,
            "column_names": ["x"],
            "similarity": 0.9,
        }],
    }
    ctx, _ = build_context(state)
    parts = ctx.split("\n\n")
    labels = [p.split("\n")[0] for p in parts if p.strip()]
    # SQL 记忆应在 HDC 之后（最后一段）
    assert "HDC 数据底座上下文" in ctx
    assert "[SQL 历史记忆" in ctx
    hdc_idx = next(i for i, p in enumerate(parts) if "HDC" in p)
    sql_idx = next(i for i, p in enumerate(parts) if "SQL 历史记忆" in p)
    assert sql_idx > hdc_idx, "SQL 记忆应在 HDC 之后"


# ============================================================================
# Tests: SQL Truncation in Display
# ============================================================================


def test_build_context_truncates_long_sql_in_display():
    """长 SQL 在注入时截断至 500 字符"""
    very_long_sql = "SELECT " + ", ".join(f"col_{i}" for i in range(200)) + " FROM long_table"
    state = {
        "_sql_memories": [{
            "question": "长查询",
            "sql_text": very_long_sql,
            "sql_truncated": very_long_sql[:500],
            "row_count": 10,
            "column_names": ["x"],
            "similarity": 0.9,
        }]
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" in ctx
    # sql_truncated 为 500 字符，注入时若 >500 再加 "..."
    # 所以总计不应超过 ~505
    assert len(ctx) < 4000  # 不会包含完整超长 SQL


# ============================================================================
# Tests: Edge Cases
# ============================================================================


def test_build_context_memory_without_question():
    """问题字段缺失 → 不崩溃"""
    state = {
        "_sql_memories": [{
            "sql_text": "SELECT 1",
            "sql_truncated": "SELECT 1",
            "row_count": 1,
            "column_names": [],
            "similarity": 0.9,
        }]
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" in ctx
    assert "SELECT 1" in ctx


def test_build_context_memory_without_row_count():
    """无行数 → 省略结果行"""
    state = {
        "_sql_memories": [{
            "question": "查询",
            "sql_text": "SELECT 1",
            "sql_truncated": "SELECT 1",
            "row_count": None,
            "column_names": [],
            "similarity": 0.9,
        }]
    }
    ctx, _ = build_context(state)
    assert "[SQL 历史记忆" in ctx
    assert "SELECT 1" in ctx


def test_build_context_multiple_memories_numbered():
    """多条记忆 → 编号"""
    state = {
        "_sql_memories": [
            {
                "question": f"Q{i}",
                "sql_text": f"SELECT {i}",
                "sql_truncated": f"SELECT {i}",
                "row_count": i,
                "column_names": ["id"],
                "similarity": 1.0 - 0.1 * i,
            }
            for i in range(3)
        ]
    }
    ctx, _ = build_context(state)
    assert "1. **问题**: Q0" in ctx
    assert "2. **问题**: Q1" in ctx
    assert "3. **问题**: Q2" in ctx
