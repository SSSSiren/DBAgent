from dataclasses import dataclass
import re

from langchain.tools import tool

from app.client.onedba_client import onedba_client
from app.tools.formatters import format_as_markdown_table


WRITE_PREFIXES = ("UPDATE", "DELETE", "INSERT")
BLOCKED_PREFIXES = ("CREATE", "ALTER", "DROP", "TRUNCATE")


@dataclass(frozen=True)
class SecurityCheckResult:
    passed: bool
    message: str = ""


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip())


def needs_confirmation(sql: str) -> bool:
    sql_upper = normalize_sql(sql).upper()
    return sql_upper.startswith(WRITE_PREFIXES)


def security_check(sql: str) -> SecurityCheckResult:
    sql_upper = normalize_sql(sql).upper()
    if not sql_upper:
        return SecurityCheckResult(False, "SQL 不能为空")
    if sql_upper.startswith(BLOCKED_PREFIXES):
        return SecurityCheckResult(False, "DDL 操作请走 OneDBA 工单")
    return SecurityCheckResult(True)


@tool
async def execute_sql(sql: str, schema_id: int) -> str:
    """Execute SQL against a OneDBA schema and return a Markdown table."""

    check = security_check(sql)
    if not check.passed:
        return f"执行被拒绝：{check.message}"

    try:
        result = await onedba_client.execute_sql(schema_id=schema_id, sql=sql)
    except Exception as exc:
        return f"执行失败：{exc}"
    return format_as_markdown_table(result)
