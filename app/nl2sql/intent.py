from dataclasses import dataclass, field
import re


@dataclass
class NL2SQLIntent:
    is_query: bool
    user_input: str = ""
    database_keyword: str = ""
    table_hint: str = ""
    table_prefix: str = ""
    field_hints: list[str] = field(default_factory=list)
    operation: str = "select"
    limit: int | None = None
    time_days: int | None = None
    needs_clarification: bool = False
    clarification_question: str = ""


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

    return NL2SQLIntent(
        is_query=is_query,
        user_input=user_input,
        database_keyword=database_keyword,
        table_hint=table_hint,
        table_prefix=table_prefix,
        field_hints=field_hints,
        operation=operation,
        limit=default_limit_for_operation(operation, user_input),
        time_days=infer_time_days(user_input),
    )
