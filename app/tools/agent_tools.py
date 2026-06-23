"""
Agent 工具定义 — LangChain Tool 封装

为 LLM Agent 提供可调用的工具集，包括：
- list_databases: 列出可用数据库
- select_database: 选择当前数据库（设置上下文）
- list_tables: 列出数据库中的表
- describe_table: 查看表结构
- execute_sql: 直接执行 SQL
- ask_user: 向用户提问（信息不足时）

核心 NL2SQL 工具 query_database 在 query_database.py 中定义。
"""

import json
from typing import Optional

from langchain_core.tools import tool

from app.client.onedba_client import onedba_client
from app.tools.db_explorer import sanitize_database_item
from app.tools.formatters import format_as_markdown_table
from app.tools.sql_executor import needs_confirmation, security_check


@tool
async def list_databases_tool(keyword: str = "", env_type: str = "test") -> str:
    """列出当前用户有权限访问的数据库。

    参数:
    - keyword: 搜索关键词（可选），用于过滤数据库名称
    - env_type: 环境类型，默认 "test"

    返回:
    - JSON 格式的数据库列表，包含 schemaId, schemaName, instanceName 等信息

    使用场景:
    - 用户没有指定数据库时，先调用此工具查找可用数据库
    - 用户提到数据库关键词（如 "dw 库"）时，用 keyword 参数搜索
    """
    try:
        databases = await onedba_client.list_databases(keyword=keyword, env_type=env_type)
    except Exception as exc:
        return f"查询失败：{exc}"
    sanitized = [sanitize_database_item(item) for item in databases]
    return json.dumps(sanitized, ensure_ascii=False, indent=2)


@tool
async def select_database_tool(schema_id: int) -> str:
    """选择当前数据库，设置后续查询的默认上下文。

    参数:
    - schema_id: 数据库的 schemaId（从 list_databases 结果中获取）

    返回:
    - 确认信息，包含数据库名称和实例名称

    使用场景:
    - 用户明确说"使用 xxx 数据库"
    - 从 list_databases 结果中选择一个数据库后调用
    - 后续查询如果不指定 schema_id，将默认使用这个数据库
    """
    # 验证 schema_id 是否存在
    try:
        databases = await onedba_client.list_databases(keyword="", env_type="test")
    except Exception as exc:
        return f"查询失败：{exc}"

    selected = None
    for db in databases:
        if db.get("schemaId") == schema_id:
            selected = sanitize_database_item(db)
            break

    if not selected:
        return f"未找到 schema_id={schema_id} 的数据库，请先调用 list_databases 查看可用数据库。"

    return (
        f"已选择数据库：\n\n"
        f"- 数据库：`{selected.get('schemaName')}`\n"
        f"- 实例：`{selected.get('instanceName')}`\n"
        f"- Schema ID：`{schema_id}`\n\n"
        f"后续查询如果不指定数据库，将默认使用该数据库。"
    )


@tool
async def list_tables_tool(schema_id: int, keyword: str = "") -> str:
    """列出指定数据库中的所有表。

    参数:
    - schema_id: 数据库的 schemaId（必需）
    - keyword: 搜索关键词（可选），用于过滤表名

    返回:
    - Markdown 格式的表名列表

    使用场景:
    - 用户问"有哪些表"
    - 需要查找特定表时
    """
    try:
        result = await onedba_client.execute_sql(schema_id=schema_id, sql="SHOW TABLES")
    except Exception as exc:
        return f"查询失败：{exc}"

    # 如果有关键词，过滤结果
    if keyword:
        # 从结果中提取表名并过滤
        # format_as_markdown_table 返回的是 Markdown 字符串，这里需要原始数据
        # 简化处理：直接返回完整列表，让 LLM 自己过滤
        pass

    return format_as_markdown_table(result)


@tool
async def describe_table_tool(schema_id: int, table_name: str) -> str:
    """查看表结构，获取字段名、类型等信息。

    参数:
    - schema_id: 数据库的 schemaId（必需）
    - table_name: 表名（必需）

    返回:
    - Markdown 格式的字段信息，包含 Field, Type, Null, Key, Default, Extra

    使用场景:
    - 用户问"表结构是什么"
    - 生成 SQL 前需要了解表结构
    """
    try:
        # 简单的表名验证
        if not table_name or not table_name.replace("_", "").replace("-", "").isalnum():
            return f"无效的表名：{table_name}"

        safe_table = f"`{table_name}`"
        result = await onedba_client.execute_sql(schema_id=schema_id, sql=f"DESCRIBE {safe_table}")
    except Exception as exc:
        return f"查询失败：{exc}"
    return format_as_markdown_table(result)


@tool
async def execute_sql_tool(schema_id: int, sql: str) -> str:
    """直接执行 SQL 查询。

    参数:
    - schema_id: 数据库的 schemaId（必需）
    - sql: SQL 语句（必需）

    返回:
    - Markdown 格式的查询结果

    约束:
    - 只允许 SELECT/SHOW/DESCRIBE
    - UPDATE/DELETE/INSERT 会被拦截，需要用户确认
    - 禁止 CREATE/ALTER/DROP/TRUNCATE 等 DDL 操作

    使用场景:
    - 用户提供了明确的 SQL 语句
    - 需要执行复杂的自定义查询
    - 对于自然语言查询，优先使用 query_database 工具
    """
    # 安全检查
    check = security_check(sql)
    if not check.passed:
        return f"执行被拒绝：{check.message}"

    # 检查是否需要确认（写操作）
    if needs_confirmation(sql):
        return (
            f"检测到写操作，需要用户确认：\n\n"
            f"```sql\n{sql}\n```\n\n"
            f"请让用户确认后再执行。"
        )

    try:
        result = await onedba_client.execute_sql(schema_id=schema_id, sql=sql)
    except Exception as exc:
        return f"执行失败：{exc}"
    return format_as_markdown_table(result)


@tool
async def ask_user_tool(question: str) -> str:
    """向用户提问，获取更多信息。

    参数:
    - question: 清晰明确的问题

    返回:
    - 用户回答（注意：这个工具需要特殊处理，Agent 会暂停等待用户输入）

    使用场景:
    - 信息不足，需要用户补充
    - 存在歧义，需要用户选择（如多个数据库候选、多个表名相似）
    - 需要用户确认重要操作

    注意:
    - 这个工具的实现需要 Agent 框架支持暂停和恢复
    - 在当前版本中，这个工具会返回一个占位符，实际实现需要在 AgentExecutor 层面处理
    """
    # 这个工具的实际执行需要在 AgentExecutor 层面特殊处理
    # 这里只是返回一个占位符，实际的问答逻辑在 Agent 循环中处理
    return f"[需要用户回答] 问题：{question}"


# 工具列表，供 AgentExecutor 使用
AGENT_TOOLS = [
    list_databases_tool,
    select_database_tool,
    list_tables_tool,
    describe_table_tool,
    execute_sql_tool,
    ask_user_tool,
]
