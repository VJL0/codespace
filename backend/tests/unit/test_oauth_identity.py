"""OAuthIdentity: the provider-neutral identity every adapter produces."""

from __future__ import annotations

from typing import Any

import pytest

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


def test_email_is_trimmed_but_keeps_its_case() -> None:
    assert identity(email="  Ada@Example.COM ").email == "Ada@Example.COM"


@pytest.mark.parametrize("email", [None, "", "not-an-email"])
def test_missing_or_invalid_email_is_no_email(email: str | None) -> None:
    assert identity(email=email).email is None


def test_verified_email_needs_the_provider_to_vouch_for_it() -> None:
    assert identity(email_verified=True).verified_email == "ada@example.com"
    assert identity(email_verified=False).verified_email is None
    assert identity(email=None, email_verified=True).verified_email is None
