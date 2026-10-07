from __future__ import annotations

from datetime import UTC, datetime

from app.modules.auth.exceptions import AccountExistsError
from app.modules.auth.models import PasswordCredential
from app.modules.auth.passwords import hash_password, needs_rehash, verify_password
from app.modules.auth.repository import PasswordCredentialRepository
from app.modules.users.emails import EmailNotValidError, normalize_email
from app.modules.users.models import User, UserEmail
from app.modules.users.repository import UserEmailRepository, UserRepository


class PasswordService:
    def __init__(
        self,
        users: UserRepository,
        emails: UserEmailRepository,
        credentials: PasswordCredentialRepository,
    ) -> None:
        self._users = users
        self._emails = emails
        self._credentials = credentials

    async def authenticate(self, address: str, password: str) -> User | None:
        """The active user whose verified email and password these are, or
        None. Every failure takes about as long as a wrong password, so the
        timing doesn't tell whether the account exists."""

        try:
            normalized = normalize_email(address)
        except EmailNotValidError:
            normalized = None

        email = normalized and await self._emails.get_verified(normalized)
        credential = email and await self._credentials.get(email.user_id)

        if not await verify_password(
            credential.password_hash if credential else None, password
        ):
            return None

        assert credential is not None
        user = await self._users.get(credential.user_id)

        if user is None or not user.is_active:
            return None

        await self._upgrade_hash(credential, password)
        user.last_sign_in_at = datetime.now(UTC)

        return user

    async def verify(self, user: User, password: str) -> bool:
        """Whether `password` is the user's: reauthentication."""

        credential = await self._credentials.get(user.id)

        if not await verify_password(
            credential.password_hash if credential else None, password
        ):
            return False

        assert credential is not None
        await self._upgrade_hash(credential, password)

        return True

    async def create_account(self, *, address: str, name: str, password: str) -> User:
        """A new user signing up with an email they've just proven is theirs.

        Raises AccountExistsError if someone verified it meanwhile.
        """

        if await self._emails.get_verified(normalize_email(address)) is not None:
            raise AccountExistsError

        now = datetime.now(UTC)
        user = User(full_name=name, last_sign_in_at=now)
        self._users.add(user)
        self._emails.add(
            UserEmail(user=user, email=address, verified_at=now, is_primary=True)
        )
        self._credentials.add(
            PasswordCredential(user=user, password_hash=await hash_password(password))
        )

        return user

    async def _upgrade_hash(
        self, credential: PasswordCredential, password: str
    ) -> None:
        # The password is at hand only now: re-hash with the current
        # parameters if they've changed since it was set.
        if needs_rehash(credential.password_hash):
            credential.password_hash = await hash_password(password)
