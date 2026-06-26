"""
RAG 数据初始化 - 将现有数据导入向量存储

职责：
1. 从语义规则文件导入数据
2. 从历史 SQL 导入示例
3. 提供批量导入接口

使用方式：
    python -m app.rag.initialize
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from langchain_core.documents import Document

from app.rag.retriever import Retriever
from app.config import settings


def initialize_semantic_rules(rules_data: List[Dict[str, Any]]) -> int:
    """
    初始化语义规则到向量存储

    参数：
        rules_data: 规则数据列表，每条规则包含：
            - name: 规则名称
            - description: 规则描述
            - sql: SQL 片段
            - tables: 相关表
            - domain: 业务域

    返回：
        导入的规则数量

    示例：
        >>> rules = [
        ...     {
        ...         "name": "有效订单",
        ...         "description": "paid 和 completed 订单才计入有效订单",
        ...         "sql": "order_status IN ('paid', 'completed')",
        ...         "tables": ["orders"],
        ...         "domain": "mysql_sandbox"
        ...     }
        ... ]
        >>> count = initialize_semantic_rules(rules)
    """
    retriever = get_semantic_retriever()

    documents = []
    for rule in rules_data:
        # 构建文档内容
        content = f"{rule.get('name', '')}: {rule.get('description', '')}"
        if rule.get('sql'):
            content += f"\nSQL: {rule.get('sql')}"

        # 构建元数据
        metadata = {
            "type": "semantic_rule",
            "name": rule.get("name", ""),
            "domain": rule.get("domain", ""),
            "tables": ",".join(rule.get("tables", [])),
        }

        documents.append(Document(page_content=content, metadata=metadata))

    if documents:
        retriever.add_documents(documents)

    return len(documents)


def initialize_sql_examples(examples: List[Dict[str, Any]]) -> int:
    """
    初始化 SQL 示例到向量存储

    参数：
        examples: SQL 示例列表，每条包含：
            - question: 用户问题
            - sql: SQL 查询
            - tables: 涉及的表
            - description: 说明（可选）

    返回：
        导入的示例数量
    """
    retriever = get_sql_retriever()

    documents = []
    for example in examples:
        content = f"问题: {example.get('question', '')}\nSQL: {example.get('sql', '')}"
        if example.get('description'):
            content += f"\n说明: {example.get('description')}"

        metadata = {
            "type": "sql_example",
            "tables": ",".join(example.get("tables", [])),
        }

        documents.append(Document(page_content=content, metadata=metadata))

    if documents:
        retriever.add_documents(documents)

    return len(documents)


def initialize_from_files(
    semantic_rules_path: str = None,
    sql_examples_path: str = None,
) -> Dict[str, int]:
    """
    从文件初始化数据

    参数：
        semantic_rules_path: 语义规则 JSON 文件路径
        sql_examples_path: SQL 示例 JSON 文件路径

    返回：
        导入数量统计 {"semantic_rules": N, "sql_examples": M}
    """
    stats = {"semantic_rules": 0, "sql_examples": 0}

    # 导入语义规则
    if semantic_rules_path:
        path = Path(semantic_rules_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                rules = data if isinstance(data, list) else data.get("rules", [])
                stats["semantic_rules"] = initialize_semantic_rules(rules)

    # 导入 SQL 示例
    if sql_examples_path:
        path = Path(sql_examples_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                examples = json.load(f)
                stats["sql_examples"] = initialize_sql_examples(examples)

    return stats


# 便捷函数
def get_semantic_retriever() -> Retriever:
    """获取语义规则检索器"""
    return Retriever("semantic_rules", settings.RAG_PERSIST_DIR)


def get_sql_retriever() -> Retriever:
    """获取 SQL 示例检索器"""
    return Retriever("sql_examples", settings.RAG_PERSIST_DIR)


if __name__ == "__main__":
    # 示例：从默认路径初始化
    stats = initialize_from_files(
        semantic_rules_path=settings.SEMANTIC_RULES_PATH or "data/semantic_rules.json",
        sql_examples_path="data/sql_examples.json",
    )
    print(f"初始化完成: {stats}")
