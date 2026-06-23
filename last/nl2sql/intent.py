from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any
import re


@dataclass
class FieldHint:
    text: str
    role: str = ""


@dataclass
class DimensionSpec:
    field_hint: str
    resolved_field: str = ""


@dataclass
class MeasureSpec:
    type: str = "count"
    field_hint: str = ""
    expression: str = ""
    alias: str = "cnt"


@dataclass
class FilterSpec:
    field_hint: str
    operator: str
    value: str | int | float | bool | None = None
    resolved_field: str = ""


@dataclass
class TimeRangeSpec:
    type: str = ""
    value: int | str | None = None
    unit: str = ""
    field_hint: str = ""
    resolved_field: str = ""


@dataclass
class OrderBySpec:
    field_hint: str
    direction: str = "desc"
    resolved_field: str = ""


@dataclass
class NL2SQLIntent:
    is_query: bool
    user_input: str = ""
    query_pattern: str = ""
    database_keyword: str = ""
    table_hint: str = ""
    table_prefix: str = ""
    field_hints: list[str] = field(default_factory=list)
    structured_field_hints: list[FieldHint] = field(default_factory=list)
    dimensions: list[DimensionSpec] = field(default_factory=list)
    measure: MeasureSpec | None = None
    filters: list[FilterSpec] = field(default_factory=list)
    time_range: TimeRangeSpec | None = None
    order_by: list[OrderBySpec] = field(default_factory=list)
    operation: str = "select"
    limit: int | None = None
    time_days: int | None = None
    needs_clarification: bool = False
    clarification_question: str = ""


OPERATION_TO_QUERY_PATTERN = {
    "select": "detail_query",
    "recent": "detail_query",
    "count": "single_table_count",
    "table_counts": "table_count_batch",
    "most_frequent": "top_n_frequency",
    "ranking_count": "group_count_rank",
    "field_count": "field_count",
}

QUERY_PATTERN_TO_OPERATION = {
    "detail_query": "select",
    "single_table_count": "count",
    "table_count_batch": "table_counts",
    "top_n_frequency": "most_frequent",
    "group_count_rank": "ranking_count",
    "time_series_trend": "select",
    "field_count": "field_count",
    "schema_explore": "select",
}


def operation_to_query_pattern(operation: str) -> str:
    return OPERATION_TO_QUERY_PATTERN.get(operation, "detail_query")


def query_pattern_to_operation(query_pattern: str) -> str:
    return QUERY_PATTERN_TO_OPERATION.get(query_pattern, "select")


def normalize_intent(intent: NL2SQLIntent) -> NL2SQLIntent:
    if not intent.query_pattern:
        intent.query_pattern = operation_to_query_pattern(intent.operation)
    if not intent.operation or intent.operation == "select":
        intent.operation = query_pattern_to_operation(intent.query_pattern)
    if intent.field_hints and not intent.structured_field_hints:
        role = "dimension" if intent.query_pattern in {"top_n_frequency", "group_count_rank"} else ""
        intent.structured_field_hints = [FieldHint(text=hint, role=role) for hint in intent.field_hints]
    if intent.field_hints and not intent.dimensions and intent.query_pattern in {"top_n_frequency", "group_count_rank"}:
        intent.dimensions = [DimensionSpec(field_hint=hint) for hint in intent.field_hints[:1]]
    if intent.query_pattern in {"top_n_frequency", "group_count_rank", "single_table_count"} and intent.measure is None:
        alias = "total" if intent.query_pattern == "single_table_count" else "cnt"
        intent.measure = MeasureSpec(type="count", expression="COUNT(*)", alias=alias)
    if intent.time_days is not None and intent.time_range is None:
        intent.time_range = TimeRangeSpec(type="relative", value=intent.time_days, unit="day")
    if intent.time_range and intent.time_days is None and intent.time_range.type == "relative" and intent.time_range.unit == "day":
        if isinstance(intent.time_range.value, int):
            intent.time_days = intent.time_range.value
    return intent


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def intent_to_dict(intent: NL2SQLIntent) -> dict[str, Any]:
    return _to_jsonable(intent)


def normalize_identifier_hint(value: str) -> str:
    value = value.strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[\s\-]+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return value.strip("_").lower()


