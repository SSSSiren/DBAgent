from app.tools.formatters import format_as_markdown_table
from app.tools.db_explorer import sanitize_database_item
from app.tools.sql_executor import needs_confirmation, security_check


def test_format_as_markdown_table_converts_onedba_result():
    result = {
        "columnNames": [
            {"key": "col_1", "field": "col_1", "title": "id"},
            {"key": "col_2", "field": "col_2", "title": "name"},
        ],
        "columnDatas": [{"_idx_": 1, "col_1": "123", "col_2": "test|demo"}],
    }

    assert format_as_markdown_table(result) == (
        "| id | name |\n"
        "| --- | --- |\n"
        "| 123 | test\\|demo |\n"
        "\n共 1 行"
    )


def test_format_as_markdown_table_empty_rows():
    assert format_as_markdown_table({"columnNames": [], "columnDatas": []}) == "查询成功，结果为空"


def test_sql_security_check_blocks_ddl():
    result = security_check(" drop table users")
    assert not result.passed
    assert "DDL" in result.message


def test_needs_confirmation_for_write_sql():
    assert needs_confirmation("update users set name = 'a'")
    assert needs_confirmation(" delete from users")
    assert needs_confirmation("insert into users values (1)")
    assert not needs_confirmation("select * from users")


def test_sanitize_database_item_removes_user_details():
    sanitized = sanitize_database_item(
        {
            "schemaId": 1,
            "schemaName": "dw",
            "instanceName": "inst",
            "ownerUsers": [{"email": "owner@example.com"}],
            "dbaUsers": [{"avatar": "https://example.test/avatar.png"}],
        }
    )

    assert sanitized["schemaId"] == 1
    assert "ownerUsers" not in sanitized
    assert "dbaUsers" not in sanitized
