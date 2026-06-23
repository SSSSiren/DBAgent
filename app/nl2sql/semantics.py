from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import settings
from app.nl2sql.schema import ColumnSchema


@dataclass(frozen=True)
class SemanticContext:
    schema_id: int | None = None
    database: str = ""
    domain: str = ""
    tables: tuple[str, ...] = ()
    columns: tuple[ColumnSchema, ...] = ()
    user_input: str = ""
    sample_values: dict[str, tuple[str, ...]] = field(default_factory=dict)
    history_sql: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticRule:
    name: str
    sql: str
    tables: tuple[str, ...] = ()
    description: str = ""
    domain: str = ""
    schema_ids: tuple[int, ...] = ()
    source: str = ""
    required_columns: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 1.0
    status: str = "system"  # system, confirmed, candidate
    requires_confirmation: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticRule":
        return cls(
            name=str(payload.get("name") or ""),
            sql=str(payload.get("sql") or ""),
            tables=tuple(str(table) for table in payload.get("tables") or ()),
            description=str(payload.get("description") or ""),
            domain=str(payload.get("domain") or ""),
            schema_ids=tuple(int(schema_id) for schema_id in payload.get("schema_ids") or ()),
            source=str(payload.get("source") or ""),
            required_columns=tuple(str(column) for column in payload.get("required_columns") or ()),
            confidence=float(payload.get("confidence", 1.0)),
            status=str(payload.get("status") or "system"),
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sql": self.sql,
            "tables": list(self.tables),
            "description": self.description,
            "domain": self.domain,
            "schema_ids": list(self.schema_ids),
            "source": self.source,
            "required_columns": list(self.required_columns),
            "confidence": self.confidence,
            "status": self.status,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass(frozen=True)
class SemanticResolution:
    rules: tuple[SemanticRule, ...] = ()
    candidates: tuple[SemanticRule, ...] = ()


class SemanticProvider(Protocol):
    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        ...


SANDBOX_SEMANTIC_RULES: tuple[SemanticRule, ...] = (
    SemanticRule(
        name="有效订单",
        sql="order_status IN ('paid', 'completed')",
        tables=("orders",),
        description="paid 和 completed 订单才计入有效订单。",
        domain="mysql_sandbox",
        source="static_sandbox",
        required_columns=("order_status",),
    ),
    SemanticRule(
        name="支付成功",
        sql="payment_status = 'success'",
        tables=("payments",),
        description="支付成功状态使用 payment_status 的真实枚举值 success。",
        domain="mysql_sandbox",
        source="static_sandbox",
        required_columns=("payment_status",),
    ),
    SemanticRule(
        name="退款成功",
        sql="refund_status = 'approved'",
        tables=("refunds",),
        description="退款成功状态使用 refund_status 的真实枚举值 approved。",
        domain="mysql_sandbox",
        source="static_sandbox",
        required_columns=("refund_status",),
    ),
    SemanticRule(
        name="在售商品",
        sql="products.status = 'active'",
        tables=("products",),
        description="在售商品状态使用 products.status 的真实枚举值 active。",
        domain="mysql_sandbox",
        source="static_sandbox",
        required_columns=("status",),
    ),
    SemanticRule(
        name="GMV",
        sql="SUM(orders.total_amount)",
        tables=("orders",),
        description="GMV 使用订单总金额 total_amount 求和。",
        domain="mysql_sandbox",
        source="static_sandbox",
        required_columns=("total_amount",),
    ),
)


class EmptySemanticProvider:
    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        return []


class StaticSandboxSemanticProvider:
    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        if context.domain != "mysql_sandbox":
            return []
        return list(SANDBOX_SEMANTIC_RULES)


class CompositeSemanticProvider:
    def __init__(self, providers: list[SemanticProvider]):
        self.providers = providers

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        rules: list[SemanticRule] = []
        for provider in self.providers:
            rules.extend(await provider.get_rules(context))
        return dedupe_rules(rules)


class FileSemanticProvider:
    def __init__(self, path: str):
        self.path = path

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        if not self.path:
            return []
        path = Path(self.path)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rules") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []
        return [SemanticRule.from_dict(row) for row in rows if isinstance(row, dict)]


class UserMemorySemanticProvider(FileSemanticProvider):
    pass


class HistorySQLSemanticProvider(FileSemanticProvider):
    pass


class SchemaInferenceSemanticProvider:
    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        table = context.tables[0] if context.tables else ""
        column_names = {column.name.lower() for column in context.columns}
        samples = {key.lower(): {value.lower() for value in values} for key, values in context.sample_values.items()}
        rules: list[SemanticRule] = []

        if "total_amount" in column_names and any(word in context.user_input.upper() for word in ("GMV", "销售额", "累计消费")):
            rules.append(
                candidate_rule(
                    name="GMV",
                    sql=qualified_sql(table, "SUM", "total_amount"),
                    table=table,
                    description="根据 total_amount 字段名推断的 GMV 候选口径，需用户确认。",
                    required_columns=("total_amount",),
                    confidence=0.72,
                    source="schema_inference",
                )
            )

        if "order_status" in column_names and "有效" in context.user_input:
            sample_values = samples.get("order_status", set())
            confidence = 0.88 if {"paid", "completed"}.issubset(sample_values) else 0.68
            rules.append(
                candidate_rule(
                    name="有效订单",
                    sql="order_status IN ('paid', 'completed')",
                    table=table,
                    description="根据 order_status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("order_status",),
                    confidence=confidence,
                    source="sample_value_inference" if sample_values else "schema_inference",
                )
            )

        if "payment_status" in column_names and "支付成功" in context.user_input:
            confidence = 0.9 if "success" in samples.get("payment_status", set()) else 0.7
            rules.append(
                candidate_rule(
                    name="支付成功",
                    sql="payment_status = 'success'",
                    table=table,
                    description="根据 payment_status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("payment_status",),
                    confidence=confidence,
                    source="sample_value_inference" if context.sample_values else "schema_inference",
                )
            )

        if "refund_status" in column_names and "退款成功" in context.user_input:
            confidence = 0.9 if "approved" in samples.get("refund_status", set()) else 0.7
            rules.append(
                candidate_rule(
                    name="退款成功",
                    sql="refund_status = 'approved'",
                    table=table,
                    description="根据 refund_status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("refund_status",),
                    confidence=confidence,
                    source="sample_value_inference" if context.sample_values else "schema_inference",
                )
            )

        if "status" in column_names and "在售" in context.user_input:
            confidence = 0.9 if "active" in samples.get("status", set()) else 0.7
            rules.append(
                candidate_rule(
                    name="在售商品",
                    sql=f"{table}.status = 'active'" if table else "status = 'active'",
                    table=table,
                    description="根据 status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("status",),
                    confidence=confidence,
                    source="sample_value_inference" if context.sample_values else "schema_inference",
                )
            )

        return rules


class HTTPSemanticProvider:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        if not self.base_url:
            return []
        payload = {
            "schema_id": context.schema_id,
            "database": context.database,
            "domain": context.domain,
            "tables": list(context.tables),
            "columns": [column.name for column in context.columns],
        }
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(f"{self.base_url}/semantic-rules", json=payload)
            response.raise_for_status()
        rows = response.json().get("rules", [])
        return [SemanticRule.from_dict(row) for row in rows if isinstance(row, dict)]


def build_semantic_provider() -> SemanticProvider:
    provider = settings.SEMANTIC_PROVIDER.lower()
    if provider == "auto":
        providers: list[SemanticProvider] = []
        if settings.SEMANTIC_SERVICE_URL:
            providers.append(HTTPSemanticProvider(settings.SEMANTIC_SERVICE_URL))
        if settings.SEMANTIC_RULES_PATH:
            providers.append(FileSemanticProvider(settings.SEMANTIC_RULES_PATH))
        if settings.SEMANTIC_USER_RULES_PATH:
            providers.append(UserMemorySemanticProvider(settings.SEMANTIC_USER_RULES_PATH))
        if settings.SEMANTIC_HISTORY_RULES_PATH:
            providers.append(HistorySQLSemanticProvider(settings.SEMANTIC_HISTORY_RULES_PATH))
        providers.append(SchemaInferenceSemanticProvider())
        return CompositeSemanticProvider(providers)
    if provider == "static_sandbox":
        return StaticSandboxSemanticProvider()
    if provider == "file":
        return FileSemanticProvider(settings.SEMANTIC_RULES_PATH)
    if provider == "http":
        return HTTPSemanticProvider(settings.SEMANTIC_SERVICE_URL)
    if provider == "schema_inference":
        return SchemaInferenceSemanticProvider()
    return EmptySemanticProvider()


async def get_semantic_rules(context: SemanticContext, provider: SemanticProvider | None = None) -> list[SemanticRule]:
    return list((await resolve_semantics(context, provider=provider)).rules)


async def get_semantic_candidates(context: SemanticContext, provider: SemanticProvider | None = None) -> list[SemanticRule]:
    return list((await resolve_semantics(context, provider=provider)).candidates)


async def resolve_semantics(context: SemanticContext, provider: SemanticProvider | None = None) -> SemanticResolution:
    selected_provider = provider or build_semantic_provider()
    rules = await selected_provider.get_rules(context)
    filtered = filter_rules_for_context(rules, context)
    return SemanticResolution(
        rules=tuple(injectable_rules(filtered)),
        candidates=tuple(candidate_rules(filtered)),
    )


def filter_rules_for_context(rules: list[SemanticRule], context: SemanticContext) -> list[SemanticRule]:
    table_names = {table.lower() for table in context.tables}
    column_names = {column.name.lower() for column in context.columns}
    filtered: list[SemanticRule] = []

    for rule in rules:
        if rule.domain and context.domain and rule.domain != context.domain:
            continue
        if rule.schema_ids and context.schema_id not in rule.schema_ids:
            continue
        if rule.tables and table_names and not any(table.lower() in table_names for table in rule.tables):
            continue
        if context.columns and not rule_columns_exist(rule, column_names):
            continue
        filtered.append(rule)
    return filtered


def injectable_rules(rules: list[SemanticRule]) -> list[SemanticRule]:
    return [
        rule
        for rule in rules
        if rule.status in {"system", "confirmed"} and not rule.requires_confirmation and rule.confidence >= 0.85
    ]


def candidate_rules(rules: list[SemanticRule]) -> list[SemanticRule]:
    return [rule for rule in rules if rule not in injectable_rules(rules)]


def candidate_rule(
    name: str,
    sql: str,
    table: str,
    description: str,
    required_columns: tuple[str, ...],
    confidence: float,
    source: str,
) -> SemanticRule:
    return SemanticRule(
        name=name,
        sql=sql,
        tables=(table,) if table else (),
        description=description,
        source=source,
        required_columns=required_columns,
        confidence=confidence,
        status="candidate",
        requires_confirmation=True,
    )


def qualified_sql(table: str, function: str, column: str) -> str:
    target = f"{table}.{column}" if table else column
    return f"{function}({target})"


def dedupe_rules(rules: list[SemanticRule]) -> list[SemanticRule]:
    deduped: dict[tuple[str, str, tuple[str, ...]], SemanticRule] = {}
    for rule in rules:
        key = (rule.name, rule.sql, rule.tables)
        previous = deduped.get(key)
        if previous is None or rule_rank(rule) > rule_rank(previous):
            deduped[key] = rule
    return list(deduped.values())


def rule_rank(rule: SemanticRule) -> tuple[int, float]:
    status_rank = {"system": 3, "confirmed": 2, "candidate": 1}.get(rule.status, 0)
    return status_rank, rule.confidence


def rule_columns_exist(rule: SemanticRule, column_names: set[str]) -> bool:
    required_columns = {column.lower() for column in rule.required_columns}
    required_columns.update(extract_unqualified_columns(rule.sql))
    return required_columns.issubset(column_names)


def extract_unqualified_columns(sql: str) -> set[str]:
    known_functions = {"in", "sum", "count", "avg", "min", "max", "coalesce", "date", "date_format"}
    identifiers = {identifier.lower() for identifier in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql)}
    quoted_values = {value.lower() for value in re.findall(r"'([^']*)'", sql)}
    table_qualifiers = {table.lower() for table in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.", sql)}
    qualified_columns = {column.lower() for column in re.findall(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\b", sql)}
    return identifiers - quoted_values - table_qualifiers - known_functions | qualified_columns


def render_semantic_rules_for_prompt(rules: list[SemanticRule] | tuple[SemanticRule, ...] | None = None) -> str:
    selected_rules = list(rules) if rules is not None else []
    if not selected_rules:
        return "无"

    lines = []
    for rule in selected_rules:
        scope = ", ".join(rule.tables) if rule.tables else "全局"
        source = f"；来源：{rule.source}" if rule.source else ""
        description = f"；{rule.description}" if rule.description else ""
        lines.append(f"- {rule.name}（适用表：{scope}）：{rule.sql}{description}{source}")
    return "\n".join(lines)


def render_semantic_candidates_for_prompt(rules: list[SemanticRule] | tuple[SemanticRule, ...] | None = None) -> str:
    selected_rules = list(rules) if rules is not None else []
    if not selected_rules:
        return "无"

    lines = []
    for rule in selected_rules:
        scope = ", ".join(rule.tables) if rule.tables else "全局"
        source = f"；来源：{rule.source}" if rule.source else ""
        lines.append(
            f"- {rule.name}（适用表：{scope}，置信度：{rule.confidence:.2f}）：{rule.sql}；需用户确认，不能直接用于 SQL{source}"
        )
    return "\n".join(lines)


def confirm_semantic_rule(rule: SemanticRule, context: SemanticContext) -> SemanticRule:
    return SemanticRule(
        name=rule.name,
        sql=rule.sql,
        tables=rule.tables or context.tables,
        description=rule.description,
        domain=rule.domain or context.domain,
        schema_ids=rule.schema_ids or ((context.schema_id,) if context.schema_id is not None else ()),
        source="user_confirmed",
        required_columns=rule.required_columns,
        confidence=1.0,
        status="confirmed",
        requires_confirmation=False,
    )


def parse_custom_semantic_rule(message: str, context: SemanticContext) -> SemanticRule | None:
    text = message.strip().rstrip("。.")
    patterns = [
        r"^(?P<name>[\u4e00-\u9fffA-Za-z0-9_ -]{1,40}?)(?:其实是|就是|是|=|：|:)\s*(?P<sql>.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if not match:
            continue
        name = match.group("name").strip()
        sql = match.group("sql").strip()
        if not name or not sql or not is_safe_semantic_sql_fragment(sql):
            return None
        candidate = SemanticRule(
            name=name,
            sql=sql,
            tables=context.tables,
            description=f"用户确认的业务口径：{name}",
            domain=context.domain,
            schema_ids=((context.schema_id,) if context.schema_id is not None else ()),
            source="user_confirmed",
            required_columns=tuple(sorted(extract_unqualified_columns(sql))),
            confidence=1.0,
            status="confirmed",
            requires_confirmation=False,
        )
        if context.columns and not rule_columns_exist(candidate, {column.name.lower() for column in context.columns}):
            return None
        return candidate
    return None


def is_safe_semantic_sql_fragment(sql: str) -> bool:
    normalized = sql.strip()
    if not normalized or ";" in normalized:
        return False
    upper = normalized.upper()
    blocked = {
        "SELECT",
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
    }
    tokens = set(re.findall(r"\b[A-Z_]+\b", upper))
    return not any(token in tokens for token in blocked)


def save_user_semantic_rules(rules: list[SemanticRule], path: str | None = None) -> None:
    target = Path(path or settings.SEMANTIC_USER_RULES_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_rules: list[SemanticRule] = []
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        rows = payload.get("rules") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            existing_rules = [SemanticRule.from_dict(row) for row in rows if isinstance(row, dict)]

    merged = dedupe_rules([*existing_rules, *rules])
    target.write_text(
        json.dumps({"rules": [rule.to_dict() for rule in merged]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def semantic_rule_from_pending(payload: dict[str, Any]) -> SemanticRule:
    return SemanticRule.from_dict(payload)
