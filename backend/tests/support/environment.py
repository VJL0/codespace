"""The environment the app is configured with under test."""

from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

APP_HOST = "app.example.test"
APP_URL = f"https://{APP_HOST}"

PROVIDER_CREDENTIALS = {
    "google": ("google-client-id", "google-client-secret"),
    "microsoft": ("microsoft-client-id", "microsoft-client-secret"),
    "github": ("github-client-id", "github-client-secret"),
}


def app_environment() -> dict[str, str]:
    """Variables that take precedence over .env for app.core.config."""

    return {
        "ENVIRONMENT": "test",
        "APP_URL": APP_URL,
        "ALLOWED_HOSTS": f'["{APP_HOST}"]',
        "DATABASE_URL": "postgresql+asyncpg://unused.invalid/unused",
        "OAUTH_SESSION_SECRET_KEY": "test-oauth-session-secret",
        "RESEND_API_KEY": "re_test_unused",
        "EMAIL_FROM": "CodeSpace <no-reply@example.com>",
        "RATE_LIMIT_SECRET_KEY": "test-rate-limit-secret",
        **{
            f"{provider.upper()}_CLIENT_{part}": value
            for provider, (client_id, secret) in PROVIDER_CREDENTIALS.items()
            for part, value in (("ID", client_id), ("SECRET", secret))
        },
    }
