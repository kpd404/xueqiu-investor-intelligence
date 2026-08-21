from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by every application layer."""

    app_name: str = "Xueqiu Investor Intelligence System"
    app_env: str = "development"
    app_version: str = "0.1.0"
    database_url: str = "sqlite+pysqlite:///./xueqiu_intelligence.db"
    database_echo: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
