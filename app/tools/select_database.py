"""
select_database 工具 — 选择当前数据库，设置后续查询的默认上下文

参考 DBAgent 的 app/tools/agent_tools.py:select_database_tool
"""

from app.client.onedba import get_onedba_client
from app.tools.list_databases import sanitize_database_item


async def select_database(schema_id: int) -> str:
    """选择当前数据库，设置后续查询的默认上下文。

    参数:
        schema_id: 数据库的 schemaId（从 list_databases 结果中获取）

    返回:
        确认信息，包含数据库名称和实例名称

    使用场景:
        - 用户明确说"使用 xxx 数据库"
        - 从 list_databases 结果中选择一个数据库后调用
        - 后续查询如果不指定 schema_id，将默认使用这个数据库
    """
    client = get_onedba_client()

    # 验证 schema_id 是否存在
    try:
        databases = await client.list_databases(keyword="", env_type="test")
    except Exception as exc:
        return f"查询失败：{exc}"

    selected = None
    for db in databases:
        if db.get("schemaId") == schema_id:
            selected = sanitize_database_item(db)
            break

    if not selected:
        return (
            f"未找到 schema_id={schema_id} 的数据库，"
            f"请先调用 list_databases 查看可用数据库。"
        )

    return (
        f"已选择数据库：\n\n"
        f"- 数据库：`{selected.get('schemaName')}`\n"
        f"- 实例：`{selected.get('instanceName')}`\n"
        f"- Schema ID：`{schema_id}`\n\n"
        f"后续查询如果不指定数据库，将默认使用该数据库。"
    )