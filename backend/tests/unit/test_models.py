"""Model validation that runs in Python, before anything reaches the database."""

from __future__ import annotations

import pytest

from app.modules.auth.models import OAuthAccount
from app.modules.users.models import User


def test_user_email_is_trimmed_and_lowercased() -> None:
    assert User(email="  Ada@Example.COM ").email == "ada@example.com"


@pytest.mark.parametrize("email", ["", "   "], ids=["empty", "blank"])
def test_user_email_cannot_be_empty(email: str) -> None:
    with pytest.raises(ValueError, match="Email cannot be empty"):
        User(email=email)


@pytest.mark.parametrize(
    ("provider_email", "stored"),
    [
        ("  Ada@Example.COM ", "ada@example.com"),
        ("   ", None),
        (None, None),
    ],
    ids=["normalized", "blank", "missing"],
)
def test_provider_email_is_normalized_or_none(
    provider_email: str | None, stored: str | None
) -> None:
    assert OAuthAccount(provider_email=provider_email).provider_email == stored
