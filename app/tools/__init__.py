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
from app.tools.list_tables import list_tables
from app.tools.describe_table import describe_table
from app.tools.query_database import query_database
from app.tools.execute_sql import execute_sql
from app.tools.ask_user import ask_user
from app.tools.formatters import format_as_markdown_table

# 工具元信息列表
# 每个工具包含 name、description、handler 和 parameters
# 用于注册到 Agent SDK 的工具系统
TOOLS = [
    {
        "name": "list_databases",
        "description": "列出当前用户有权限访问的数据库。当用户没有指定数据库时使用此工具。",
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
        "name": "list_tables",
        "description": "列出指定数据库中的所有表。",
        "handler": list_tables,
        "parameters": {
            "type": "object",
            "properties": {
                "schema_id": {
                    "type": "integer",
                    "description": "数据库的 schemaId",
                },
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，用于过滤表名",
                },
            },
            "required": ["schema_id"],
        },
    },
    {
        "name": "describe_table",
        "description": "查看表结构，获取字段名、类型等信息。在生成 SQL 前使用此工具了解表结构。",
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
            "自然语言查询数据库。根据用户问题自动生成 SQL 并执行。"
            "当用户用自然语言描述查询需求时使用此工具，而不是直接写 SQL。"
            "追问时也使用此工具，在 question 参数中包含完整需求。"
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
                    "description": "目标表名",
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
        "description": "直接执行 SQL 查询。当用户提供了明确的 SQL 语句时使用。只允许 SELECT/SHOW/DESCRIBE。",
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
    {
        "name": "ask_user",
        "description": "向用户提问，获取更多信息。当信息不足或存在歧义时使用。",
        "handler": ask_user,
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "清晰明确的问题",
                },
            },
            "required": ["question"],
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
    "list_tables",
    "describe_table",
    "query_database",
    "execute_sql",
    "ask_user",
    "format_as_markdown_table",
]