def infer_database_keyword(user_input: str) -> str:
    patterns = [
        r"查查\s*([A-Za-z][A-Za-z0-9_-]*)\s*数据库",
        r"看看\s*([A-Za-z][A-Za-z0-9_-]*)\s*数据库",
        r"([A-Za-z][A-Za-z0-9_-]*)\s*数据库",
        r"([A-Za-z][A-Za-z0-9_-]*)\s*库",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            return match.group(1)
    return ""


def infer_table_hint(user_input: str) -> str:
    patterns = [
        r"数据库中\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*表",
        r"库中\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*表",
        r"([A-Za-z][A-Za-z0-9_\-\s]*?)\s*表",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            return normalize_identifier_hint(match.group(1))
    return ""


def infer_table_prefix(user_input: str) -> str:
    patterns = [
        r"数据库中\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*各个表",
        r"库中\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*各个表",
        r"([A-Za-z][A-Za-z0-9_\-\s]*?)\s*各个表",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            return normalize_identifier_hint(match.group(1))
    return ""


def infer_field_hints(user_input: str) -> list[str]:
    lower_input = user_input.lower()
    hints: list[str] = []
    for match in re.finditer(r"出现最多的\s*([A-Za-z][A-Za-z0-9_]*)", lower_input):
        hints.append(normalize_identifier_hint(match.group(1)))
    if not hints:
        for field in re.findall(r"[A-Za-z][A-Za-z0-9_]*", user_input):
            normalized = normalize_identifier_hint(field)
            if normalized not in {"select", "show", "from", "where", "limit"}:
                hints.append(normalized)
    return list(dict.fromkeys(hints))


def infer_operation(user_input: str) -> str:
    if "字段" in user_input and any(word in user_input for word in ("多少", "几个", "有多少")):
        return "field_count"
    if "各个表" in user_input and any(word in user_input for word in ("多少条", "多少行", "数据量", "条数据")):
        return "table_counts"
    if "排行" in user_input and any(word in user_input for word in ("次数", "数量", "告警")):
        return "ranking_count"
    if "最多" in user_input or "最高" in user_input or "第一" in user_input:
        return "most_frequent"
    if "总数" in user_input or "多少" in user_input:
        return "count"
    if "最近" in user_input:
        return "recent"
    return "select"


CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def parse_requested_limit(user_input: str) -> int | None:
    patterns = [
        r"(?:前|最多的?|最高的?|排名前)\s*(\d+)\s*(?:个|条|名)?",
        r"(?:前|最多的?|最高的?|排名前)\s*([一二两三四五六七八九十])\s*(?:个|条|名)?",
        r"(\d+)\s*(?:个|条|名)",
        r"([一二两三四五六七八九十])\s*(?:个|条|名)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if not match:
            continue
        value = match.group(1)
        if value.isdigit():
            return int(value)
        return CHINESE_NUMBERS.get(value)
    return None


def default_limit_for_operation(operation: str, user_input: str) -> int:
    requested_limit = parse_requested_limit(user_input)
    if requested_limit:
        return requested_limit
    if operation == "most_frequent":
        if any(word in user_input for word in ("一个", "第一", "最多的")):
            return 1
        return 20
    if operation == "ranking_count":
        return 20
    if operation == "field_count":
        return 1
    if operation == "count":
        return 1
    if operation == "table_counts":
        return 100
    return 100


def infer_time_days(user_input: str) -> int | None:
    match = re.search(r"最近\s*(\d+)\s*天", user_input)
    if match:
        return int(match.group(1))
    match = re.search(r"最近\s*([一二两三四五六七八九十])\s*天", user_input)
    if match:
        return CHINESE_NUMBERS.get(match.group(1))
    return None


def parse_nl2sql_intent(user_input: str) -> NL2SQLIntent:
    operation = infer_operation(user_input)
    table_hint = infer_table_hint(user_input)
    table_prefix = infer_table_prefix(user_input)
    database_keyword = infer_database_keyword(user_input)
    field_hints = infer_field_hints(user_input)
    is_query = bool(
        table_hint
        or table_prefix
        or operation in {"most_frequent", "count", "recent", "table_counts", "ranking_count", "field_count"}
    )

    return normalize_intent(NL2SQLIntent(
        is_query=is_query,
        user_input=user_input,
        database_keyword=database_keyword,
        table_hint=table_hint,
        table_prefix=table_prefix,
        field_hints=field_hints,
        operation=operation,
        limit=default_limit_for_operation(operation, user_input),
        time_days=infer_time_days(user_input),
    ))
