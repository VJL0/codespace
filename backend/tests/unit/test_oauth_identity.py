"""OAuthIdentity: the provider-neutral identity every adapter produces."""

from __future__ import annotations

from typing import Any

from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import OAuthIdentity


def identity(**overrides: Any) -> OAuthIdentity:
    return OAuthIdentity(
        **{
            "provider": OAuthProvider.GOOGLE,
            "provider_user_id": "110169484474386276334",
            "email": "ada@example.com",
            **overrides,
        }
    )


def test_email_is_trimmed_and_lowercased() -> None:
    assert identity(email="  Ada@Example.COM ").email == "ada@example.com"
