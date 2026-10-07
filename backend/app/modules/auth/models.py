from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.users.models import User


class OAuthProvider(enum.StrEnum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"


class UserSession(TimestampMixin, Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Hex SHA-256 of the session token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)

    # The last time the person proved they're present (a password, an email
    # link, a provider reauthentication that forced credential entry). A
    # plain provider sign-in leaves it unset: its SSO proves nothing about
    # who is at the keyboard now.
    authenticated_at: Mapped[datetime | None]

    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    expires_at: Mapped[datetime]

    user: Mapped[User] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("created_at < expires_at", name="expires_after_created"),
    )

    def __repr__(self) -> str:
        return f"UserSession(id={self.id!s}, user_id={self.user_id!s})"


class OAuthAccount(TimestampMixin, Base):
    """A provider account a user signs in with, at most one per provider
    (User 1 ─── * OAuthAccount).

    provider_user_id is the provider's immutable user ID, never an email or
    username: Google's `sub`, Microsoft's "<oid>.<tid>", GitHub's numeric `id`.
    """

    __tablename__ = "oauth_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    provider: Mapped[OAuthProvider] = mapped_column(
        Enum(
            OAuthProvider,
            name="oauth_provider",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
    )

    # 255: OIDC caps `sub` at 255 ASCII characters; Microsoft's two GUIDs
    # (73 characters) and a GitHub int64 ID are shorter.
    provider_user_id: Mapped[str] = mapped_column(String(255))

    # The email the provider last reported, for display only: it identifies
    # nothing and proves nothing (verified addresses live in user_emails).
    email_snapshot: Mapped[str | None] = mapped_column(String(254))

    user: Mapped[User] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id"),
        UniqueConstraint("user_id", "provider"),
        CheckConstraint(
            "length(provider_user_id) > 0", name="provider_user_id_not_empty"
        ),
    )

    @validates("email_snapshot")
    def strip_email_snapshot(self, key: str, value: str | None) -> str | None:
        return (value or "").strip() or None

    def __repr__(self) -> str:
        return (
            "OAuthAccount("
            f"id={self.id!s}, "
            f"user_id={self.user_id!s}, "
            f"provider={self.provider.value!r}"
            ")"
        )


class PasswordCredential(TimestampMixin, Base):
    """A user's password, if they set one (User 1 ─── 0..1 PasswordCredential).

    updated_at is when it last changed.
    """

    __tablename__ = "password_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    # The Argon2id PHC string; it carries its own salt and parameters.
    password_hash: Mapped[str] = mapped_column(Text)

    user: Mapped[User] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return f"PasswordCredential(user_id={self.user_id!s})"


class EmailTokenPurpose(enum.StrEnum):
    SIGNUP = "signup"
    PASSWORD_RESET = "password_reset"
    PASSWORD_SETUP = "password_setup"
    REAUTHENTICATION = "reauthentication"


class EmailToken(TimestampMixin, Base):
    """A single-use secret emailed to prove someone receives mail at `email`.

    Only a hash of the secret is stored, so these rows alone can't be used.
    """

    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        Enum(
            EmailTokenPurpose,
            name="email_token_purpose",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
    )

    # Where the secret was sent.
    email: Mapped[str] = mapped_column(String(254))

    # Whose account it's for; none for a signup, which has no account yet.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # The session a reauthentication link confirms; only that session may
    # complete it.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE")
    )

    # Hex SHA-256 of the secret.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)

    expires_at: Mapped[datetime]

    consumed_at: Mapped[datetime | None]

    def __repr__(self) -> str:
        return f"EmailToken(id={self.id!s}, purpose={self.purpose.value!r})"


class RateLimitCounter(Base):
    """Attempts under `key` in the fixed window starting at `window_start`."""

    __tablename__ = "rate_limit_counters"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)

    window_start: Mapped[datetime] = mapped_column(primary_key=True)

    hits: Mapped[int]
