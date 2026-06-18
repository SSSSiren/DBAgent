import json
import re

from langchain.tools import tool

from app.client.onedba_client import onedba_client
from app.tools.formatters import format_as_markdown_table


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier):
        raise ValueError(f"非法表名：{identifier}")
    return f"`{identifier}`"


def sanitize_database_item(item: dict) -> dict:
    """Keep only fields useful for agent planning and user display."""

    return {
        "schemaId": item.get("schemaId"),
        "schemaName": item.get("schemaName"),
        "instanceName": item.get("instanceName"),
        "instanceHost": item.get("instanceHost"),
        "instancePort": item.get("instancePort"),
        "envType": item.get("envType"),
        "mainBody": item.get("mainBody"),
        "regionId": item.get("regionId"),
        "dataSource": item.get("dataSource"),
        "ownerPriv": item.get("ownerPriv"),
        "selectPriv": item.get("selectPriv"),
        "exportPriv": item.get("exportPriv"),
        "changePriv": item.get("changePriv"),
        "logic": item.get("logic"),
    }


@tool
async def list_databases(keyword: str = "", env_type: str = "test") -> str:
    """List database schemas available to the current OneDBA token."""

    try:
        databases = await onedba_client.list_databases(keyword=keyword, env_type=env_type)
    except Exception as exc:
        return f"查询失败：{exc}"
    sanitized = [sanitize_database_item(item) for item in databases]
    return json.dumps(sanitized, ensure_ascii=False)


@tool
async def list_tables(schema_id: int) -> str:
    """List tables in a schema."""

    try:
        result = await onedba_client.execute_sql(schema_id=schema_id, sql="SHOW TABLES")
    except Exception as exc:
        return f"查询失败：{exc}"
    return format_as_markdown_table(result)


@tool
async def describe_table(schema_id: int, table_name: str) -> str:
    """Describe a table in a schema."""

    try:
        safe_table = quote_identifier(table_name)
        result = await onedba_client.execute_sql(schema_id=schema_id, sql=f"DESCRIBE {safe_table}")
    except Exception as exc:
        return f"查询失败：{exc}"
    return format_as_markdown_table(result)
