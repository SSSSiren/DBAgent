from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API key")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com/v1")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat")

    ONEDBA_BASE_URL: str = Field(default="https://onedba.shizhuang-inc.com")
    ONEDBA_ACCESS_TOKEN: str = Field(default="", description="OneDBA access token")

    SEMANTIC_PROVIDER: str = Field(default="auto", description="Semantic rule provider: none/static_sandbox/file/http/auto")
    SEMANTIC_RULES_PATH: str = Field(default="", description="Path to semantic rules JSON for file provider")
    SEMANTIC_USER_RULES_PATH: str = Field(default="data/user_semantic_rules.json", description="Path to user-confirmed semantic rules JSON")
    SEMANTIC_HISTORY_RULES_PATH: str = Field(default="", description="Path to history-derived semantic rules JSON")
    SEMANTIC_SERVICE_URL: str = Field(default="", description="Base URL for external semantic metadata service")
    SEMANTIC_DEFAULT_DOMAIN: str = Field(default="", description="Default semantic domain, e.g. mysql_sandbox")

    # RAG 配置
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for embeddings")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="Embedding model name")
    RAG_ENABLED: bool = Field(default=True, description="Enable RAG functionality")
    RAG_TOP_K: int = Field(default=4, description="Number of documents to retrieve")
    RAG_PERSIST_DIR: str = Field(default="data/vector_store", description="Vector store persistence directory")

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
