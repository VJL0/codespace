# app/core/config.py

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, PositiveInt, SecretStr
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

    # Authlib / OAuth transaction state
    oauth_session_secret_key: SecretStr
    oauth_session_cookie_name: str = "oauth_session"
    oauth_session_max_age_seconds: PositiveInt = 10 * 60

    # Logged-in application session
    auth_session_cookie_name: str = "__Host-Http-session"
    auth_session_idle_timeout_seconds: PositiveInt = 30 * 60
    auth_session_absolute_timeout_seconds: PositiveInt = 14 * 24 * 60 * 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def google_redirect_uri(self) -> str:
        return f"{str(self.api_url).rstrip('/')}/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
