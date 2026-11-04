from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/code2api.db"
    admin_token: str = ""
    encryption_key: str = ""
    host: str = "127.0.0.1"
    port: int = 8045
    upstream_timeout_seconds: float = 300
    default_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
