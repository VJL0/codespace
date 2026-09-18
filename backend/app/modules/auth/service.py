from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import OAuthProvider, User, UserOAuthAccount


async def upsert_google_user(
    session: AsyncSession,
    *,
    google_sub: str,
    email: str,
    full_name: str | None,
    avatar_url: str | None,
) -> User:
    """
    Resolve a Google sign-in to a local user.

    Matches by the stable OIDC `sub` claim first. Only falls back to matching
    an existing account by email because Google has already verified it -
    `sub` is what stays stable if the user later changes their email.
    """

    normalized_email = email.strip().lower()
    now = datetime.now(UTC)

    oauth_account = await session.scalar(
        select(UserOAuthAccount).where(
            UserOAuthAccount.provider == OAuthProvider.GOOGLE,
            UserOAuthAccount.provider_user_id == google_sub,
        )
    )

    if oauth_account is not None:
        oauth_account.provider_email = normalized_email
        oauth_account.provider_email_verified = True
        oauth_account.last_login_at = now

        user = await session.get(User, oauth_account.user_id)

        if user is None:
            raise RuntimeError("OAuth account references a missing user.")

        user.last_login_at = now

        if avatar_url:
            user.avatar_url = avatar_url

        return user

    user = await session.scalar(select(User).where(User.email == normalized_email))

    if user is None:
        user = User(
            email=normalized_email,
            full_name=full_name,
            avatar_url=avatar_url,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

    session.add(
        UserOAuthAccount(
            user_id=user.id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id=google_sub,
            provider_email=normalized_email,
            provider_email_verified=True,
            last_login_at=now,
        )
    )
    user.last_login_at = now

    return user
