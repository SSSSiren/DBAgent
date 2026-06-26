"""
RAG 工具集 - 为 Agent 提供检索增强能力

职责：
1. 提供语义规则检索工具
2. 提供 SQL 示例检索工具
3. 提供文档检索工具

设计决策：
- 工具返回格式化的上下文，便于 LLM 理解
- 支持元数据过滤（如按表名、数据库过滤）
- 返回结果包含相关性分数
"""

from typing import Optional
from langchain_core.tools import tool, BaseTool

from app.rag.retriever import Retriever
from app.config import settings


def create_rag_tools() -> list[BaseTool]:
    """
    创建 RAG 工具集

    返回：
        工具列表，包含：
        - search_semantic_rules: 搜索语义规则
        - search_sql_examples: 搜索 SQL 示例
        - search_documentation: 搜索文档
    """
    if not settings.RAG_ENABLED:
        return []

    tools = []

    # 1. 语义规则检索工具
    semantic_retriever = Retriever("semantic_rules", settings.RAG_PERSIST_DIR)

    @tool
    def search_semantic_rules(query: str) -> str:
        """搜索业务语义规则，如'有效订单'、'GMV'等定义。当用户询问业务概念或指标定义时使用。"""
        return semantic_retriever.retrieve_and_format(query, k=settings.RAG_TOP_K, header="相关语义规则：")

    tools.append(search_semantic_rules)

    # 2. SQL 示例检索工具
    sql_retriever = Retriever("sql_examples", settings.RAG_PERSIST_DIR)

    @tool
    def search_sql_examples(query: str) -> str:
        """搜索历史 SQL 查询示例。当需要参考类似查询的写法时使用。"""
        return sql_retriever.retrieve_and_format(query, k=settings.RAG_TOP_K, header="相关 SQL 示例：")

    tools.append(search_sql_examples)

    # 3. 文档检索工具
    doc_retriever = Retriever("documentation", settings.RAG_PERSIST_DIR)

    @tool
    def search_documentation(query: str) -> str:
        """搜索数据库文档和表结构说明。当需要了解表字段含义或业务背景时使用。"""
        return doc_retriever.retrieve_and_format(query, k=settings.RAG_TOP_K, header="相关文档：")

    tools.append(search_documentation)

    return tools


# 便捷函数：获取单个检索器
def get_semantic_retriever() -> Retriever:
    """获取语义规则检索器"""
    return Retriever("semantic_rules", settings.RAG_PERSIST_DIR)


def get_sql_retriever() -> Retriever:
    """获取 SQL 示例检索器"""
    return Retriever("sql_examples", settings.RAG_PERSIST_DIR)


def get_doc_retriever() -> Retriever:
    """获取文档检索器"""
    return Retriever("documentation", settings.RAG_PERSIST_DIR)
