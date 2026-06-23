from dataclasses import dataclass
from typing import Any
import re


def normalize_identifier_hint(value: str) -> str:
    """Normalize identifier names (e.g., camelCase to snake_case)."""
    value = value.strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[\s\-]+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return value.strip("_").lower()


@dataclass
class ColumnSchema:
    name: str
    type: str = ""
    nullable: str = ""
    key: str = ""
    default: str = ""
    extra: str = ""


def parse_describe_result(result: dict[str, Any]) -> list[ColumnSchema]:
    columns = result.get("columnNames") or []
    rows = result.get("columnDatas") or []
    title_to_key = {
        str(column.get("title") or column.get("field") or "").lower(): column.get("key") or column.get("field")
        for column in columns
    }

    def key_for(*titles: str) -> str | None:
        for title in titles:
            key = title_to_key.get(title.lower())
            if key:
                return key
        return None

    field_key = key_for("Field", "field", "字段")
    type_key = key_for("Type", "type", "类型")
    null_key = key_for("Null", "null")
    key_key = key_for("Key", "key")
    default_key = key_for("Default", "default")
    extra_key = key_for("Extra", "extra")

    schemas = []
    for row in rows:
        name = str(row.get(field_key, "") if field_key else "")
        if not name:
            continue
        schemas.append(
            ColumnSchema(
                name=name,
                type=str(row.get(type_key, "") if type_key else ""),
                nullable=str(row.get(null_key, "") if null_key else ""),
                key=str(row.get(key_key, "") if key_key else ""),
                default=str(row.get(default_key, "") if default_key else ""),
                extra=str(row.get(extra_key, "") if extra_key else ""),
            )
        )
    return schemas


def schema_to_prompt(columns: list[ColumnSchema]) -> str:
    return "\n".join(
        f"- {column.name} {column.type} null={column.nullable} key={column.key} default={column.default} extra={column.extra}"
        for column in columns
    )
