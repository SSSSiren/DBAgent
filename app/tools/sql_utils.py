"""
SQL 工具函数 — 复用的 SQL 处理函数
"""

import re


def strip_limit(sql: str) -> str:
    """去除 SQL 末尾的 LIMIT 子句和分号"""
    sql = re.sub(r"\s+LIMIT\s+\d+(\s*;?\s*)$", "", sql, flags=re.IGNORECASE)
    return sql.rstrip(";").strip()


def to_count_sql(sql: str) -> str:
    """将 SELECT ... FROM ... 替换为 SELECT COUNT(*) AS cnt FROM ..."""
    return re.sub(
        r"SELECT\s+.*?\s+FROM\s+",
        "SELECT COUNT(*) AS cnt FROM ",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )