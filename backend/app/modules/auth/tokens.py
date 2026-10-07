from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import EmailToken, EmailTokenPurpose


def new_secret() -> str:
    """256 random bits, URL-safe: for session tokens and emailed links."""

    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    """The stored form of a random secret. A fast hash suffices: unlike a
    password, the secret has too much entropy to guess."""

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


async def issue_email_token(
    db: AsyncSession,
    purpose: EmailTokenPurpose,
    *,
    email: str,
    lifetime: timedelta,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> tuple[EmailToken, str]:
    """Add a token; return it and the secret to email, which isn't stored.

    The account's earlier unused tokens for `purpose` are spent, so only the
    newest link sent works.
    """

    if user_id is not None:
        await db.execute(
            update(EmailToken)
            .where(
                EmailToken.purpose == purpose,
                EmailToken.user_id == user_id,
                EmailToken.consumed_at.is_(None),
            )
            .values(consumed_at=func.now())
        )

    secret = new_secret()
    token = EmailToken(
        purpose=purpose,
        email=email,
        user_id=user_id,
        session_id=session_id,
        token_hash=hash_secret(secret),
        expires_at=datetime.now(UTC) + lifetime,
    )
    db.add(token)

    return token, secret


async def consume_email_token(
    db: AsyncSession,
    purpose: EmailTokenPurpose,
    secret: str,
    *,
    session_id: uuid.UUID | None = None,
) -> EmailToken | None:
    """Use up the live token for `secret`, or return None.

    One UPDATE, so of two concurrent uses only one gets the token. With
    `session_id`, only that session's token matches, and anyone else's
    attempt leaves it unspent.
    """

    conditions = [
        EmailToken.token_hash == hash_secret(secret),
        EmailToken.purpose == purpose,
        EmailToken.consumed_at.is_(None),
        EmailToken.expires_at > func.now(),
    ]

    if session_id is not None:
        conditions.append(EmailToken.session_id == session_id)

    return await db.scalar(
        update(EmailToken)
        .where(*conditions)
        .values(consumed_at=func.now())
        .returning(EmailToken)
    )
