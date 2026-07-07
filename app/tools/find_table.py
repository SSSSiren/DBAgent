"""
find_table 工具 — 在所有可访问数据库中搜索匹配的表名

一次调用即可跨库搜索，避免逐个 select_database → list_tables 的机械遍历。
支持多关键词（逗号分隔）取并集，内部在 SQL 层用 LIKE 过滤。
当 keyword 为空时，返回指定环境的所有表（兜底方案）。
"""

from app.client.onedba import get_onedba_client
from app.tools.formatters import format_as_markdown_table


async def find_table(keyword: str = "", max_results: int = 200) -> str:
    """在所有可访问数据库中搜索匹配的表名和表注释。

    一次调用遍历所有数据库（自动覆盖 test/prod/dev 等环境），
    返回 (schemaId, 数据库名, 环境, 表名, 表注释) 列表。

    参数:
        keyword: 搜索关键词，用于在表名中做 LIKE 匹配。
                 支持多个关键词（逗号分隔），取并集，如 "order,ticket,task"。
                 最多 5 个关键词。
                 当 keyword 为空时，返回所有环境的所有表（兜底方案，每环境最多 500 条）。
        max_results: 最大返回结果数，默认 200，上限 500

    返回:
        Markdown 格式的搜索结果，包含 schemaId、数据库名、环境、表名、表注释五列

    使用场景:
        - 正常搜索：keyword="order,ticket,task" → LIKE 过滤
        - 兜底方案：多次搜索无果后，keyword="" → 返回全部表目录
    """
    # 1. 解析关键词
    if keyword and keyword.strip():
        keywords = [k.strip().lower() for k in keyword.split(",") if k.strip()][:5]
        if any(len(k) > 100 for k in keywords):
            return "关键词过长，每个关键词请控制在 100 字符以内。"
        is_fallback = False
    else:
        keywords = []
        is_fallback = True

    # 2. 限制 max_results 范围（兜底模式上限 500）
    max_results = max(min(max_results, 500), 1)

    client = get_onedba_client()

    # 3. 遍历所有环境
    all_rows: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()  # 去重：(schemaId, table_name)
    env_types = ["test", "prod", "dev"]

    for env_type in env_types:
        if len(all_rows) >= max_results:
            break

        try:
            databases = await client.list_databases(env_type=env_type, size=70)
        except Exception:
            continue

        if not databases:
            continue

        for db in databases:
            if len(all_rows) >= max_results:
                break

            schema_id = db.get("schemaId")
            schema_name = db.get("schemaName", "未知")
            if schema_id is None:
                continue

            try:
                if is_fallback:
                    # 兜底：全量拉取该库所有表
                    sql = "SHOW TABLE STATUS"
                    result = await client.execute_sql(schema_id=schema_id, sql=sql)
                    datas = result.get("columnDatas") or []

                    for row in datas:
                        if len(all_rows) >= max_results:
                            break
                        if isinstance(row, dict):
                            table_name = str(row.get("col_1") or row.get("Name") or "")
                            key = (schema_id, table_name)
                            if key in seen:
                                continue
                            seen.add(key)
                            all_rows.append({
                                "schemaId": schema_id,
                                "schemaName": schema_name,
                                "env_type": env_type,
                                "table_name": table_name,
                                "comment": str(row.get("col_18") or row.get("Comment") or ""),
                            })
                else:
                    # 正常：每个关键词单独 LIKE
                    for kw in keywords:
                        if len(all_rows) >= max_results:
                            break

                        escaped = kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                        sql = f"SHOW TABLE STATUS LIKE '%{escaped}%'"

                        result = await client.execute_sql(schema_id=schema_id, sql=sql)
                        datas = result.get("columnDatas") or []

                        for row in datas:
                            if len(all_rows) >= max_results:
                                break
                            if isinstance(row, dict):
                                table_name = str(row.get("col_1") or row.get("Name") or "")
                                key = (schema_id, table_name)
                                if key in seen:
                                    continue
                                seen.add(key)
                                all_rows.append({
                                    "schemaId": schema_id,
                                    "schemaName": schema_name,
                                    "env_type": env_type,
                                    "table_name": table_name,
                                    "comment": str(row.get("col_18") or row.get("Comment") or ""),
                                })
            except Exception:
                # 单个库查询失败不影响整体，跳过
                continue

    if not all_rows:
        return (
            f"未找到匹配关键词 {keywords} 的表。\n\n"
            f"建议：\n"
            f"- 尝试使用不同的关键词组合\n"
            f"- 使用 list_databases 先查看有哪些数据库，再尝试搜索"
        )

    # 4. 处理截断
    total_found = len(all_rows)
    truncated = total_found >= max_results
    if truncated:
        all_rows = all_rows[:max_results]

    # 5. 格式化为 Markdown 表格
    result_dict = {
        "columnNames": [
            {"title": "schemaId", "key": "schemaId"},
            {"title": "数据库名", "key": "schemaName"},
            {"title": "环境", "key": "env_type"},
            {"title": "表名", "key": "table_name"},
            {"title": "表注释", "key": "comment"},
        ],
        "columnDatas": all_rows,
    }

    result = format_as_markdown_table(result_dict)

    if truncated:
        result += (
            f"\n\n⚠️ 结果过多，已截断，仅显示前 {max_results} 条。"
            f" 如果未找到目标表，请使用更精确的关键词重新搜索。"
        )

    if is_fallback:
        result += (
            f"\n\n这是完整的表目录（兜底模式）。"
            f" 共 {len(all_rows)} 个表，请根据表注释选出目标表。"
        )
    else:
        result += (
            f"\n\n找到 {len(all_rows)} 个匹配关键词 {keywords} 的表。"
            f" 请根据表注释与用户问题的语义相关性选择最匹配的表。"
        )

    return result