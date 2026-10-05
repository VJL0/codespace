from __future__ import annotations

from datetime import UTC, datetime

from app.modules.auth.exceptions import AccountExistsError
from app.modules.auth.models import OAuthAccount
from app.modules.auth.providers.base import OAuthIdentity
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.users.emails import normalize_email
from app.modules.users.models import User, UserEmail
from app.modules.users.repository import UserEmailRepository, UserRepository


class AuthService:
    def __init__(
        self,
        accounts: OAuthAccountRepository,
        users: UserRepository,
        emails: UserEmailRepository,
    ) -> None:
        self._accounts = accounts
        self._users = users
        self._emails = emails

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
