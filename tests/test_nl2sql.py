"""
NL2SQL 管道测试

测试核心的 NL2SQL 流程：生成 → 验证 → 修复
"""

import pytest
from app.nl2sql.schema import ColumnSchema, parse_describe_result, schema_to_prompt
from app.nl2sql.validator import validate_sql, strip_sql, is_aggregate_sql


# ========== Schema 解析测试 ==========

def test_parse_describe_result():
    """测试 DESCRIBE 结果解析"""
    result = {
        "columnNames": [
            {"title": "Field", "key": "Field"},
            {"title": "Type", "key": "Type"},
            {"title": "Null", "key": "Null"},
            {"title": "Key", "key": "Key"},
            {"title": "Default", "key": "Default"},
            {"title": "Extra", "key": "Extra"},
        ],
        "columnDatas": [
            {
                "Field": "id",
                "Type": "int",
                "Null": "NO",
                "Key": "PRI",
                "Default": None,
                "Extra": "auto_increment",
            },
            {
                "Field": "name",
                "Type": "varchar(100)",
                "Null": "YES",
                "Key": "",
                "Default": None,
                "Extra": "",
            },
        ],
    }

    columns = parse_describe_result(result)

    assert len(columns) == 2
    assert columns[0].name == "id"
    assert columns[0].type == "int"
    assert columns[0].key == "PRI"
    assert columns[0].extra == "auto_increment"

    assert columns[1].name == "name"
    assert columns[1].type == "varchar(100)"
    assert columns[1].nullable == "YES"


def test_schema_to_prompt():
    """测试表结构转 prompt 文本"""
    columns = [
        ColumnSchema(name="id", type="int", key="PRI"),
        ColumnSchema(name="name", type="varchar(100)"),
    ]
    prompt = schema_to_prompt(columns)
    assert "id" in prompt
    assert "int" in prompt
    assert "name" in prompt
    assert "varchar(100)" in prompt


# ========== SQL 验证测试 ==========

def test_strip_sql():
    """测试 SQL 规范化"""
    assert strip_sql("SELECT *\nFROM users;") == "SELECT * FROM users"
    assert strip_sql("  SELECT  1  ") == "SELECT 1"


def test_is_aggregate_sql():
    """测试聚合查询判断"""
    assert is_aggregate_sql("SELECT COUNT(*) FROM t")
    assert is_aggregate_sql("SELECT name, SUM(amount) FROM t GROUP BY name")
    assert not is_aggregate_sql("SELECT * FROM t LIMIT 10")


def test_validate_sql_pass():
    """测试正常 SQL 验证通过"""
    columns = [
        ColumnSchema(name="id", type="int"),
        ColumnSchema(name="name", type="varchar(100)"),
        ColumnSchema(name="status", type="varchar(20)"),
    ]
    result = validate_sql(
        "SELECT id, name FROM users WHERE status = 'active' LIMIT 10",
        "users",
        columns,
    )
    assert result.passed is True


def test_validate_sql_ddl_blocked():
    """测试 DDL 被拦截"""
    result = validate_sql("DROP TABLE users", "users", [])
    assert result.passed is False
    assert any("DDL" in e for e in result.errors)


def test_validate_sql_write_needs_confirmation():
    """测试写操作需要确认"""
    columns = [ColumnSchema(name="id", type="int")]
    result = validate_sql("UPDATE users SET id = 1", "users", columns)
    assert result.needs_confirmation is True


def test_validate_sql_field_not_exist():
    """测试不存在的字段被检测"""
    columns = [ColumnSchema(name="id", type="int")]
    result = validate_sql(
        "SELECT non_existent_field FROM users LIMIT 10",
        "users",
        columns,
    )
    assert result.passed is False
    assert any("字段不存在" in e for e in result.errors)


def test_validate_sql_multiple_statements():
    """测试多条 SQL 被拦截"""
    result = validate_sql("SELECT 1; SELECT 2", "users", [])
    assert result.passed is False
    assert any("单条" in e for e in result.errors)