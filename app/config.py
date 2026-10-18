"""Only deployment operators can set the trusted Spring API endpoint."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    spring_api_base_url: str = "http://127.0.0.1:8080"
    internal_service_token: str = ""
    spring_api_timeout_seconds: float = Field(default=8.0, ge=1, le=30)
    max_ai_concurrency: int = Field(default=8, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
