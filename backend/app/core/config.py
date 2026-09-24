# app/core/config.py

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App (URLs without trailing slash)
    environment: Literal["development", "test", "production"]
    api_url: str
    frontend_url: str

    # HTTP
    allowed_hosts: list[str]

    # Database
    database_url: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    oauth_session_secret_key: str

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.api_url}/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
