"""
结果格式化 — 将 OneDBA 查询结果转换为 Markdown 表格

参考 DBAgent 的 app/tools/formatters.py
"""

from __future__ import annotations

from typing import Any


def escape_markdown_cell(value: Any) -> str:
    """将值转换为安全的 Markdown 表格单元格（单行）"""
    if value is None:
        return ""
    text = str(value).replace("\n", "<br>").replace("\r", "")
    return text.replace("|", "\\|")


def format_as_markdown_table(
    result: dict[str, Any], max_rows: int | None = None
) -> str:
    """
    将 OneDBA columnNames/columnDatas 转换为 Markdown 表格。

    输入格式：
    {
        "columnNames": [{"title": "id", "key": "id"}, ...],
        "columnDatas": [{"id": 1, "name": "foo"}, ...]
    }
    """
    columns = result.get("columnNames") or []
    rows = result.get("columnDatas") or []

    if not columns:
        return "查询成功，结果为空"

    # 提取列标题和键
    col_titles = [
        escape_markdown_cell(
            col.get("title") or col.get("field") or col.get("key") or ""
        )
        for col in columns
    ]
    col_keys = [col.get("key") or col.get("field") for col in columns]

    # 构建表格
    lines = [
        "| " + " | ".join(col_titles) + " |",
        "| " + " | ".join(["---"] * len(col_titles)) + " |",
    ]

    visible_rows = rows[:max_rows] if max_rows is not None else rows
    for row in visible_rows:
        values = [escape_markdown_cell(row.get(key, "")) for key in col_keys]
        lines.append("| " + " | ".join(values) + " |")

    # 行数信息
    suffix = f"\n共 {len(rows)} 行"
    if max_rows is not None and len(rows) > max_rows:
        suffix += f"，已显示前 {max_rows} 行"
    lines.append(suffix)

    return "\n".join(lines)