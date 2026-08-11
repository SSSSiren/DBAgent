"""execute_sql 工具测试 — 重点覆盖安全 LIMIT 追加逻辑。"""

import importlib

import pytest

from app.tools.execute_sql import (
    _security_check,
    _needs_confirmation,
    _should_append_limit,
    execute_sql,
)

# 注意：app.tools 包与 app.tools.execute_sql 模块同名函数 execute_sql 并存，
# `import app.tools.execute_sql as X` 会因 from-import 同名绑定解析为函数。
# 用 importlib 显式取模块对象供 monkeypatch 使用。
execute_sql_module = importlib.import_module("app.tools.execute_sql")


# ── _should_append_limit：判断语句类型是否支持 LIMIT ──

@pytest.mark.parametrize("sql", [
    "SELECT * FROM account",
    "SELECT a, b FROM t WHERE id = 1",
    "  select name from users  ",
    "WITH cte AS (SELECT 1) SELECT * FROM cte",
    "SELECT * FROM t UNION SELECT * FROM t2",
])
def test_should_append_limit_true_for_select(sql):
    assert _should_append_limit(sql) is True


@pytest.mark.parametrize("sql", [
    "SHOW TABLES",
    "SHOW DATABASES",
    "DESCRIBE account",
    "desc account",
    "EXPLAIN SELECT * FROM t",
    "USE testdb",
])
def test_should_append_limit_false_for_non_select(sql):
    assert _should_append_limit(sql) is False


# ── _security_check / _needs_confirmation 回归 ──

def test_security_check_blocks_ddl():
    ok, msg = _security_check("DROP TABLE account")
    assert not ok
    assert "DDL" in msg


def test_security_check_allows_select():
    ok, _ = _security_check("SELECT * FROM account")
    assert ok


def test_needs_confirmation_for_write():
    assert _needs_confirmation("UPDATE account SET x=1") is True
    assert _needs_confirmation("DELETE FROM account") is True
    assert _needs_confirmation("SELECT * FROM account") is False


# ── execute_sql：SHOW 类语句不追加 LIMIT（回归 bug：near "LIMIT 500"）──

@pytest.mark.asyncio
async def test_execute_sql_show_does_not_append_limit(monkeypatch):
    """SHOW TABLES 不应被追加 LIMIT 500（否则 OneDBA 报 near "LIMIT 500"）。"""
    captured = {}

    class FakeClient:
        async def execute_sql(self, schema_id, sql):
            captured["sql"] = sql
            return {"columnNames": [], "columnDatas": []}

    monkeypatch.setattr(
        execute_sql_module,
        "get_onedba_client",
        lambda: FakeClient(),
    )
    result = await execute_sql(
        schema_id=65938636, sql="SHOW TABLES"
    )
    assert "LIMIT" not in captured["sql"]
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_execute_sql_select_appends_limit(monkeypatch):
    """SELECT 应被追加安全 LIMIT 500。"""
    captured = {}

    class FakeClient:
        async def execute_sql(self, schema_id, sql):
            captured["sql"] = sql
            return {"columnNames": [], "columnDatas": []}

    monkeypatch.setattr(
        execute_sql_module,
        "get_onedba_client",
        lambda: FakeClient(),
    )
    await execute_sql(
        schema_id=65938636, sql="SELECT * FROM account"
    )
    assert captured["sql"].endswith("LIMIT 500")
