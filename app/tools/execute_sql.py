"""
execute_sql 工具 — 直接执行 SQL 查询

参考 DBAgent 的 app/tools/agent_tools.py:execute_sql_tool
"""

import re

from app.client.onedba import get_onedba_client
from app.tools.formatters import format_as_markdown_table
from app.tools.sql_utils import strip_limit


DEFAULT_SAFETY_LIMIT = 500  # 工程安全 LIMIT，防止一次性返回太多数据挤爆 LLM 上下文


# 安全检查
WRITE_PREFIXES = ("UPDATE", "DELETE", "INSERT")
BLOCKED_PREFIXES = ("CREATE", "ALTER", "DROP", "TRUNCATE", "REPLACE", "GRANT", "REVOKE")


def _security_check(sql: str) -> tuple[bool, str]:
    """安全检查：拦截 DDL 操作"""
    sql_upper = re.sub(r"\s+", " ", sql.strip()).upper()
    if not sql_upper:
        return False, "SQL 不能为空"
    if sql_upper.startswith(BLOCKED_PREFIXES):
        return False, "DDL/DCL 操作请走 OneDBA 工单"
    return True, ""


def _needs_confirmation(sql: str) -> bool:
    """检查是否为需要用户确认的写操作"""
    sql_upper = re.sub(r"\s+", " ", sql.strip()).upper()
    return sql_upper.startswith(WRITE_PREFIXES)


def _should_append_limit(sql: str) -> bool:
    """判断语句类型是否支持 LIMIT 子句。

    只对 SELECT（含 WITH...SELECT / UNION 等以 SELECT 开头的语句）追加安全 LIMIT。
    SHOW / DESCRIBE / EXPLAIN / USE 等语句不支持 LIMIT，追加会导致 OneDBA
    语法错误（实测报 near "LIMIT 500"）。
    """
    sql_upper = re.sub(r"\s+", " ", sql.strip()).upper()
    return sql_upper.startswith(("SELECT", "WITH"))


async def execute_sql(schema_id: int, sql: str) -> str:
    """直接执行 SQL 查询。

    参数:
        schema_id: 数据库的 schemaId（必需）
        sql: SQL 语句（必需）

    返回:
        Markdown 格式的查询结果

    约束:
        - 只允许 SELECT/SHOW/DESCRIBE
        - UPDATE/DELETE/INSERT 会被拦截，需要用户确认
        - 禁止 CREATE/ALTER/DROP/TRUNCATE 等 DDL 操作

    使用场景:
        - 用户提供了明确的 SQL 语句
        - 需要执行复杂的自定义查询
        - 对于自然语言查询，优先使用 query_database 工具
    """
    # 安全检查
    passed, message = _security_check(sql)
    if not passed:
        return f"执行被拒绝：{message}"

    # 检查是否需要确认（写操作）
    if _needs_confirmation(sql):
        return (
            f"检测到写操作，需要用户确认：\n\n"
            f"```sql\n{sql}\n```\n\n"
            f"请让用户确认后再执行。"
        )

    client = get_onedba_client()

    # 剥离 LLM 可能习惯性加的 LIMIT（不可靠），对支持 LIMIT 的语句加安全兜底
    display_sql = strip_limit(sql)
    if _should_append_limit(display_sql):
        execute_sql_str = f"{display_sql} LIMIT {DEFAULT_SAFETY_LIMIT}"
    else:
        # SHOW / DESCRIBE / EXPLAIN 等不支持 LIMIT，直接执行（OneDBA 会报语法错误）
        execute_sql_str = display_sql

    try:
        result = await client.execute_sql(schema_id=schema_id, sql=execute_sql_str)
    except Exception as exc:
        return f"执行失败：{exc}"

    return format_as_markdown_table(result)