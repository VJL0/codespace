from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class UserSession(TimestampMixin, Base):
    """
    Server-side record backing an opaque session cookie.

    Only a hash of the cookie's random token is stored, never the token
    itself, so reading this table (e.g. from a backup) can't be used to
    forge a valid cookie. Revoking a session (logout) means deleting the
    row here - the cookie alone is worthless without a matching row.

    `created_at` (from TimestampMixin) anchors the absolute timeout;
    `last_seen_at` slides forward on each use and anchors the idle timeout.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "token_hash",
            name="uq_user_sessions_token_hash",
        ),
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_last_seen_at", "last_seen_at"),
    )

    def __repr__(self) -> str:
        return f"UserSession(id={self.id!s}, user_id={self.user_id!s})"
