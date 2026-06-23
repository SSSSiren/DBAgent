from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


READONLY_PREFIXES = ("SELECT", "WITH")
BLOCKED_TOKENS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
)


@dataclass(frozen=True)
class ResultCheck:
    type: str = "compare_result"
    order_sensitive: bool = False
    tolerance: float = 0.0


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    difficulty: str
    task_type: str
    user_question: str
    expected_tables: list[str]
    expected_columns: list[str]
    reference_sql: str
    result_check: ResultCheck = field(default_factory=ResultCheck)
    must_include: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkCase":
        result_check = payload.get("result_check") or {}
        return cls(
            id=payload["id"],
            difficulty=payload["difficulty"],
            task_type=payload["task_type"],
            user_question=payload["user_question"],
            expected_tables=list(payload.get("expected_tables") or []),
            expected_columns=list(payload.get("expected_columns") or []),
            reference_sql=payload["reference_sql"],
            result_check=ResultCheck(**result_check),
            must_include=list(payload.get("must_include") or []),
            must_not_include=list(payload.get("must_not_include") or []),
            notes=payload.get("notes", ""),
        )


@dataclass(frozen=True)
class Prediction:
    id: str
    sql: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Prediction":
        return cls(id=payload["id"], sql=payload.get("sql", ""))


@dataclass
class CaseScore:
    id: str
    static_passed: bool
    safety_passed: bool
    schema_passed: bool
    execution_passed: bool | None
    result_passed: bool | None
    errors: list[str] = field(default_factory=list)
    failure_categories: list[str] = field(default_factory=list)
    candidate_sql: str = ""


@dataclass
class BenchmarkReport:
    total: int
    scores: list[CaseScore]

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "static_pass_rate": ratio(score.static_passed for score in self.scores),
            "safety_pass_rate": ratio(score.safety_passed for score in self.scores),
            "schema_pass_rate": ratio(score.schema_passed for score in self.scores),
            "execution_pass_rate": ratio_optional(score.execution_passed for score in self.scores),
            "result_accuracy": ratio_optional(score.result_passed for score in self.scores),
            "failed_case_ids": [score.id for score in self.scores if not is_case_passed(score)],
            "failure_category_counts": count_failure_categories(self.scores),
        }


def ratio(values: Any) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(1 for value in values if value) / len(values), 4)


def ratio_optional(values: Any) -> float | None:
    values = [value for value in values if value is not None]
    if not values:
        return None
    return ratio(values)


def count_failure_categories(scores: list[CaseScore]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for score in scores:
        for category in score.failure_categories:
            counts[category] = counts.get(category, 0) + 1
    return counts


def is_case_passed(score: CaseScore) -> bool:
    if not (score.static_passed and score.safety_passed and score.schema_passed):
        return False
    if score.execution_passed is False or score.result_passed is False:
        return False
    return True


def load_cases(path: str | Path) -> list[BenchmarkCase]:
    return [BenchmarkCase.from_dict(payload) for payload in load_jsonl(path)]


def load_predictions(path: str | Path) -> dict[str, Prediction]:
    return {prediction.id: prediction for prediction in (Prediction.from_dict(payload) for payload in load_jsonl(path))}


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSONL") from exc
    return rows


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";"))


def is_readonly_sql(sql: str) -> bool:
    normalized = normalize_sql(sql)
    upper = normalized.upper()
    if not upper.startswith(READONLY_PREFIXES):
        return False
    if ";" in normalized:
        return False
    tokens = set(re.findall(r"\b[A-Z_]+\b", upper))
    return not any(token in tokens for token in BLOCKED_TOKENS)


def extract_sql_identifiers(sql: str) -> set[str]:
    cleaned = re.sub(r"`([^`]+)`", r"\1", normalize_sql(sql))
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", cleaned))
    return {identifier.lower() for identifier in identifiers}


