"""
检索器 - RAG 检索逻辑封装

职责：
1. 封装向量检索逻辑
2. 提供多种检索策略（相似度、MMR）
3. 格式化检索结果为 LLM 可用的上下文

设计决策：
- 支持相似度检索和 MMR（最大边际相关性）检索
- 提供结果格式化，便于注入到 prompt
- 支持元数据过滤
"""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document

from app.rag.vector_store import VectorStore


class Retriever:
    """
    检索器 - 封装 RAG 检索逻辑

    功能：
    - 相似度检索
    - MMR 检索（多样性）
    - 结果格式化

    示例：
        >>> retriever = Retriever("semantic_rules")
        >>> context = retriever.retrieve("什么是有效订单", k=3)
        >>> print(context)
        "相关文档：\n1. 有效订单定义：...\n2. ..."
    """

    def __init__(self, collection_name: str, persist_dir: Optional[str] = None):
        """
        初始化检索器

        参数：
            collection_name: 向量集合名称
            persist_dir: 持久化目录
        """
        self.vector_store = VectorStore(collection_name, persist_dir)

    def retrieve(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        相似度检索

        参数：
            query: 查询文本
            k: 返回结果数量
            filter: 元数据过滤条件

        返回：
            Document 列表
        """
        return self.vector_store.similarity_search(query, k, filter)

    def retrieve_with_score(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[tuple[Document, float]]:
        """
        相似度检索（带分数）

        参数：
            query: 查询文本
            k: 返回结果数量
            filter: 元数据过滤条件

        返回：
            (Document, score) 元组列表
        """
        return self.vector_store.similarity_search_with_score(query, k, filter)

    def retrieve_mmr(
        self,
        query: str,
        k: int = 4,
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        MMR 检索（最大边际相关性）

        平衡相关性和多样性，避免返回过于相似的结果

        参数：
            query: 查询文本
            k: 返回结果数量
            fetch_k: 候选结果数量（先检索这么多，再筛选）
            lambda_mult: 相关性权重（0=最大多样性，1=最大相关性）
            filter: 元数据过滤条件

        返回：
            Document 列表
        """
        if self.vector_store.vectorstore is None:
            return []

        return self.vector_store.vectorstore.max_marginal_relevance_search(
            query,
            k=k,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
            filter=filter,
        )

    def format_as_context(
        self,
        documents: List[Document],
        header: str = "相关参考信息：",
        include_metadata: bool = True,
    ) -> str:
        """
        将检索结果格式化为 LLM 可用的上下文

        参数：
            documents: Document 列表
            header: 上下文标题
            include_metadata: 是否包含元数据

        返回：
            格式化后的文本

        示例：
            >>> docs = retriever.retrieve("有效订单", k=2)
            >>> context = retriever.format_as_context(docs)
            >>> print(context)
            "相关参考信息：
            1. [来源: rule1] 有效订单定义：...
            2. [来源: rule2] GMV 计算：..."
        """
        if not documents:
            return ""

        lines = [header]
        for i, doc in enumerate(documents, 1):
            if include_metadata and doc.metadata:
                meta_str = ", ".join(f"{k}={v}" for k, v in doc.metadata.items())
                lines.append(f"{i}. [{meta_str}] {doc.page_content}")
            else:
                lines.append(f"{i}. {doc.page_content}")

        return "\n".join(lines)

    def retrieve_and_format(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        header: str = "相关参考信息：",
    ) -> str:
        """
        检索并格式化（便捷方法）

        参数：
            query: 查询文本
            k: 返回结果数量
            filter: 元数据过滤条件
            header: 上下文标题

        返回：
            格式化后的上下文文本
        """
        documents = self.retrieve(query, k, filter)
        return self.format_as_context(documents, header)

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        添加文本到向量存储

        参数：
            texts: 文本列表
            metadatas: 元数据列表

        返回：
            文档 ID 列表
        """
        return self.vector_store.add_texts(texts, metadatas)

    def add_documents(self, documents: List[Document]) -> List[str]:
        """
        添加 Document 对象到向量存储

        参数：
            documents: Document 列表

        返回：
            文档 ID 列表
        """
        return self.vector_store.add_documents(documents)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        返回：
            统计信息字典
        """
        return self.vector_store.get_stats()
