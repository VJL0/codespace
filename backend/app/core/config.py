# app/core/config.py

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Codespace API"

    environment: Literal["development", "testing", "production"]
    debug: bool = False

    database_url: str

    access_token_secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = 60 * 24

    backend_cors_origins: list[AnyHttpUrl]

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("debug")
    @classmethod
    def validate_debug(cls, value: bool, info) -> bool:
        environment = info.data.get("environment")

        if environment == "production" and value:
            raise ValueError("DEBUG must be false in production")

        return value

    @field_validator("backend_cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[AnyHttpUrl], info) -> list[AnyHttpUrl]:
        environment = info.data.get("environment")

        if environment == "production":
            for origin in value:
                if origin.host in {"localhost", "127.0.0.1", "0.0.0.0"}:
                    raise ValueError(
                        "Localhost CORS origins are not allowed in production"
                    )

        return value

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
