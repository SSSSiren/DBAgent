from dataclasses import dataclass, field
import re

from app.nl2sql.schema import ColumnSchema, normalize_identifier_hint


# 内联安全检查逻辑，避免循环导入
WRITE_PREFIXES = ("UPDATE", "DELETE", "INSERT")
BLOCKED_PREFIXES = ("CREATE", "ALTER", "DROP", "TRUNCATE")


def _security_check(sql: str) -> tuple[bool, str]:
    """内联的安全检查，返回 (passed, message)"""
    sql_upper = re.sub(r"\s+", " ", sql.strip()).upper()
    if not sql_upper:
        return False, "SQL 不能为空"
    if sql_upper.startswith(BLOCKED_PREFIXES):
        return False, "DDL 操作请走 OneDBA 工单"
    return True, ""


@dataclass
class ValidationResult:
    passed: bool
    sql: str
    errors: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def strip_sql(sql: str) -> str:
    # 先处理字面的 \n 和 \r 字符串（LLM 可能返回双重转义）
    sql = sql.replace('\\n', ' ').replace('\\r', ' ')
    # 再将所有空白字符替换为单个空格
    return re.sub(r"\s+", " ", sql.strip().rstrip(";"))


def is_aggregate_sql(sql: str) -> bool:
    upper = sql.upper()
    return any(token in upper for token in ("COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "GROUP BY"))


def ensure_limit(sql: str, limit: int, assumptions: list[str]) -> str:
    match = re.search(r"\bLIMIT\s+(\d+)\b", sql, re.IGNORECASE)
    if match:
        current_limit = int(match.group(1))
        if current_limit == limit:
            return sql
        assumptions.append(f"已按用户要求将 LIMIT {current_limit} 调整为 LIMIT {limit}")
        return re.sub(r"\bLIMIT\s+\d+\b", f"LIMIT {limit}", sql, flags=re.IGNORECASE)
    assumptions.append(f"已自动追加 LIMIT {limit}")
    return f"{sql} LIMIT {limit}"


def referenced_columns(sql: str, table_name: str) -> set[str]:
    normalized = strip_sql(sql)
    match = re.search(r"SELECT\s+(.*?)\s+FROM\s+", normalized, re.IGNORECASE)
    if not match:
        return set()
    select_expression = match.group(1)
    aliases = set(re.findall(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\b", select_expression, re.IGNORECASE))
    select_part = re.sub(r"\bCOUNT\s*\(\s*\*\s*\)", "", select_expression, flags=re.IGNORECASE)
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", select_part))
    tokens.update(re.findall(r"\bGROUP\s+BY\s+([A-Za-z_][A-Za-z0-9_]*)", normalized, re.IGNORECASE))
    tokens.update(re.findall(r"\bORDER\s+BY\s+([A-Za-z_][A-Za-z0-9_]*)", normalized, re.IGNORECASE))
    ignored = {
        "select",
        "from",
        "where",
        "group",
        "by",
        "order",
        "limit",
        "as",
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "desc",
        "asc",
        table_name.lower(),
    }
    return {
        token
        for token in tokens
        if token.lower() not in ignored and token not in aliases and not token.isdigit()
    }


def _has_join(sql: str) -> bool:
    """检查 SQL 是否包含 JOIN 语句"""
    return bool(re.search(r'\bJOIN\b', sql, re.IGNORECASE))


def validate_sql(sql: str, table_name: str, columns: list[ColumnSchema], default_limit: int = 100) -> ValidationResult:
    errors: list[str] = []
    assumptions: list[str] = []
    normalized_sql = strip_sql(sql)
    print(f"Normalized SQL: {normalized_sql}")

    passed, message = _security_check(normalized_sql)
    if not passed:
        errors.append(message)
    if ";" in normalized_sql:
        errors.append("只允许单条 SQL")
    if not normalized_sql.upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
        errors.append("NL2SQL 只允许 SELECT/SHOW/DESCRIBE")

    identifier = r"`?[A-Za-z_][A-Za-z0-9_]*`?"
    table_pattern = rf"\bFROM\s+(?:{identifier}\.)?`?{re.escape(table_name)}`?\b"
    if normalized_sql.upper().startswith("SELECT") and not re.search(table_pattern, normalized_sql, re.IGNORECASE):
        errors.append(f"SQL 只能查询已解析表 {table_name}")

    column_names = {column.name for column in columns}
    normalized_columns = {normalize_identifier_hint(column.name): column.name for column in columns}

    # 如果 SQL 包含 JOIN，跳过字段验证（validator 只知道主表的字段）
    if not _has_join(normalized_sql):
        for column in referenced_columns(normalized_sql, table_name):
            if column in {"cnt", "total"}:
                continue
            if normalize_identifier_hint(column) not in normalized_columns:
                errors.append(f"字段不存在：{column}")

    # 不再在此处强制追加 LIMIT
    # 改由 query_database.py 在执行时：
    #   1) 先 COUNT 获取真实总数
    #   2) 执行时加安全 LIMIT 防止拉爆
    #   3) 展示时限制显示行数
    # 这样 LLM 能看到真实总数，不会误报

    return ValidationResult(not errors, normalized_sql, errors, assumptions)
