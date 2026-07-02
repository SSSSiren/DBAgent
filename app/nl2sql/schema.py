"""
表结构解析 — 解析 OneDBA DESCRIBE 结果，提取 ColumnSchema

参考 DBAgent 的 app/nl2sql/schema.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


def normalize_identifier_hint(value: str) -> str:
    """将标识符规范化（如 camelCase → snake_case），用于模糊字段匹配"""
    value = value.strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[\s\-]+", "_", value)
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return value.strip("_").lower()


@dataclass
class ColumnSchema:
    """表字段描述"""

    name: str
    type: str = ""
    nullable: str = ""
    key: str = ""          # PRI / UNI / MUL
    default: str = ""
    extra: str = ""        # auto_increment, on update CURRENT_TIMESTAMP, etc.


def parse_describe_result(result: dict[str, Any]) -> list[ColumnSchema]:
    """
    解析 OneDBA DESCRIBE 命令的返回结果。

    返回格式：
    {
        "columnNames": [{"title": "Field", "key": "Field"}, ...],
        "columnDatas": [{"Field": "id", "Type": "int", ...}, ...]
    }
    """
    columns = result.get("columnNames") or []
    rows = result.get("columnDatas") or []

    # 建立 title → key 映射
    title_to_key: dict[str, str] = {}
    for column in columns:
        title = str(column.get("title") or column.get("field") or "").lower()
        key = column.get("key") or column.get("field")
        if title and key:
            title_to_key[title] = key

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

    schemas: list[ColumnSchema] = []
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
    """将表结构转换为 LLM prompt 可用的文本格式"""
    return "\n".join(
        f"- {column.name} {column.type} null={column.nullable} key={column.key} "
        f"default={column.default} extra={column.extra}"
        for column in columns
    )