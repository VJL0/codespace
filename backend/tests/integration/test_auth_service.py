"""AuthService against the database: who a provider identity signs in as."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.auth.exceptions import AccountExistsError, LastSignInMethodError
from app.modules.auth.models import OAuthAccount, OAuthProvider
from app.modules.auth.providers.base import OAuthIdentity
from app.modules.auth.repository import (
    OAuthAccountRepository,
    PasswordCredentialRepository,
)
from app.modules.auth.service import AuthService
from app.modules.users.models import User, UserEmail
from app.modules.users.repository import UserEmailRepository, UserRepository
from tests.support.database import MakeUser, count_rows


@pytest.fixture
def auth(db: AsyncSession) -> AuthService:
    return AuthService(
        OAuthAccountRepository(db),
        UserRepository(db),
        UserEmailRepository(db),
        PasswordCredentialRepository(db),
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


# --- Linking and unlinking ----------------------------------------------------


async def test_relinking_the_same_account_changes_nothing(
    db: AsyncSession, auth: AuthService
) -> None:
    user = await sign_in(db, auth)

    await auth.link_oauth_account(user, identity())
    await db.flush()

    assert await count_rows(db, OAuthAccount) == 1
    assert await count_rows(db, UserEmail) == 1


async def test_a_linked_verified_email_becomes_primary_if_there_was_none(
    db: AsyncSession, auth: AuthService
) -> None:
    user = await sign_in(db, auth, email=None)

    await auth.link_oauth_account(
        user,
        identity(provider=OAuthProvider.GITHUB, provider_user_id="583231"),
    )
    await db.flush()

    email = await db.scalar(select(UserEmail))
    assert email is not None
    assert (email.email, email.is_primary) == ("ada@example.com", True)


async def test_a_linked_unverified_email_isnt_attached(
    db: AsyncSession, auth: AuthService
) -> None:
    user = await sign_in(db, auth, email=None)

    await auth.link_oauth_account(
        user,
        identity(
            provider=OAuthProvider.GITHUB,
            provider_user_id="583231",
            email_verified=False,
        ),
    )
    await db.flush()

    assert await count_rows(db, OAuthAccount) == 2
    assert await count_rows(db, UserEmail) == 0


async def test_concurrent_unlinks_leave_one_sign_in_method(engine: AsyncEngine) -> None:
    # Two requests each unlink one of a user's two accounts. Each alone is
    # allowed; together they'd leave none, unless the second waits for the
    # first. Real concurrency takes separate connections and committed data,
    # so this test runs outside the per-test rollback and cleans up after.
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = User(full_name="Two Methods")
        setup.add_all(
            [
                user,
                OAuthAccount(
                    user=user, provider=OAuthProvider.GOOGLE, provider_user_id="race-1"
                ),
                OAuthAccount(
                    user=user, provider=OAuthProvider.GITHUB, provider_user_id="race-2"
                ),
            ]
        )
        await setup.commit()

    async def unlink(provider: OAuthProvider) -> bool:
        async with AsyncSession(engine) as db:
            service = AuthService(
                OAuthAccountRepository(db),
                UserRepository(db),
                UserEmailRepository(db),
                PasswordCredentialRepository(db),
            )

            try:
                await service.unlink_oauth_account(user, provider)
            except LastSignInMethodError:
                return False

            await db.commit()

            return True

    try:
        results = await asyncio.gather(
            unlink(OAuthProvider.GOOGLE), unlink(OAuthProvider.GITHUB)
        )

        assert sorted(results) == [False, True]
        async with AsyncSession(engine) as db:
            remaining = await db.scalar(
                select(func.count())
                .select_from(OAuthAccount)
                .where(OAuthAccount.user_id == user.id)
            )
        assert remaining == 1
    finally:
        async with AsyncSession(engine) as db:
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()
