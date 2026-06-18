from dataclasses import dataclass
from difflib import SequenceMatcher

from app.nl2sql.intent import normalize_identifier_hint


@dataclass
class ResolveResult:
    value: str | int | None
    candidates: list
    needs_clarification: bool = False
    question: str = ""


def database_score(database: dict, keyword: str) -> int:
    keyword_lower = keyword.lower()
    if not keyword_lower:
        return 0
    if str(database.get("instanceName", "")).lower() == keyword_lower:
        return 100
    if str(database.get("schemaName", "")).lower() == keyword_lower:
        return 90
    if keyword_lower in str(database.get("searchName", "")).lower():
        return 80
    if keyword_lower in str(database.get("instanceName", "")).lower():
        return 70
    if keyword_lower in str(database.get("schemaName", "")).lower():
        return 60
    return 0


def resolve_database_candidate(databases: list[dict], keyword: str) -> ResolveResult:
    if not databases:
        return ResolveResult(None, [], True, f"没有找到与 {keyword} 匹配的数据库。")

    scored = [(database_score(database, keyword), database) for database in databases]
    scored = [(score, database) for score, database in scored if score > 0]
    if not scored:
        return ResolveResult(None, databases, True, f"没有找到与 {keyword} 高置信匹配的数据库。")

    best_score = max(score for score, _ in scored)
    best = [database for score, database in scored if score == best_score]
    if len(best) == 1:
        return ResolveResult(best[0].get("schemaId"), best)

    names = ", ".join(f"{item.get('schemaName')}@{item.get('instanceName')}" for item in best)
    return ResolveResult(None, best, True, f"找到多个匹配数据库，请选择一个：{names}")


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def resolve_table_candidate(table_names: list[str], table_hint: str) -> ResolveResult:
    normalized_hint = normalize_identifier_hint(table_hint)
    if not normalized_hint:
        return ResolveResult(None, table_names, True, "请提供要查询的表名。")

    normalized_map = {normalize_identifier_hint(name): name for name in table_names}
    if normalized_hint in normalized_map:
        return ResolveResult(normalized_map[normalized_hint], [normalized_map[normalized_hint]])

    suffix_matches = [name for name in table_names if normalize_identifier_hint(name).endswith(normalized_hint)]
    if len(suffix_matches) == 1:
        return ResolveResult(suffix_matches[0], suffix_matches)

    scored = sorted(
        ((similarity(normalized_hint, normalize_identifier_hint(name)), name) for name in table_names),
        reverse=True,
    )
    best_score, best_name = scored[0] if scored else (0.0, "")
    if best_score >= 0.92:
        return ResolveResult(best_name, [best_name])

    candidates = [name for score, name in scored[:5] if score >= 0.65]
    if candidates:
        return ResolveResult(None, candidates, True, f"没有精确匹配表 {table_hint}，请确认是否为：{', '.join(candidates)}")
    return ResolveResult(None, [], True, f"没有找到与 {table_hint} 匹配的表。")
