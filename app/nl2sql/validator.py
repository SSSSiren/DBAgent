"""
SQL 验证器 — 安全检查、字段检查、LIMIT 强制

参考 DBAgent 的 app/nl2sql/validator.py
"""

import re
from dataclasses import dataclass, field

from app.nl2sql.schema import ColumnSchema, normalize_identifier_hint


# 写操作前缀
WRITE_PREFIXES = ("UPDATE", "DELETE", "INSERT")
# 被拦截的 DDL 操作
BLOCKED_PREFIXES = ("CREATE", "ALTER", "DROP", "TRUNCATE")


def _security_check(sql: str) -> tuple[bool, str]:
    """安全检查：拦截 DDL 操作"""
    sql_upper = re.sub(r"\s+", " ", sql.strip()).upper()
    if not sql_upper:
        return False, "SQL 不能为空"
    if sql_upper.startswith(BLOCKED_PREFIXES):
        return False, "DDL 操作请走 OneDBA 工单"
    return True, ""


def _is_write_operation(sql: str) -> bool:
    """检查是否为写操作（UPDATE/DELETE/INSERT）"""
    sql_upper = re.sub(r"\s+", " ", sql.strip()).upper()
    return sql_upper.startswith(WRITE_PREFIXES)


def _has_join(sql: str) -> bool:
    """检查 SQL 是否包含 JOIN"""
    return bool(re.search(r"\bJOIN\b", sql, re.IGNORECASE))


@dataclass
class ValidationResult:
    """SQL 验证结果"""

    passed: bool
    sql: str                          # 规范化后的 SQL
    errors: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    needs_confirmation: bool = False  # 是否需要用户确认（写操作）


def strip_sql(sql: str) -> str:
    """规范化 SQL：去除多余空白、转义换行、末尾分号"""
    sql = sql.replace("\\n", " ").replace("\\r", " ")
    return re.sub(r"\s+", " ", sql.strip().rstrip(";"))


def is_aggregate_sql(sql: str) -> bool:
    """判断是否为聚合查询"""
    upper = sql.upper()
    return any(
        token in upper
        for token in ("COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "GROUP BY")
    )


def ensure_limit(sql: str, limit: int, assumptions: list[str]) -> str:
    """确保 SQL 包含 LIMIT 子句"""
    match = re.search(r"\bLIMIT\s+(\d+)\b", sql, re.IGNORECASE)
    if match:
        current_limit = int(match.group(1))
        if current_limit == limit:
            return sql
        assumptions.append(f"已将 LIMIT {current_limit} 调整为 LIMIT {limit}")
        return re.sub(r"\bLIMIT\s+\d+\b", f"LIMIT {limit}", sql, flags=re.IGNORECASE)
    assumptions.append(f"已自动追加 LIMIT {limit}")
    return f"{sql} LIMIT {limit}"


def _referenced_columns(sql: str, table_name: str) -> set[str]:
    """
    提取 SQL 中引用的列名（仅 SELECT 和 GROUP BY 中的非关键字标识符）。

    用于验证列名是否存在于表结构中。
    """
    normalized = strip_sql(sql)
    match = re.search(r"SELECT\s+(.*?)\s+FROM\s+", normalized, re.IGNORECASE)
    if not match:
        return set()

    select_expression = match.group(1)

    # 提取别名
    aliases = set(
        re.findall(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)", select_expression, re.IGNORECASE)
    )

    # 去除 COUNT(*) 避免 * 被误提取
    select_part = re.sub(r"\bCOUNT\s*\(\s*\*\s*\)", "", select_expression, flags=re.IGNORECASE)

    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", select_part))
    tokens.update(
        re.findall(r"\bGROUP\s+BY\s+([A-Za-z_][A-Za-z0-9_]*)", normalized, re.IGNORECASE)
    )
    tokens.update(
        re.findall(r"\bORDER\s+BY\s+([A-Za-z_][A-Za-z0-9_]*)", normalized, re.IGNORECASE)
    )

    ignored = {
        "select", "from", "where", "group", "by", "order", "limit",
        "as", "count", "sum", "avg", "min", "max", "desc", "asc",
        table_name.lower(),
    }

    return {
        token
        for token in tokens
        if token.lower() not in ignored
        and token not in aliases
        and not token.isdigit()
    }


def validate_sql(
    sql: str,
    table_name: str,
    columns: list[ColumnSchema],
) -> ValidationResult:
    """
    验证生成的 SQL。

    检查项：
    1. 安全：不允许 DDL 操作
    2. 单语句：不允许分号分隔的多条 SQL
    3. 只读：只允许 SELECT/SHOW/DESCRIBE
    4. 表名匹配：只允许查询指定的表
    5. 字段存在性：引用的列名必须在表结构中存在（JOIN 除外）
    6. 写操作：UPDATE/DELETE/INSERT 标记为需要确认

    Args:
        sql: 待验证的 SQL
        table_name: 目标表名
        columns: 表结构中的字段列表
        default_limit: 默认 LIMIT 值

    Returns:
        ValidationResult: 验证结果
    """
    errors: list[str] = []
    assumptions: list[str] = []
    normalized_sql = strip_sql(sql)

    # 1. 安全检查
    passed, message = _security_check(normalized_sql)
    if not passed:
        errors.append(message)

    # 2. 单语句检查
    if ";" in normalized_sql:
        errors.append("只允许单条 SQL")

    # 3. 只读检查
    if not normalized_sql.upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
        errors.append("NL2SQL 只允许 SELECT/SHOW/DESCRIBE")

    # 4. 表名匹配
    identifier = r"`?[A-Za-z_][A-Za-z0-9_]*`?"
    table_pattern = rf"\bFROM\s+(?:{identifier}\.)?`?{re.escape(table_name)}`?\b"
    if normalized_sql.upper().startswith("SELECT") and not re.search(
        table_pattern, normalized_sql, re.IGNORECASE
    ):
        errors.append(f"SQL 只能查询已解析表 {table_name}")

    # 5. 字段存在性检查（JOIN 查询跳过，因为 validator 只知道主表字段）
    if not _has_join(normalized_sql):
        column_names = {column.name for column in columns}
        normalized_columns = {
            normalize_identifier_hint(column.name): column.name
            for column in columns
        }
        for column in _referenced_columns(normalized_sql, table_name):
            # 跳过常见的聚合别名
            if column in {"cnt", "total"}:
                continue
            if normalize_identifier_hint(column) not in normalized_columns:
                errors.append(f"字段不存在：{column}")

    # 6. 写操作检测
    needs_confirmation = _is_write_operation(normalized_sql)

    return ValidationResult(
        passed=not errors,
        sql=normalized_sql,
        errors=errors,
        assumptions=assumptions,
        needs_confirmation=needs_confirmation,
    )