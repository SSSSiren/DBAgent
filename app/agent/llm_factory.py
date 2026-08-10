"""ChatOpenAI 客户端工厂 — 将 DeepSeek(OpenAI 兼容代理) 接入 LangChain ChatOpenAI。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import get_settings

_chat_model: ChatOpenAI | None = None


def get_chat_model() -> ChatOpenAI:
    """获取 ChatOpenAI 客户端（模块级懒加载单例，复用连接池）。"""
    global _chat_model
    if _chat_model is None:
        settings = get_settings()
        _chat_model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.1,
        )
    return _chat_model
