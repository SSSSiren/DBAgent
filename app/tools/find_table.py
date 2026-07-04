"""
find_table 工具 — 在所有可访问数据库中搜索匹配的表名

一次调用即可跨库搜索，避免逐个 select_database → list_tables 的机械遍历。
表名推断仍由 Agent 完成，本工具只负责消除 N 次切换数据库的机械操作。
"""

from app.client.onedba import get_onedba_client
from app.tools.formatters import format_as_markdown_table


async def find_table(keyword: str = "", env_type: str = "test") -> str:
    """在所有可访问数据库中搜索匹配的表名。

    一次调用遍历所有数据库，返回 (schemaId, 数据库名, 表名) 列表。
    适合 Agent 不知道目标表在哪个库时的初始探索。

    参数:
        keyword: 搜索关键词（可选），用于过滤表名。
                 为空时返回所有库的所有表（谨慎使用，数据量可能很大）。
        env_type: 环境类型，默认 test

    返回:
        Markdown 格式的搜索结果，包含 schemaId、数据库名、表名三列

    使用场景:
        - 用户问"工单表在哪"但 Agent 不知道在哪个数据库
        - 需要跨多个数据库查找同名或相似表
    """
    client = get_onedba_client()

    # 1. 获取所有可访问的数据库
    try:
        databases = await client.list_databases(env_type=env_type, size=200)
    except Exception as exc:
        return f"获取数据库列表失败：{exc}"

    if not databases:
        return "当前没有可访问的数据库"

    # 2. 遍历每个数据库，搜索匹配的表
    all_rows: list[dict[str, object]] = []

    for db in databases:
        schema_id = db.get("schemaId")
        schema_name = db.get("schemaName", "未知")
        if schema_id is None:
            continue

        try:
            if keyword:
                escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                sql = f"SHOW TABLES LIKE '%{escaped}%'"
            else:
                sql = "SHOW TABLES"

            result = await client.execute_sql(schema_id=schema_id, sql=sql)
            datas = result.get("columnDatas") or []

            for row in datas:
                if isinstance(row, dict):
                    # SHOW TABLES 返回的列名可能是 Tables_in_xxx
                    table_name = list(row.values())[0] if row else ""
                    all_rows.append({
                        "schemaId": schema_id,
                        "schemaName": schema_name,
                        "table_name": str(table_name),
                    })
        except Exception:
            # 单个数据库查询失败不影响整体，跳过
            continue

    if not all_rows:
        return f"未找到匹配 '{keyword}' 的表" if keyword else "未找到任何表"

    # 3. 格式化为 Markdown 表格
    result_dict = {
        "columnNames": [
            {"title": "schemaId", "key": "schemaId"},
            {"title": "数据库名", "key": "schemaName"},
            {"title": "表名", "key": "table_name"},
        ],
        "columnDatas": all_rows,
    }

    return format_as_markdown_table(result_dict)
