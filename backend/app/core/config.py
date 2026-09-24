# app/core/config.py

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
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


settings = Settings()
