"""
list_databases 工具 — 列出用户有权限访问的数据库

参考 DBAgent 的 app/tools/agent_tools.py:list_databases_tool
"""

import json

from app.client.onedba import get_onedba_client


def sanitize_database_item(item: dict) -> dict:
    """提取数据库列表中的关键字段"""
    return {
        "schemaId": item.get("schemaId"),
        "schemaName": item.get("schemaName"),
        "instanceName": item.get("instanceName"),
        "envType": item.get("envType"),
    }


async def list_databases(keyword: str = "", env_type: str = "test") -> str:
    """列出当前用户有权限访问的数据库。

    参数:
        keyword: 搜索关键词（可选），用于过滤数据库名称
        env_type: 环境类型，默认 "test"

    返回:
        JSON 格式的数据库列表，包含 schemaId, schemaName, instanceName 等信息

    使用场景:
        - 用户没有指定数据库时，先调用此工具查找可用数据库
        - 用户提到数据库关键词（如 "dw 库"）时，用 keyword 参数搜索
    """
    client = get_onedba_client()
    try:
        databases = await client.list_databases(keyword=keyword, env_type=env_type)
    except Exception as exc:
        return f"查询失败：{exc}"

    sanitized = [sanitize_database_item(item) for item in databases]
    return json.dumps(sanitized, ensure_ascii=False, indent=2)