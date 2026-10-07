"""Email normalization, and the model validation built on it."""

from __future__ import annotations

import pytest

from app.modules.auth.models import OAuthAccount
from app.modules.users.emails import EmailNotValidError, normalize_email
from app.modules.users.models import UserEmail


@pytest.mark.parametrize(
    ("address", "normalized"),
    [
        ("  Ada@Example.COM ", "Ada@example.com"),
        ("a@münchen.DE", "a@münchen.de"),
        # No provider-specific rules: Gmail's dots and +tags are kept.
        ("a.d.a+tag@gmail.com", "a.d.a+tag@gmail.com"),
        # Role names (RFC 2142) are lowercased.
        ("Postmaster@Example.com", "postmaster@example.com"),
    ],
)
def test_normalization_lowercases_the_domain(address: str, normalized: str) -> None:
    assert normalize_email(address) == normalized


@pytest.mark.parametrize("address", ["", "   ", "not-an-email", "a@localhost"])
def test_invalid_address_is_rejected(address: str) -> None:
    with pytest.raises(EmailNotValidError):
        normalize_email(address)


def test_user_email_keeps_the_address_and_its_normalized_key() -> None:
    email = UserEmail(email="  Ada@Example.COM ")

    assert email.email == "Ada@Example.COM"
    assert email.normalized_email == "Ada@example.com"


def test_user_email_cannot_be_invalid() -> None:
    with pytest.raises(EmailNotValidError):
        UserEmail(email="not-an-email")


@pytest.mark.parametrize(
    ("reported", "stored"),
    [("  Ada@Example.COM ", "Ada@Example.COM"), ("   ", None), (None, None)],
    ids=["stripped", "blank", "missing"],
)
def test_email_snapshot_is_stripped_or_none(
    reported: str | None, stored: str | None
) -> None:
    assert OAuthAccount(email_snapshot=reported).email_snapshot == stored
