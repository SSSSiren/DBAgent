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

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=True)

    # Langfuse 可观测性配置
    LANGFUSE_ENABLED: bool = Field(default=True, description="Enable Langfuse tracing")
    LANGFUSE_PUBLIC_KEY: str = Field(default="", description="Langfuse public key")
    LANGFUSE_SECRET_KEY: str = Field(default="", description="Langfuse secret key")
    LANGFUSE_HOST: str = Field(default="https://cloud.langfuse.com", description="Langfuse host URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
