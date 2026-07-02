"""
list_tables 工具 — 列出指定数据库中的所有表

参考 DBAgent 的 app/tools/agent_tools.py:list_tables_tool
"""

from app.client.onedba import get_onedba_client
from app.tools.formatters import format_as_markdown_table


async def list_tables(schema_id: int, keyword: str = "") -> str:
    """列出指定数据库中的所有表。

    参数:
        schema_id: 数据库的 schemaId（必需）
        keyword: 搜索关键词（可选），用于过滤表名

    返回:
        Markdown 格式的表名列表

    使用场景:
        - 用户问"有哪些表"
        - 需要查找特定表时
    """
    client = get_onedba_client()
    try:
        if keyword:
            # 转义 LIKE 通配符，避免 % 和 _ 被当作模糊匹配符
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql = f"SHOW TABLES LIKE '%{escaped}%'"
        else:
            sql = "SHOW TABLES"
        result = await client.execute_sql(schema_id=schema_id, sql=sql)
    except Exception as exc:
        return f"查询失败：{exc}"

    return format_as_markdown_table(result)