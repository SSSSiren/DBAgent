from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


@lru_cache
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY or "missing-api-key",
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.1,
    )


def is_llm_configured() -> bool:
    return bool(settings.DEEPSEEK_API_KEY)
