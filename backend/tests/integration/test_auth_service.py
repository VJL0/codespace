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
from app.modules.users.models import User, UserEmail
from app.modules.users.repository import UserEmailRepository, UserRepository
from tests.support.database import MakeUser, count_rows


@pytest.fixture
def auth(db: AsyncSession) -> AuthService:
    return AuthService(
        OAuthAccountRepository(db), UserRepository(db), UserEmailRepository(db)
    )


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

    assert user.full_name == "Ada Lovelace"
    assert user.last_sign_in_at is not None
    assert user.last_sign_in_at >= before
    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert account.user_id == user.id
    assert account.email_snapshot == "ada@example.com"
    email = await db.scalar(select(UserEmail))
    assert email is not None
    assert email.user_id == user.id
    assert email.email == "ada@example.com"
    assert email.is_primary
    assert email.verified_at is not None


async def test_returning_user_is_matched_by_provider_id_not_email(
    db: AsyncSession, auth: AuthService
) -> None:
    first = await sign_in(db, auth)
    first.last_sign_in_at = datetime.now(UTC) - timedelta(days=1)

    again = await sign_in(db, auth, email="ada@newmail.com", email_verified=False)

    assert again.id == first.id
    assert again.last_sign_in_at > datetime.now(UTC) - timedelta(minutes=1)
    assert await count_rows(db, User) == 1
    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert account.email_snapshot == "ada@newmail.com"
    # A changed provider email changes nothing the user owns.
    assert await db.scalar(select(UserEmail.email)) == "ada@example.com"


async def test_returning_user_keeps_their_avatar_when_the_provider_sends_none(
    db: AsyncSession, auth: AuthService
) -> None:
    await sign_in(db, auth)

    user = await sign_in(db, auth, avatar_url=None)

    assert user.avatar_url == "https://example.com/ada.png"


@pytest.mark.parametrize("owned", ["ada@example.com", "ada@EXAMPLE.COM"])
async def test_verified_email_owned_by_another_user_is_refused(
    db: AsyncSession, auth: AuthService, make_user: MakeUser, owned: str
) -> None:
    await make_user(email=owned)

    with pytest.raises(AccountExistsError):
        await auth.sign_in_with_oauth(identity())

    assert await count_rows(db, OAuthAccount) == 0


@pytest.mark.parametrize(
    "overrides",
    [{"email": None}, {"email_verified": False}],
    ids=["no-email", "unverified-email"],
)
async def test_without_a_verified_email_the_user_has_none(
    db: AsyncSession, auth: AuthService, overrides: dict[str, Any]
) -> None:
    user = await sign_in(db, auth, **overrides)

    assert user.id is not None
    assert await count_rows(db, OAuthAccount) == 1
    assert await count_rows(db, UserEmail) == 0


async def test_unverified_email_may_match_another_users_address(
    db: AsyncSession, auth: AuthService, make_user: MakeUser
) -> None:
    # Unverified, it claims nothing, so it can't collide either.
    owner = await make_user(email="ada@example.com")

    user = await sign_in(db, auth, email_verified=False)

    assert user.id != owner.id
    assert await count_rows(db, UserEmail) == 1


async def test_local_part_case_makes_a_different_address(
    db: AsyncSession, auth: AuthService, make_user: MakeUser
) -> None:
    # Only the receiving server may treat Ada@ and ada@ as one mailbox.
    await make_user(email="Ada@example.com")

    await sign_in(db, auth)

    assert await count_rows(db, UserEmail) == 2
