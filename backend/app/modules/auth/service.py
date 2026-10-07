from __future__ import annotations

from datetime import UTC, datetime

from app.modules.auth.exceptions import AccountExistsError
from app.modules.auth.models import OAuthAccount
from app.modules.auth.providers.base import OAuthIdentity
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class AuthService:
    def __init__(self, accounts: OAuthAccountRepository, users: UserRepository) -> None:
        self._accounts = accounts
        self._users = users

    async def sign_in_with_oauth(self, oauth_identity: OAuthIdentity) -> User:
        email = oauth_identity.email
        now = datetime.now(UTC)

        account = await self._accounts.get_by_provider_user_id(
            oauth_identity.provider, oauth_identity.provider_user_id
        )

        if account is not None:
            account.provider_email = email
            account.provider_email_verified = oauth_identity.email_verified

            user = await self._users.get(account.user_id)

            if user is None:
                raise RuntimeError("OAuth account references a missing user.")

            user.last_sign_in_at = now

            if oauth_identity.avatar_url:
                user.avatar_url = oauth_identity.avatar_url

            return user

        # Each user has exactly one account, so a matching email belongs to
        # someone who signs in another way; never attach to it on email alone.
        if await self._users.email_exists(email):
            raise AccountExistsError

        user = User(
            email=email,
            full_name=oauth_identity.full_name,
            avatar_url=oauth_identity.avatar_url,
            last_sign_in_at=now,
        )
        self._users.add(user)
        self._accounts.add(
            OAuthAccount(
                user=user,
                provider=oauth_identity.provider,
                provider_user_id=oauth_identity.provider_user_id,
                provider_email=email,
                provider_email_verified=oauth_identity.email_verified,
            )
        )

        return user
