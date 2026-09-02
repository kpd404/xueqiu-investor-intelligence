from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from contracts.analysis import PRODUCTION_OPINION_ANALYSIS_VERSION


class Settings(BaseSettings):
    """Runtime settings shared by every application layer."""

    app_name: str = "Xueqiu Investor Intelligence System"
    app_env: str = "development"
    app_version: str = "0.1.0"
    database_url: str = "sqlite+pysqlite:///./xueqiu_intelligence.db"
    database_echo: bool = False
    llm_provider_id: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    llm_api_style: str = "responses"
    llm_structured_output: str = "json_schema"
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    production_opinion_analysis_version: str = PRODUCTION_OPINION_ANALYSIS_VERSION

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
