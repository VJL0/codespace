"""The rules for signing in, for adding and removing ways to sign in, and
for clearing out what has expired.

Each function works in the caller's transaction; the router commits."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error
from app.modules.auth.models import (
    EmailToken,
    OAuthAccount,
    OAuthProvider,
    PasswordCredential,
    RateLimitCounter,
    UserSession,
)
from app.modules.auth.passwords import check_password, hash_password
from app.modules.auth.providers.base import OAuthIdentity
from app.modules.auth.session import SESSION_IDLE_TIMEOUT
from app.modules.users.emails import EmailNotValidError
from app.modules.users.models import User, UserEmail
from app.modules.users.service import get_primary_email, get_verified_email

# --- Provider accounts ---------------------------------------------------------


async def list_oauth_accounts(
    db: AsyncSession, user_id: uuid.UUID
) -> list[OAuthAccount]:
    return list(
        await db.scalars(
            select(OAuthAccount)
            .where(OAuthAccount.user_id == user_id)
            .order_by(OAuthAccount.created_at)
        )
    )


async def sign_in_with_oauth(db: AsyncSession, identity: OAuthIdentity) -> User:
    """The user this provider account belongs to, created on its first
    sign-in. Refuses (409) one whose verified email another user has."""

    now = datetime.now(UTC)
    account = await _find_oauth_account(db, identity)

    if account is not None:
        account.email_snapshot = identity.email
        user = await db.get_one(User, account.user_id)
        user.last_sign_in_at = now

        if identity.avatar_url:
            user.avatar_url = identity.avatar_url

        return user

    verified_email = identity.verified_email

    # Someone already owns this address. It may well be the same person, but
    # a matching email proves nothing about that: never attach to an account
    # on email alone. They sign in there and link this provider.
    if verified_email is not None:
        await ensure_email_unclaimed(db, verified_email)

    user = User(
        full_name=identity.full_name,
        avatar_url=identity.avatar_url,
        last_sign_in_at=now,
    )
    db.add_all([user, _new_oauth_account(user, identity)])

    # Without a provider-verified email, the user simply has none yet.
    if verified_email is not None:
        db.add(
            UserEmail(user=user, email=verified_email, verified_at=now, is_primary=True)
        )

    return user


async def ensure_provider_unlinked(
    db: AsyncSession, user_id: uuid.UUID, provider: OAuthProvider
) -> None:
    """Refuse (409) if the user already has an account with this provider."""

    linked = await db.scalar(
        select(OAuthAccount.id).where(
            OAuthAccount.user_id == user_id, OAuthAccount.provider == provider
        )
    )

    if linked is not None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "provider_already_linked",
            "You already have an account with this provider linked.",
        )


async def link_oauth_account(
    db: AsyncSession, user: User, identity: OAuthIdentity
) -> None:
    """Add a provider account to the user's ways to sign in."""

    account = await _find_oauth_account(db, identity)

    if account is not None:
        if account.user_id == user.id:
            return

        raise api_error(
            status.HTTP_409_CONFLICT,
            "identity_in_use",
            "That account is linked to a different user.",
        )

    await ensure_provider_unlinked(db, user.id, identity.provider)
    db.add(_new_oauth_account(user, identity))

    # The provider vouches for this address and no one else has verified it:
    # it's the user's too. It's primary only if they had none.
    verified_email = identity.verified_email

    if (
        verified_email is not None
        and await get_verified_email(db, verified_email) is None
    ):
        db.add(
            UserEmail(
                user=user,
                email=verified_email,
                verified_at=datetime.now(UTC),
                is_primary=await get_primary_email(db, user.id) is None,
            )
        )


async def unlink_oauth_account(
    db: AsyncSession, user_id: uuid.UUID, provider: OAuthProvider
) -> None:
    """Remove a provider account, unless it's the user's last way in."""

    await _lock_user(db, user_id)
    accounts = await list_oauth_accounts(db, user_id)
    account = next((a for a in accounts if a.provider == provider), None)

    if account is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND, "not_linked", "That account isn't linked."
        )

    if len(accounts) == 1 and not await has_password(db, user_id):
        raise api_error(
            status.HTTP_409_CONFLICT,
            "last_method",
            "This is your only way to sign in. Add another one first.",
        )

    await db.delete(account)


