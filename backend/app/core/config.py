from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"]
    # The one public origin, without a trailing slash: the SPA at / and the
    # API at /api are served from it.
    app_url: str

    allowed_hosts: list[str]

    database_url: str

    google_client_id: str
    google_client_secret: str
    microsoft_client_id: str
    microsoft_client_secret: str
    github_client_id: str
    github_client_secret: str
    oauth_session_secret_key: str

    # Email (Resend in production; logged elsewhere)
    resend_api_key: str
    email_from: str

    # Keys the rate limiter's per-email buckets by HMAC, so its table isn't a
    # list of every address someone tried.
    rate_limit_secret_key: str

    # What Vercel Cron sends as `Authorization: Bearer ...` to run scheduled
    # jobs, and what the app requires of anyone calling them.
    cron_secret: str

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
