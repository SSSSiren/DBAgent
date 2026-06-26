"""
RAG (Retrieval-Augmented Generation) 模块

提供检索增强生成功能，包括：
- Embedding 服务：将文本转换为向量
- 向量存储：存储和检索文档向量
- 检索工具：为 Agent 提供 RAG 检索能力
"""

from app.rag.embeddings import get_embedding_model
from app.rag.vector_store import VectorStore
from app.rag.retriever import Retriever

__all__ = [
    "get_embedding_model",
    "VectorStore",
    "Retriever",
]
