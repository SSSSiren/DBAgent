"""
工具注册 — 导出所有工具 handler 函数和元信息

每个工具包含：
- name: 工具名称（LLM 通过名称调用）
- description: 工具描述（LLM 用于判断何时调用）
- handler: 异步 handler 函数
- parameters: 参数定义（JSON Schema 格式）
"""

from app.tools.list_databases import list_databases
from app.tools.select_database import select_database
from app.tools.describe_table import describe_table
from app.tools.query_database import query_database
from app.tools.execute_sql import execute_sql
from app.tools.find_table import find_table
from app.tools.formatters import format_as_markdown_table

# 工具元信息列表
# 每个工具包含 name、description、handler 和 parameters
# 用于注册到 Agent SDK 的工具系统
TOOLS = [
    {
        "name": "list_databases",
        "description": "列出当前用户有权限访问的数据库。仅在用户想了解'有哪些数据库'时使用，找表请用 find_table。",
        "handler": list_databases,
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，用于过滤数据库名称",
                },
                "env_type": {
                    "type": "string",
                    "description": "环境类型，默认 test",
                },
            },
        },
    },
    {
        "name": "select_database",
        "description": "选择当前数据库，设置后续查询的默认上下文。",
        "handler": select_database,
        "parameters": {
            "type": "object",
            "properties": {
                "schema_id": {
                    "type": "integer",
                    "description": "数据库的 schemaId（从 list_databases 结果中获取）",
                },
            },
            "required": ["schema_id"],
        },
    },
    {
        "name": "find_table",
        "description": (
            "在所有可访问数据库中搜索匹配的表名（自动覆盖所有环境）。"
            "正常搜索：keyword 支持逗号分隔的多关键词（最多5个），取并集。"
            "兜底模式：3-4 次关键词搜索仍找不到目标表时，keyword 留空调用，"
            "返回所有环境的所有表（每环境最多 500 条）。"
            "结果包含 (schemaId, 数据库名, 环境, 表名, 表注释)，"
            "请根据表注释与用户问题的语义匹配，选择最合适的表。"
        ),
        "handler": find_table,
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，支持逗号分隔多个（如'order,ticket,task'），最多5个，取并集。留空则返回所有表（兜底模式）。",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "describe_table",
        "description": "查看表结构，获取字段名、类型等信息。仅在用户明确要求'看看表结构'时使用，找表、查询数据时不要调用此工具。",
        "handler": describe_table,
        "parameters": {
            "type": "object",
            "properties": {
                "schema_id": {
                    "type": "integer",
                    "description": "数据库的 schemaId",
                },
                "table_name": {
                    "type": "string",
                    "description": "表名",
                },
            },
            "required": ["schema_id", "table_name"],
        },
    },
    {
        "name": "query_database",
        "description": (
            "【首选】自然语言查询数据库，根据用户问题自动生成 SQL 并执行。"
            "当用户用自然语言描述查询需求时优先使用此工具，不要自己写 SQL 用 execute_sql 试错。"
            "追问时也使用此工具，在 question 参数中包含完整需求。"
            "涉及多表 JOIN 时，table_name 用逗号分隔传入所有表名（如 \"order_record, account\"），工具会自动获取各表结构。"
        ),
        "handler": query_database,
        "parameters": {
            "type": "object",
            "properties": {
                "schema_id": {
                    "type": "integer",
                    "description": "数据库的 schemaId",
                },
                "question": {
                    "type": "string",
                    "description": "用户的自然语言问题（包含完整需求，追问时也包含修改点）",
                },
                "table_name": {
                    "type": "string",
                    "description": "目标表名，涉及多表 JOIN 时用逗号分隔（如 \"order_record, account\"），最多 5 个",
                },
                "summary": {
                    "type": "string",
                    "description": "对话摘要（可选），用于理解上下文",
                },
            },
            "required": ["schema_id", "question", "table_name"],
        },
    },
    {
        "name": "execute_sql",
        "description": "直接执行 SQL 查询。仅在用户提供了明确 SQL 语句时使用。不要用此工具搜索表名——找表请用 find_table，不要执行 SHOW TABLES。只允许 SELECT/SHOW/DESCRIBE。",
        "handler": execute_sql,
        "parameters": {
            "type": "object",
            "properties": {
                "schema_id": {
                    "type": "integer",
                    "description": "数据库的 schemaId",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL 语句（只允许 SELECT/SHOW/DESCRIBE）",
                },
            },
            "required": ["schema_id", "sql"],
        },
    },
]

# 工具名称到 handler 的映射，方便快速查找
TOOL_HANDLERS: dict[str, object] = {
    tool["name"]: tool["handler"] for tool in TOOLS
}


def get_tool_handler(name: str):
    """根据名称获取工具 handler"""
    return TOOL_HANDLERS.get(name)


__all__ = [
    "TOOLS",
    "TOOL_HANDLERS",
    "get_tool_handler",
    "list_databases",
    "select_database",
    "find_table",
    "describe_table",
    "query_database",
    "execute_sql",
    "format_as_markdown_table",
]