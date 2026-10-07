from __future__ import annotations

from datetime import UTC, datetime

from app.modules.auth.exceptions import (
    AccountExistsError,
    IdentityInUseError,
    LastSignInMethodError,
    OAuthAccountNotLinkedError,
    ProviderAlreadyLinkedError,
)
from app.modules.auth.models import OAuthAccount, OAuthProvider
from app.modules.auth.providers.base import OAuthIdentity
from app.modules.auth.repository import (
    OAuthAccountRepository,
    PasswordCredentialRepository,
)
from app.modules.users.emails import normalize_email
from app.modules.users.models import User, UserEmail
from app.modules.users.repository import UserEmailRepository, UserRepository


class AuthService:
    def __init__(
        self,
        accounts: OAuthAccountRepository,
        users: UserRepository,
        emails: UserEmailRepository,
        credentials: PasswordCredentialRepository,
    ) -> None:
        self._accounts = accounts
        self._users = users
        self._emails = emails
        self._credentials = credentials

    async def sign_in_with_oauth(self, oauth_identity: OAuthIdentity) -> User:
        now = datetime.now(UTC)

        account = await self._accounts.get_by_provider_user_id(
            oauth_identity.provider, oauth_identity.provider_user_id
        )

        if account is not None:
            account.email_snapshot = oauth_identity.email

            user = await self._users.get(account.user_id)

            if user is None:
                raise RuntimeError("OAuth account references a missing user.")

            user.last_sign_in_at = now

            if oauth_identity.avatar_url:
                user.avatar_url = oauth_identity.avatar_url

            return user

        verified_email = oauth_identity.verified_email

        # Someone already owns this address. It may well be the same person,
        # but a matching email proves nothing about that: never attach to an
        # account on email alone. They sign in there and link this provider.
        if (
            verified_email is not None
            and await self._emails.get_verified(normalize_email(verified_email))
            is not None
        ):
            raise AccountExistsError

        user = User(
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
                email_snapshot=oauth_identity.email,
            )
        )

        # Without a provider-verified email, the user simply has none yet.
        if verified_email is not None:
            self._emails.add(
                UserEmail(
                    user=user, email=verified_email, verified_at=now, is_primary=True
                )
            )

        return user

    async def owns_oauth_identity(
        self, user: User, oauth_identity: OAuthIdentity
    ) -> bool:
        account = await self._accounts.get_by_provider_user_id(
            oauth_identity.provider, oauth_identity.provider_user_id
        )

        return account is not None and account.user_id == user.id

    async def link_oauth_account(
        self, user: User, oauth_identity: OAuthIdentity
    ) -> None:
        """Add a provider account to `user`'s sign-in methods."""

        account = await self._accounts.get_by_provider_user_id(
            oauth_identity.provider, oauth_identity.provider_user_id
        )

        if account is not None:
            if account.user_id == user.id:
                return

            raise IdentityInUseError

        if await self._accounts.get_for_user(user.id, oauth_identity.provider):
            raise ProviderAlreadyLinkedError

        self._accounts.add(
            OAuthAccount(
                user=user,
                provider=oauth_identity.provider,
                provider_user_id=oauth_identity.provider_user_id,
                email_snapshot=oauth_identity.email,
            )
        )

        # The provider vouches for this address and no one else has verified
        # it: it's the user's too. It's primary only if they had none.
        verified_email = oauth_identity.verified_email

        if (
            verified_email is not None
            and await self._emails.get_verified(normalize_email(verified_email)) is None
        ):
            self._emails.add(
                UserEmail(
                    user=user,
                    email=verified_email,
                    verified_at=datetime.now(UTC),
                    is_primary=await self._emails.get_primary(user.id) is None,
                )
            )

    async def unlink_oauth_account(self, user: User, provider: OAuthProvider) -> None:
        """Remove a provider account, unless it's the user's last way in."""

        # Two concurrent unlinks could each see another method left and
        # together remove both; the lock makes the second see the first.
        await self._users.lock(user.id)

        account = await self._accounts.get_for_user(user.id, provider)

        if account is None:
            raise OAuthAccountNotLinkedError

        remaining = len(await self._accounts.list_for_user(user.id)) - 1

        if remaining == 0 and await self._credentials.get(user.id) is None:
            raise LastSignInMethodError

        await self._accounts.delete(account)