def static_score(case: BenchmarkCase, sql: str) -> tuple[bool, bool, bool, list[str]]:
    errors: list[str] = []
    normalized_sql = normalize_sql(sql)
    identifiers = extract_sql_identifiers(normalized_sql)

    safety_passed = is_readonly_sql(normalized_sql)
    if not safety_passed:
        errors.append("SQL must be a single read-only SELECT/WITH statement")

    upper_sql = normalized_sql.upper()
    for token in case.must_include:
        if token.upper() not in upper_sql:
            errors.append(f"Missing required token: {token}")
    for token in case.must_not_include:
        if token.upper() in upper_sql:
            errors.append(f"Forbidden token present: {token}")

    missing_tables = [table for table in case.expected_tables if table.lower() not in identifiers]
    missing_columns = [column for column in case.expected_columns if column.lower() not in identifiers]
    schema_passed = not missing_tables and not missing_columns
    if missing_tables:
        errors.append(f"Missing expected tables: {', '.join(missing_tables)}")
    if missing_columns:
        errors.append(f"Missing expected columns: {', '.join(missing_columns)}")

    static_passed = safety_passed and schema_passed and not any(
        error.startswith(("Missing required", "Forbidden token")) for error in errors
    )
    return static_passed, safety_passed, schema_passed, errors


def normalize_rows(rows: list[dict[str, Any]], order_sensitive: bool = False) -> list[dict[str, str]]:
    normalized = [{key: normalize_value(value) for key, value in row.items()} for row in rows]
    if order_sensitive:
        return normalized
    return sorted(normalized, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))


def normalize_value(value: Any) -> str:
    if value is None:
        return "<NULL>"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def result_hash(rows: list[dict[str, Any]], order_sensitive: bool = False) -> str:
    payload = json.dumps(normalize_rows(rows, order_sensitive), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


KNOWN_ENUM_VALUES = {
    "order_status": {"pending", "paid", "completed", "cancelled"},
    "payment_status": {"success", "failed", "pending"},
    "refund_status": {"approved", "rejected", "processing"},
    "status": {"active", "inactive"},
    "event_name": {"view_product", "add_to_cart", "purchase", "search"},
}

BUSINESS_RULE_FRAGMENTS = (
    "ORDER_STATUS IN ('PAID', 'COMPLETED')",
    "PAYMENT_STATUS = 'SUCCESS'",
    "REFUND_STATUS = 'APPROVED'",
    "PRODUCTS.STATUS = 'ACTIVE'",
    "P.STATUS = 'ACTIVE'",
    "STATUS = 'ACTIVE'",
    "SUM(ORDERS.TOTAL_AMOUNT)",
    "SUM(O.TOTAL_AMOUNT)",
    "SUM(TOTAL_AMOUNT)",
)

BUSINESS_RULE_HINTS = (
    "有效",
    "GMV",
    "支付成功",
    "退款成功",
    "在售",
    "paid",
    "completed",
)


def classify_failure_categories(
    case: BenchmarkCase,
    candidate_sql: str,
    reference_sql: str,
    candidate_rows: list[dict[str, Any]] | None = None,
    reference_rows: list[dict[str, Any]] | None = None,
    execution_error: str = "",
) -> list[str]:
    categories: list[str] = []
    normalized_candidate = normalize_sql(candidate_sql).upper()
    normalized_reference = normalize_sql(reference_sql).upper()

    if execution_error:
        categories.append("execution_error")
        if is_mysql_dialect_error(execution_error, candidate_sql):
            categories.append("mysql_dialect_error")
        return categories

    if has_enum_value_error(candidate_sql):
        categories.append("enum_value_error")

    if has_business_rule_error(case, normalized_candidate, normalized_reference):
        categories.append("business_rule_error")

    if candidate_rows is not None and reference_rows is not None:
        if has_output_shape_mismatch(candidate_rows, reference_rows):
            categories.append("output_shape_mismatch")
        if (
            case.result_check.order_sensitive
            and result_hash(candidate_rows, order_sensitive=False) == result_hash(reference_rows, order_sensitive=False)
            and result_hash(candidate_rows, order_sensitive=True) != result_hash(reference_rows, order_sensitive=True)
        ):
            categories.append("order_mismatch")

    if not categories:
        categories.append("execution_error")
    return categories


def is_mysql_dialect_error(error: str, sql: str) -> bool:
    combined = f"{error}\n{sql}".upper()
    dialect_markers = (
        "SYNTAX",
        "WINDOW",
        "OVER",
        "QUALIFY",
        "ILIKE",
        "DATE_TRUNC",
        "INTERVAL '",
        "LIMIT ALL",
        "ONLY_FULL_GROUP_BY",
    )
    return any(marker in combined for marker in dialect_markers)


def has_enum_value_error(sql: str) -> bool:
    if re.search(r"'[^']*[\u4e00-\u9fff][^']*'", sql):
        return True

    normalized = normalize_sql(sql)
    comparisons = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'([^']+)'", normalized)
    for _, column, value in comparisons:
        allowed_values = KNOWN_ENUM_VALUES.get(column.lower())
        if allowed_values and value not in allowed_values:
            return True
    return False


