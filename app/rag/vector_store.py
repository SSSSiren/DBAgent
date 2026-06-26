"""
向量存储 - 文档向量的存储与检索

职责：
1. 管理文档的向量化存储
2. 提供相似度检索能力
3. 支持持久化到磁盘

设计决策：
- 使用 FAISS 作为向量数据库（轻量、高效）
- 支持从文件加载/保存索引
- 提供简单的文档管理接口
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

try:
    import faiss
    from langchain_community.docstore.in_memory import InMemoryDocstore
    from langchain_community.vectorstores import FAISS
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: FAISS not installed. Run: pip install faiss-cpu")

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore as LangChainVectorStore

from app.rag.embeddings import get_embedding_model


class VectorStore:
    """
    向量存储管理器

    功能：
    - 添加文档（自动向量化）
    - 相似度检索
    - 持久化存储

    示例：
        >>> store = VectorStore("semantic_rules")
        >>> store.add_texts(["有效订单", "GMV"], [{"source": "rule1"}])
        >>> results = store.similarity_search("什么是有效订单", k=3)
    """

    def __init__(self, collection_name: str, persist_dir: Optional[str] = None):
        """
        初始化向量存储

        参数：
            collection_name: 集合名称（用于区分不同类型的文档）
            persist_dir: 持久化目录（可选，默认 ./data/vector_store）
        """
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS not installed. Run: pip install faiss-cpu")

        self.collection_name = collection_name
        self.persist_dir = Path(persist_dir or "./data/vector_store")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.embedding_model = get_embedding_model()
        self.vectorstore: Optional[LangChainVectorStore] = None

        # 尝试加载已存在的索引
        self._load_if_exists()

    def _load_if_exists(self):
        """如果存在持久化的索引，则加载"""
        index_path = self.persist_dir / self.collection_name
        if (index_path / "index.faiss").exists():
            try:
                self.vectorstore = FAISS.load_local(
                    str(index_path),
                    self.embedding_model,
                    allow_dangerous_deserialization=True,
                )
            except Exception as e:
                print(f"Warning: Failed to load vector store: {e}")
                self.vectorstore = None

    def _ensure_vectorstore(self):
        """确保向量存储已初始化"""
        if self.vectorstore is None:
            # 创建一个空的向量存储
            self.vectorstore = FAISS.from_texts(
                ["__init__"],  # 占位符
                self.embedding_model,
            )

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加文本到向量存储

        参数：
            texts: 文本列表
            metadatas: 元数据列表（可选）
            ids: 文档 ID 列表（可选）

        返回：
            文档 ID 列表

        示例：
            >>> store.add_texts(
            ...     ["有效订单", "GMV"],
            ...     [{"source": "rule1"}, {"source": "rule2"}]
            ... )
        """
        self._ensure_vectorstore()
        ids = self.vectorstore.add_texts(texts, metadatas, ids)
        self._persist()
        return ids

    def add_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加 Document 对象到向量存储

        参数：
            documents: Document 对象列表
            ids: 文档 ID 列表（可选）

        返回：
            文档 ID 列表
        """
        self._ensure_vectorstore()
        ids = self.vectorstore.add_documents(documents, ids)
        self._persist()
        return ids

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        相似度检索

        参数：
            query: 查询文本
            k: 返回结果数量（默认 4）
            filter: 元数据过滤条件（可选）

        返回：
            相似的 Document 列表

        示例：
            >>> results = store.similarity_search("什么是有效订单", k=3)
            >>> for doc in results:
            ...     print(doc.page_content, doc.metadata)
        """
        if self.vectorstore is None:
            return []

        return self.vectorstore.similarity_search(query, k, filter=filter)

    def similarity_search_with_score(
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
            (Document, score) 元组列表，分数越低越相似
        """
        if self.vectorstore is None:
            return []

        return self.vectorstore.similarity_search_with_score(query, k, filter=filter)

    def delete(self, ids: List[str]) -> None:
        """
        删除文档

        参数：
            ids: 要删除的文档 ID 列表
        """
        if self.vectorstore is None:
            return

        self.vectorstore.delete(ids)
        self._persist()

    def clear(self) -> None:
        """清空向量存储"""
        self.vectorstore = None
        index_path = self.persist_dir / self.collection_name
        if index_path.exists():
            import shutil
            shutil.rmtree(index_path)

    def _persist(self):
        """持久化到磁盘"""
        if self.vectorstore is None:
            return

        index_path = self.persist_dir / self.collection_name
        index_path.mkdir(parents=True, exist_ok=True)
        self.vectorstore.save_local(str(index_path))

    def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        返回：
            统计信息字典
        """
        if self.vectorstore is None:
            return {"count": 0, "collection": self.collection_name}

        # FAISS 索引的文档数量
        index = self.vectorstore.index
        count = index.ntotal if hasattr(index, "ntotal") else 0

        return {
            "count": count,
            "collection": self.collection_name,
            "persist_dir": str(self.persist_dir),
        }
