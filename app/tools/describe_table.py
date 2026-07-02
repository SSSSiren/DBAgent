"""
describe_table 工具 — 查看表结构，获取字段名、类型等信息

参考 DBAgent 的 app/tools/agent_tools.py:describe_table_tool
"""

from app.client.onedba import get_onedba_client
from app.tools.formatters import format_as_markdown_table


async def describe_table(schema_id: int, table_name: str) -> str:
    """查看表结构，获取字段名、类型等信息。

    参数:
        schema_id: 数据库的 schemaId（必需）
        table_name: 表名（必需）

    返回:
        Markdown 格式的字段信息，包含 Field, Type, Null, Key, Default, Extra

    使用场景:
        - 用户问"表结构是什么"
        - 生成 SQL 前需要了解表结构
    """
    # 简单的表名验证
    if not table_name or not table_name.replace("_", "").replace("-", "").isalnum():
        return f"无效的表名：{table_name}"

    client = get_onedba_client()
    safe_table = f"`{table_name}`"
    try:
        result = await client.execute_sql(
            schema_id=schema_id, sql=f"DESCRIBE {safe_table}"
        )
    except Exception as exc:
        return f"查询失败：{exc}"

    return format_as_markdown_table(result)