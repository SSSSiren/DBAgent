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
    提取 SQL 中可能是字段引用的标识符（排除已知非字段的 SQL 元素）。

    策略（混合检测）：
    1. 从 SELECT/GROUP BY/ORDER BY 中提取所有标识符
    2. 自动检测函数名（后跟 '(' 的）、CAST 类型关键字（AS xxx 后跟 ')' 或 ','）
    3. 排除 SQL 保留字、AS 别名、表别名
    4. 剩余 token 作为候选字段引用，由调用方验证是否存在于表结构中

    函数名和 CAST 类型通过正则自动检测，无需枚举；SQL 保留字是有限固定集合。
    """
    normalized = strip_sql(sql)

    # 剥离字符串字面量（单引号和双引号），避免 '...' 和 "..." 内的
    # 标识符（如 DATE_FORMAT 中的 '%Y-%m'）被误提取为字段名。
    # 必须在所有 token 提取之前执行。
    _no_strings = re.sub(r"'[^']*'", "''", normalized)
    _no_strings = re.sub(r'"[^"]*"', '""', _no_strings)

    match = re.search(r"SELECT\s+(.*?)\s+FROM\s+", _no_strings, re.IGNORECASE)
    if not match:
        return set()

    select_expression = match.group(1)

    # 提取 AS 别名
    aliases = set(
        re.findall(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)", select_expression, re.IGNORECASE)
    )

    # 提取 FROM 子句中的表别名
    from_clause = _no_strings[match.end():]
    table_aliases = set(
        re.findall(r"\b(?:JOIN\s+)?[A-Za-z_][A-Za-z0-9_]*\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)", from_clause, re.IGNORECASE)
    )

    # 去除 COUNT(*) 避免 * 被误提取
    select_part = re.sub(r"\bCOUNT\s*\(\s*\*\s*\)", "", select_expression, flags=re.IGNORECASE)

    # 提取候选 token
    candidates = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", select_part))
    candidates.update(
        re.findall(r"\bGROUP\s+BY\s+([A-Za-z_][A-Za-z0-9_]*)", _no_strings, re.IGNORECASE)
    )
    candidates.update(
        re.findall(r"\bORDER\s+BY\s+([A-Za-z_][A-Za-z0-9_]*)", _no_strings, re.IGNORECASE)
    )

    # 自动检测函数名：后跟 '(' 的标识符，如 CAST/DATE_FORMAT/YEAR/COALESCE/...
    # 统一转为小写，与后续 token.lower() 匹配。
    function_names = set(
        name.lower()
        for name in re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            _no_strings,
            re.IGNORECASE,
        )
    )

    # 自动检测 CAST 中的类型关键字：AS xxx 后跟 ')' 或 ','，如 CAST(x AS DATE)
    cast_types = set(
        name.lower()
        for name in re.findall(
            r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\),]",
            _no_strings,
            re.IGNORECASE,
        )
    )

    # SQL 保留字/关键字（有限固定集合，不会增长）
    sql_keywords = {
        # 子句关键字
        "select", "from", "where", "group", "by", "order", "limit",
        "having", "offset", "union", "all", "any", "some",
        # 函数关键字
        "as", "count", "sum", "avg", "min", "max", "distinct",
        # 排序
        "desc", "asc",
        # 逻辑/比较
        "and", "or", "not", "in", "is", "like", "between", "exists",
        "regexp", "rlike",
        # JOIN 关键字
        "on", "join", "inner", "left", "right", "outer", "cross", "natural",
        # CASE WHEN
        "case", "when", "then", "else", "end",
        # 窗口函数
        "over", "partition", "rows", "range", "unbounded",
        "preceding", "following", "current", "row",
        # 字面量
        "null", "true", "false", "unknown",
        # 间隔
        "interval",
        "table_name",
    }

    return {
        token
        for token in candidates
        if token not in aliases
        and token.lower() not in table_aliases
        and token.lower() not in sql_keywords
        and token.lower() not in function_names
        and token.lower() not in cast_types
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

    # 4. 表名匹配：支持逗号分隔的多表名（如 "order_record, account"）
    # 检查 SQL 的 FROM/JOIN 子句中是否引用了所有已解析表
    table_names = [t.strip() for t in table_name.split(",") if t.strip()]
    for t_name in table_names:
        identifier = r"`?[A-Za-z_][A-Za-z0-9_]*`?"
        table_pattern = rf"\b(?:FROM|JOIN)\s+(?:{identifier}\.)?`?{re.escape(t_name)}`?\b"
        if normalized_sql.upper().startswith("SELECT") and not re.search(
            table_pattern, normalized_sql, re.IGNORECASE
        ):
            errors.append(f"SQL 未引用已解析表 {t_name}")

    # 5. 字段存在性检查
    # _referenced_columns 返回候选字段引用（已排除函数名、关键字、别名），
    # 此处验证候选字段是否存在于表结构中。
    # 多表 DESCRIBE 后 columns 包含所有表的字段，JOIN 查询也能验证。
    # 构建字段名查找表：同时注册带前缀和裸字段名。
    # query_database 会给字段名加表前缀（如 order_record.id），
    # 但 SQL 中引用的是裸字段名（如 id），两者都需要能匹配。
    normalized_columns: dict[str, str] = {}
    for column in columns:
        full_name = column.name
        bare_name = full_name.split(".")[-1] if "." in full_name else full_name
        normalized_columns[normalize_identifier_hint(full_name)] = full_name
        normalized_columns[normalize_identifier_hint(bare_name)] = full_name
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