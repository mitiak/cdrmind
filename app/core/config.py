from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://cdrmind:cdrmind@localhost:5432/cdrmind"

    # External services
    raggy_url: str = "http://raggy:8001"
    taskonaut_url: str = "http://taskonaut-soc:8002"
    guardflow_url: str = "http://guardflow:8003"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    llm_max_tokens: int = 4096

    # Rate limiting
    redis_url: str = "redis://redis:6379"
    rate_limit_per_minute: int = 10

    # Polling
    task_poll_interval_secs: float = 1.0
    task_poll_max_attempts: int = 120

    # Logging
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
