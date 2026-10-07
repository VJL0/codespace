"""AuthService against the database: who a provider identity signs in as."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.exceptions import AccountExistsError
from app.modules.auth.models import OAuthAccount, OAuthProvider
from app.modules.auth.providers.base import OAuthIdentity
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.auth.service import AuthService
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from tests.support.database import MakeUser, count_rows


@pytest.fixture
def auth(db: AsyncSession) -> AuthService:
    return AuthService(OAuthAccountRepository(db), UserRepository(db))


def identity(**overrides: Any) -> OAuthIdentity:
    return OAuthIdentity(
        **{
            "provider": OAuthProvider.GOOGLE,
            "provider_user_id": "110169484474386276334",
            "email": "ada@example.com",
            "email_verified": True,
            "full_name": "Ada Lovelace",
            "avatar_url": "https://example.com/ada.png",
            **overrides,
        }
    )


async def sign_in(db: AsyncSession, auth: AuthService, **overrides: Any) -> User:
    user = await auth.sign_in_with_oauth(identity(**overrides))
    await db.flush()

    return user


async def test_first_sign_in_creates_the_user_and_their_account(
    db: AsyncSession, auth: AuthService
) -> None:
    before = datetime.now(UTC)

    user = await sign_in(db, auth)

    assert user.email == "ada@example.com"
    assert user.full_name == "Ada Lovelace"
    assert user.last_sign_in_at is not None
    assert user.last_sign_in_at >= before
    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert account.user_id == user.id
    assert account.provider_email == "ada@example.com"


async def test_returning_user_is_matched_by_provider_id_not_email(
    db: AsyncSession, auth: AuthService
) -> None:
    first = await sign_in(db, auth)
    first.last_sign_in_at = datetime.now(UTC) - timedelta(days=1)

    again = await sign_in(db, auth, email="ada@newmail.com", email_verified=False)

    assert again.id == first.id
    assert again.email == "ada@example.com"
    assert again.last_sign_in_at > datetime.now(UTC) - timedelta(minutes=1)
    assert await count_rows(db, User) == 1
    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert account.provider_email == "ada@newmail.com"
    assert account.provider_email_verified is False


async def test_returning_user_keeps_their_avatar_when_the_provider_sends_none(
    db: AsyncSession, auth: AuthService
) -> None:
    await sign_in(db, auth)

    user = await sign_in(db, auth, avatar_url=None)

    assert user.avatar_url == "https://example.com/ada.png"


async def test_email_owned_by_another_user_is_refused(
    db: AsyncSession, auth: AuthService, make_user: MakeUser
) -> None:
    await make_user(email="ada@example.com")

    with pytest.raises(AccountExistsError):
        await auth.sign_in_with_oauth(identity())

    assert await count_rows(db, OAuthAccount) == 0