def has_business_rule_error(case: BenchmarkCase, normalized_candidate: str, normalized_reference: str) -> bool:
    relevant = any(hint.upper() in case.user_question.upper() for hint in BUSINESS_RULE_HINTS)
    relevant = relevant or any(fragment in normalized_reference for fragment in BUSINESS_RULE_FRAGMENTS)
    if not relevant:
        return False

    reference_fragments = [fragment for fragment in BUSINESS_RULE_FRAGMENTS if fragment in normalized_reference]
    return any(fragment not in normalized_candidate for fragment in reference_fragments)


def has_output_shape_mismatch(candidate_rows: list[dict[str, Any]], reference_rows: list[dict[str, Any]]) -> bool:
    candidate_columns = row_columns(candidate_rows)
    reference_columns = row_columns(reference_rows)
    return bool(candidate_columns and reference_columns and candidate_columns != reference_columns)


def row_columns(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    if not rows:
        return ()
    return tuple(rows[0].keys())


class MySQLClient:
    def __init__(self, mysql_url: str):
        self.mysql_url = mysql_url

    def execute(self, sql: str) -> list[dict[str, Any]]:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:
            raise RuntimeError("PyMySQL is required for execution mode. Install it with `pip install PyMySQL`.") from exc

        parsed = urlparse(self.mysql_url)
        password = parsed.password or ""
        database = parsed.path.lstrip("/")
        connection = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=parsed.username or "root",
            password=password,
            database=database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            read_timeout=15,
            write_timeout=15,
            connect_timeout=5,
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
                cursor.execute(sql)
                return list(cursor.fetchall())
        finally:
            connection.close()


def evaluate_cases(
    cases: list[BenchmarkCase],
    predictions: dict[str, Prediction],
    mysql_url: str = "",
    use_reference: bool = False,
) -> BenchmarkReport:
    client = MySQLClient(mysql_url) if mysql_url else None
    scores: list[CaseScore] = []

    for case in cases:
        prediction = predictions.get(case.id)
        candidate_sql = case.reference_sql if use_reference else (prediction.sql if prediction else "")
        static_passed, safety_passed, schema_passed, errors = static_score(case, candidate_sql)
        execution_passed: bool | None = None
        result_passed: bool | None = None
        failure_categories: list[str] = []

        if not candidate_sql:
            errors.append("Missing prediction SQL")
            failure_categories.append("execution_error")
        elif client:
            try:
                candidate_rows = client.execute(candidate_sql)
                reference_rows = client.execute(case.reference_sql)
                execution_passed = True
                result_passed = result_hash(candidate_rows, case.result_check.order_sensitive) == result_hash(
                    reference_rows,
                    case.result_check.order_sensitive,
                )
                if not result_passed:
                    errors.append("Candidate result does not match reference result")
                    failure_categories.extend(
                        classify_failure_categories(case, candidate_sql, case.reference_sql, candidate_rows, reference_rows)
                    )
            except Exception as exc:
                execution_passed = False
                result_passed = False
                errors.append(f"Execution failed: {exc}")
                failure_categories.extend(
                    classify_failure_categories(case, candidate_sql, case.reference_sql, execution_error=str(exc))
                )

        scores.append(
            CaseScore(
                id=case.id,
                static_passed=static_passed,
                safety_passed=safety_passed,
                schema_passed=schema_passed,
                execution_passed=execution_passed,
                result_passed=result_passed,
                errors=errors,
                failure_categories=sorted(set(failure_categories)),
                candidate_sql=candidate_sql,
            )
        )

    return BenchmarkReport(total=len(cases), scores=scores)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MySQL sandbox SQL benchmark.")
    parser.add_argument("--cases", default="benchmarks/mysql_sandbox/cases.jsonl")
    parser.add_argument("--predictions", default="")
    parser.add_argument("--mysql-url", default="")
    parser.add_argument("--use-reference", action="store_true", help="Evaluate reference_sql as predictions.")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    predictions = load_predictions(args.predictions) if args.predictions else {}
    report = evaluate_cases(cases, predictions, mysql_url=args.mysql_url, use_reference=args.use_reference)
    payload = {
        "summary": report.summary(),
        "cases": [score.__dict__ for score in report.scores],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if not payload["summary"]["failed_case_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