async def _find_oauth_account(
    db: AsyncSession, identity: OAuthIdentity
) -> OAuthAccount | None:
    return await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == identity.provider,
            OAuthAccount.provider_user_id == identity.provider_user_id,
        )
    )


def _new_oauth_account(user: User, identity: OAuthIdentity) -> OAuthAccount:
    # By relationship rather than user.id: a new user has no id until the flush.
    return OAuthAccount(
        user=user,
        provider=identity.provider,
        provider_user_id=identity.provider_user_id,
        email_snapshot=identity.email,
    )


# --- Passwords -----------------------------------------------------------------


async def has_password(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await db.get(PasswordCredential, user_id) is not None


async def authenticate(db: AsyncSession, address: str, password: str) -> User | None:
    """The active user whose verified email and password these are, or None.
    Every failure takes about as long as a wrong password, so the timing
    doesn't tell whether the account exists."""

    try:
        email = await get_verified_email(db, address)
    except EmailNotValidError:
        email = None

    credential = email and await db.get(PasswordCredential, email.user_id)

    if not await check_password(credential, password):
        return None

    assert credential is not None  # check_password() fails without one
    user = await db.get_one(User, credential.user_id)

    if not user.is_active:
        return None

    user.last_sign_in_at = datetime.now(UTC)

    return user


async def password_matches(db: AsyncSession, user_id: uuid.UUID, password: str) -> bool:
    """Whether `password` is the user's, for confirming it's them."""

    return await check_password(await db.get(PasswordCredential, user_id), password)


async def create_password_account(
    db: AsyncSession, *, address: str, name: str, password: str
) -> User:
    """A new user signing up with an email they've just proven is theirs.
    Refuses (409) one someone verified meanwhile."""

    await ensure_email_unclaimed(db, address)

    now = datetime.now(UTC)
    user = User(full_name=name, last_sign_in_at=now)
    db.add_all(
        [
            user,
            UserEmail(user=user, email=address, verified_at=now, is_primary=True),
            PasswordCredential(user=user, password_hash=await hash_password(password)),
        ]
    )

    return user


async def ensure_no_password(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Refuse (409) if the user already has a password."""

    if await has_password(db, user_id):
        raise api_error(
            status.HTTP_409_CONFLICT, "password_exists", "You already have a password."
        )


async def set_password(db: AsyncSession, user_id: uuid.UUID, password: str) -> None:
    """Add the user's password, or replace it."""

    password_hash = await hash_password(password)
    credential = await db.get(PasswordCredential, user_id)

    if credential is None:
        db.add(PasswordCredential(user_id=user_id, password_hash=password_hash))
    else:
        credential.password_hash = password_hash


async def remove_password(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Remove the user's password, unless it's their last way in."""

    await _lock_user(db, user_id)
    credential = await db.get(PasswordCredential, user_id)

    if credential is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND, "no_password", "You have no password."
        )

    if not await list_oauth_accounts(db, user_id):
        raise api_error(
            status.HTTP_409_CONFLICT,
            "last_method",
            "This is your only way to sign in. Link another account first.",
        )

    await db.delete(credential)


# --- Shared --------------------------------------------------------------------


async def ensure_email_unclaimed(db: AsyncSession, address: str) -> None:
    """Refuse (409) an address another user has verified."""

    if await get_verified_email(db, address) is not None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "account_exists",
            "This email already has an account. Sign in instead.",
        )


async def _lock_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    # Two concurrent removals could each see another way in left and together
    # remove both; holding the user's row makes the second wait for the first.
    await db.get_one(User, user_id, with_for_update=True)


# --- Housekeeping --------------------------------------------------------------


async def purge_expired(db: AsyncSession) -> None:
    """Delete rows that can never be used again: ended sessions, spent or
    expired links, and rate-limit windows that are over. Safe to repeat."""

    now = datetime.now(UTC)

    await db.execute(
        delete(UserSession).where(
            or_(
                UserSession.expires_at <= now,
                UserSession.last_seen_at <= now - SESSION_IDLE_TIMEOUT,
            )
        )
    )
    await db.execute(
        delete(EmailToken).where(
            or_(EmailToken.expires_at <= now, EmailToken.consumed_at.is_not(None))
        )
    )
    # No rate-limit window is longer than a day.
    await db.execute(
        delete(RateLimitCounter).where(
            RateLimitCounter.window_start <= now - timedelta(days=1)
        )
    )
