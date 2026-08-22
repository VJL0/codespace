# app/core/config.py

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Codespace"

    environment: Literal["development", "test", "production"]

    api_url: AnyHttpUrl
    frontend_url: AnyHttpUrl

    allowed_hosts: list[str]
    cors_origins: list[AnyHttpUrl]

    database_url: str

    google_client_id: str
    google_client_secret: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
