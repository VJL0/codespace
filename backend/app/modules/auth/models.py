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
