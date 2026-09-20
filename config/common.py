from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from contracts.analysis import (
    PRODUCTION_OPINION_ANALYSIS_VERSION,
    PRODUCTION_THESIS_COMPARISON_VERSION,
)


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
    llm_retry_backoff_seconds: float = Field(default=1.0, ge=0, le=60)
    llm_retry_invalid_structured_output: bool = True
    production_opinion_analysis_version: str = PRODUCTION_OPINION_ANALYSIS_VERSION
    production_thesis_comparison_version: str = PRODUCTION_THESIS_COMPARISON_VERSION
    feed_activation_window_days: int = Field(default=30, ge=0)
    feed_stale_window_days: int = Field(default=30, gt=0)
    context_window_days: int = Field(default=30, gt=0)
    pattern_multi_investor_threshold: int = Field(default=3, ge=2)
    operational_refresh_interval_minutes: int = Field(default=60, gt=0, le=1440)
    operational_refresh_stale_after_minutes: int = Field(default=90, gt=0, le=10080)
    xueqiu_cdp_endpoint: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
