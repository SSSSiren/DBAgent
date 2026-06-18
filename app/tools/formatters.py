from typing import Any


def escape_markdown_cell(value: Any) -> str:
    """Convert a value to a safe single-line Markdown table cell."""

    if value is None:
        return ""
    text = str(value).replace("\n", "<br>").replace("\r", "")
    return text.replace("|", "\\|")


def format_as_markdown_table(result: dict[str, Any], max_rows: int | None = None) -> str:
    """Convert OneDBA columnNames/columnDatas into a Markdown table."""

    columns = result.get("columnNames") or []
    rows = result.get("columnDatas") or []
    if not columns:
        return "查询成功，结果为空"

    col_titles = [escape_markdown_cell(col.get("title") or col.get("field") or col.get("key") or "") for col in columns]
    col_keys = [col.get("key") or col.get("field") for col in columns]

    lines = [
        "| " + " | ".join(col_titles) + " |",
        "| " + " | ".join(["---"] * len(col_titles)) + " |",
    ]

    visible_rows = rows[:max_rows] if max_rows is not None else rows
    for row in visible_rows:
        values = [escape_markdown_cell(row.get(key, "")) for key in col_keys]
        lines.append("| " + " | ".join(values) + " |")

    suffix = f"\n共 {len(rows)} 行"
    if max_rows is not None and len(rows) > max_rows:
        suffix += f"，已显示前 {max_rows} 行"
    lines.append(suffix)
    return "\n".join(lines)
