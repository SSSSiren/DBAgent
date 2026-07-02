"""
语义规则引擎 — 业务概念  SQL 条件的映射

参考 DBAgent 的 app/nl2sql/semantics.py

核心概念：
- SemanticRule: 一个业务概念（如"有效订单"）对应一个 SQL 条件（如 status IN ('paid', 'completed')）
- SemanticProvider: 提供语义规则的来源（文件、静态规则、Schema 推断等）
- SemanticResolution: 规则解析结果，分为已确认规则和候选规则
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings
from app.nl2sql.schema import ColumnSchema


# ========== 数据模型 ==========


@dataclass(frozen=True)
class SemanticContext:
    """语义规则查询上下文"""

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
    """语义规则：业务概念 → SQL 条件"""

    name: str
    sql: str
    tables: tuple[str, ...] = ()
    description: str = ""
    domain: str = ""
    schema_ids: tuple[int, ...] = ()
    source: str = ""
    required_columns: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 1.0
    status: str = "system"  # system / confirmed / candidate
    requires_confirmation: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticRule":
        return cls(
            name=str(payload.get("name") or ""),
            sql=str(payload.get("sql") or ""),
            tables=tuple(str(t) for t in payload.get("tables") or ()),
            description=str(payload.get("description") or ""),
            domain=str(payload.get("domain") or ""),
            schema_ids=tuple(int(s) for s in payload.get("schema_ids") or ()),
            source=str(payload.get("source") or ""),
            required_columns=tuple(str(c) for c in payload.get("required_columns") or ()),
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
    """语义规则解析结果"""

    rules: tuple[SemanticRule, ...] = ()        # 已确认的规则，可直接用于 SQL 生成
    candidates: tuple[SemanticRule, ...] = ()    # 候选规则，需用户确认


# ========== Provider 接口 ==========


class SemanticProvider(Protocol):
    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        ...


# ========== 静态沙箱规则 ==========

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


# ========== Provider 实现 ==========


class EmptySemanticProvider:
    """空提供者：不返回任何规则"""

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        return []


class StaticSandboxSemanticProvider:
    """静态沙箱规则提供者"""

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        if context.domain != "mysql_sandbox":
            return []
        return list(SANDBOX_SEMANTIC_RULES)


class FileSemanticProvider:
    """从 JSON 文件加载规则"""

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


class SchemaInferenceSemanticProvider:
    """基于 Schema 字段名和样例值推断语义规则"""

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        table = context.tables[0] if context.tables else ""
        column_names = {column.name.lower() for column in context.columns}
        samples = {
            key.lower(): {value.lower() for value in values}
            for key, values in context.sample_values.items()
        }
        rules: list[SemanticRule] = []

        # GMV 推断
        if "total_amount" in column_names and any(
            word in context.user_input.upper()
            for word in ("GMV", "销售额", "累计消费")
        ):
            rules.append(
                _candidate_rule(
                    name="GMV",
                    sql=_qualified_sql(table, "SUM", "total_amount"),
                    table=table,
                    description="根据 total_amount 字段名推断的 GMV 候选口径，需用户确认。",
                    required_columns=("total_amount",),
                    confidence=0.72,
                    source="schema_inference",
                )
            )

        # 有效订单推断
        if "order_status" in column_names and "有效" in context.user_input:
            sample_values = samples.get("order_status", set())
            confidence = 0.88 if {"paid", "completed"}.issubset(sample_values) else 0.68
            rules.append(
                _candidate_rule(
                    name="有效订单",
                    sql="order_status IN ('paid', 'completed')",
                    table=table,
                    description="根据 order_status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("order_status",),
                    confidence=confidence,
                    source="sample_value_inference" if sample_values else "schema_inference",
                )
            )

        # 支付成功推断
        if "payment_status" in column_names and "支付成功" in context.user_input:
            confidence = 0.9 if "success" in samples.get("payment_status", set()) else 0.7
            rules.append(
                _candidate_rule(
                    name="支付成功",
                    sql="payment_status = 'success'",
                    table=table,
                    description="根据 payment_status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("payment_status",),
                    confidence=confidence,
                    source="sample_value_inference" if context.sample_values else "schema_inference",
                )
            )

        # 退款成功推断
        if "refund_status" in column_names and "退款成功" in context.user_input:
            confidence = 0.9 if "approved" in samples.get("refund_status", set()) else 0.7
            rules.append(
                _candidate_rule(
                    name="退款成功",
                    sql="refund_status = 'approved'",
                    table=table,
                    description="根据 refund_status 字段和样例值推断的候选口径，需用户确认。",
                    required_columns=("refund_status",),
                    confidence=confidence,
                    source="sample_value_inference" if context.sample_values else "schema_inference",
                )
            )

        # 在售商品推断
        if "status" in column_names and "在售" in context.user_input:
            confidence = 0.9 if "active" in samples.get("status", set()) else 0.7
            rules.append(
                _candidate_rule(
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


class CompositeSemanticProvider:
    """组合多个 Provider，按优先级合并规则"""

    def __init__(self, providers: list[SemanticProvider]):
        self.providers = providers

    async def get_rules(self, context: SemanticContext) -> list[SemanticRule]:
        rules: list[SemanticRule] = []
        for provider in self.providers:
            rules.extend(await provider.get_rules(context))
        return _dedupe_rules(rules)


# ========== Provider 工厂 ==========


def build_semantic_provider() -> SemanticProvider:
    """根据配置构建语义规则提供者"""
    settings = get_settings()
    provider = settings.semantic_provider.lower()

    if provider == "auto":
        providers: list[SemanticProvider] = []
        if settings.semantic_rules_path:
            providers.append(FileSemanticProvider(settings.semantic_rules_path))
        if settings.semantic_user_rules_path:
            providers.append(FileSemanticProvider(settings.semantic_user_rules_path))
        providers.append(SchemaInferenceSemanticProvider())
        return CompositeSemanticProvider(providers)

    if provider == "static_sandbox":
        return StaticSandboxSemanticProvider()

    if provider == "file":
        return FileSemanticProvider(settings.semantic_rules_path)

    if provider == "schema_inference":
        return SchemaInferenceSemanticProvider()

    return EmptySemanticProvider()


# ========== 规则过滤与解析 ==========


async def resolve_semantics(
    context: SemanticContext, provider: SemanticProvider | None = None
) -> SemanticResolution:
    """解析语义规则，返回已确认规则和候选规则"""
    selected_provider = provider or build_semantic_provider()
    rules = await selected_provider.get_rules(context)
    filtered = _filter_rules_for_context(rules, context)
    return SemanticResolution(
        rules=tuple(_injectable_rules(filtered)),
        candidates=tuple(_candidate_rules(filtered)),
    )


def _filter_rules_for_context(
    rules: list[SemanticRule], context: SemanticContext
) -> list[SemanticRule]:
    """根据上下文过滤规则"""
    table_names = {table.lower() for table in context.tables}
    column_names = {column.name.lower() for column in context.columns}
    filtered: list[SemanticRule] = []

    for rule in rules:
        if rule.domain and context.domain and rule.domain != context.domain:
            continue
        if rule.schema_ids and context.schema_id not in rule.schema_ids:
            continue
        if rule.tables and table_names and not any(
            t.lower() in table_names for t in rule.tables
        ):
            continue
        if context.columns and not _rule_columns_exist(rule, column_names):
            continue
        filtered.append(rule)
    return filtered


def _injectable_rules(rules: list[SemanticRule]) -> list[SemanticRule]:
    """筛选可直接注入 SQL 生成的规则（已确认、高置信度）"""
    return [
        rule
        for rule in rules
        if rule.status in {"system", "confirmed"}
        and not rule.requires_confirmation
        and rule.confidence >= 0.85
    ]


def _candidate_rules(rules: list[SemanticRule]) -> list[SemanticRule]:
    """筛选候选规则（需用户确认）"""
    return [rule for rule in rules if rule not in _injectable_rules(rules)]


def _rule_columns_exist(rule: SemanticRule, column_names: set[str]) -> bool:
    """检查规则所需的列是否存在于表结构中"""
    required = {column.lower() for column in rule.required_columns}
    required.update(_extract_unqualified_columns(rule.sql))
    return required.issubset(column_names)


def _extract_unqualified_columns(sql: str) -> set[str]:
    """从 SQL 片段中提取未限定的列名"""
    known_functions = {
        "in", "sum", "count", "avg", "min", "max",
        "coalesce", "date", "date_format",
    }
    identifiers = {
        i.lower() for i in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql)
    }
    quoted_values = {
        v.lower() for v in re.findall(r"'([^']*)'", sql)
    }
    table_qualifiers = {
        t.lower() for t in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.", sql)
    }
    qualified_columns = {
        c.lower() for c in re.findall(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\b", sql)
    }
    return identifiers - quoted_values - table_qualifiers - known_functions | qualified_columns


# ========== 辅助函数 ==========


def _candidate_rule(
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


def _qualified_sql(table: str, function: str, column: str) -> str:
    target = f"{table}.{column}" if table else column
    return f"{function}({target})"


def _dedupe_rules(rules: list[SemanticRule]) -> list[SemanticRule]:
    """去重，保留高优先级规则"""
    deduped: dict[tuple[str, str, tuple[str, ...]], SemanticRule] = {}
    for rule in rules:
        key = (rule.name, rule.sql, rule.tables)
        previous = deduped.get(key)
        if previous is None or _rule_rank(rule) > _rule_rank(previous):
            deduped[key] = rule
    return list(deduped.values())


def _rule_rank(rule: SemanticRule) -> tuple[int, float]:
    status_rank = {"system": 3, "confirmed": 2, "candidate": 1}.get(rule.status, 0)
    return status_rank, rule.confidence


# ========== Prompt 渲染 ==========


def render_semantic_rules_for_prompt(
    rules: list[SemanticRule] | tuple[SemanticRule, ...] | None = None,
) -> str:
    """渲染已确认的语义规则为 prompt 文本"""
    selected = list(rules) if rules is not None else []
    if not selected:
        return "无"

    lines = []
    for rule in selected:
        scope = ", ".join(rule.tables) if rule.tables else "全局"
        source = f"；来源：{rule.source}" if rule.source else ""
        description = f"；{rule.description}" if rule.description else ""
        lines.append(
            f"- {rule.name}（适用表：{scope}）：{rule.sql}{description}{source}"
        )
    return "\n".join(lines)


def render_semantic_candidates_for_prompt(
    rules: list[SemanticRule] | tuple[SemanticRule, ...] | None = None,
) -> str:
    """渲染候选语义规则为 prompt 文本"""
    selected = list(rules) if rules is not None else []
    if not selected:
        return "无"

    lines = []
    for rule in selected:
        scope = ", ".join(rule.tables) if rule.tables else "全局"
        source = f"；来源：{rule.source}" if rule.source else ""
        lines.append(
            f"- {rule.name}（适用表：{scope}，置信度：{rule.confidence:.2f}）："
            f"{rule.sql}；需用户确认，不能直接用于 SQL{source}"
        )
    return "\n".join(lines)