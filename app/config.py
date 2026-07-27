"""
应用配置 — 基于 Pydantic Settings 的环境变量管理

参考 DBAgent 的 config.py，管理 LLM、OneDBA、Langfuse、服务等配置。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从 .env 文件和环境变量自动加载"""

    # ========== LLM ==========
    llm_api_key: str = ""
    llm_base_url: str = "https://dwai-data.dewu-inc.com/openai/v1"
    llm_model: str = "deepseek-v4-flash-260425"
    llm_embedding_model: str = "text-embedding-3-small"

    # ========== OneDBA ==========
    onedba_base_url: str = "https://onedba.shizhuang-inc.com"
    onedba_access_token: str = ""

    # ========== Langfuse ==========
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_trace_prefix: str = "DBAgent"

    # ========== 语义规则 ==========
    semantic_provider: str = "auto"
    semantic_rules_path: str = "data/semantic_rules.json"
    semantic_user_rules_path: str = "data/user_semantic_rules.json"
    semantic_history_rules_path: str = ""
    semantic_service_url: str = ""
    semantic_default_domain: str = "mysql_sandbox"

    # ========== 服务 ==========
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ========== OpenViking 对话记忆（可选）==========
    kb_enabled: bool = False
    kb_openviking_url: str = "http://localhost:1933"
    kb_auto_commit_turns: int = 10

    # ========== 存储后端 ==========
    storage_backend: str = "memory"
    redis_url: str = ""
    storage_file_path: str = "data/sessions.db"

    # ========== 操作记忆（查询偏好）==========
    preference_enabled: bool = True

    # ========== SQL 历史记忆 ==========
    sql_memory_enabled: bool = False
    sql_memory_top_k: int = 5
    sql_memory_token_budget: int = 1500
    sql_memory_sql_max_length: int = 2000
    sql_memory_ttl_days: int = 90
    sql_memory_min_similarity: float = 0.0
    sql_memory_pattern_min_records: int = 20
    sql_memory_scope: str = "user"  # "user" / "database" / "mixed"

    # ========== HDC 数据底座 ==========
    hdc_enabled: bool = False
    hdc_auto_generate: bool = False
    hdc_semantic_timeout: float = 300.0  # write(wait=True) 等待 SemanticProcessor 的超时秒数

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取配置单例（带缓存）"""
    return Settings()