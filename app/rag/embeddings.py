"""
Embedding 服务 - 文本向量化

职责：
1. 提供文本转向量的能力
2. 支持多种 Embedding 模型（OpenAI / 本地模型）
3. 缓存模型实例，避免重复加载

设计决策：
- 默认使用 OpenAI text-embedding-3-small（性价比高）
- 可切换为本地 sentence-transformers（离线可用）
- 使用 lru_cache 缓存模型实例
"""

from functools import lru_cache
from typing import List

from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings

from app.config import settings


@lru_cache
def get_embedding_model() -> Embeddings:
    """
    获取 Embedding 模型实例

    返回：
        Embeddings: LangChain Embedding 实例

    配置：
        在 .env 中设置：
        - OPENAI_API_KEY: OpenAI API 密钥
        - OPENAI_BASE_URL: API 基础 URL（可选，用于代理）
        - EMBEDDING_MODEL: 模型名称，默认 text-embedding-3-small
    """
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_api_base=settings.OPENAI_BASE_URL,
    )


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    批量将文本转换为向量

    参数：
        texts: 文本列表

    返回：
        向量列表，每个向量是浮点数数组

    示例：
        >>> vectors = await embed_texts(["有效订单", "GMV"])
        >>> len(vectors)
        2
        >>> len(vectors[0])
        1536  # text-embedding-3-small 的维度
    """
    model = get_embedding_model()
    return await model.aembed_documents(texts)


async def embed_query(text: str) -> List[float]:
    """
    将查询文本转换为向量

    参数：
        text: 查询文本

    返回：
        向量（浮点数数组）

    注意：
        查询和文档使用不同的嵌入方法（LangChain 内部处理）
    """
    model = get_embedding_model()
    return await model.aembed_query(text)
