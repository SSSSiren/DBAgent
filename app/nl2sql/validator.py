from dataclasses import dataclass, field
import re

from app.nl2sql.intent import normalize_identifier_hint
from app.nl2sql.schema import ColumnSchema
from app.tools.sql_executor import security_check


@dataclass
class ValidationResult:
    passed: bool
    sql: str
    errors: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def strip_sql(sql: str) -> str:
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


def validate_sql(sql: str, table_name: str, columns: list[ColumnSchema], default_limit: int = 100) -> ValidationResult:
    errors: list[str] = []
    assumptions: list[str] = []
    normalized_sql = strip_sql(sql)

    check = security_check(normalized_sql)
    if not check.passed:
        errors.append(check.message)
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
    for column in referenced_columns(normalized_sql, table_name):
        if column in {"cnt", "total"}:
            continue
        if normalize_identifier_hint(column) not in normalized_columns:
            errors.append(f"字段不存在：{column}")

    limit = default_limit
    if is_aggregate_sql(normalized_sql):
        limit = min(default_limit, 20) if default_limit != 1 else 1
    if normalized_sql.upper().startswith("SELECT"):
        normalized_sql = ensure_limit(normalized_sql, limit, assumptions)

    return ValidationResult(not errors, normalized_sql, errors, assumptions)
