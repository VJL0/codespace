from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import UserSession

if TYPE_CHECKING:
    from fastapi import Response

TOKEN_BYTES = 32


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncSession, *, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)

    db.add(
        UserSession(
            user_id=user_id,
            token_hash=_hash_token(token),
        )
    )

    return token


async def get_user_id_for_session(db: AsyncSession, token: str) -> uuid.UUID | None:
    session_row = await db.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    )

    if session_row is None:
        return None

    now = datetime.now(UTC)

    idle_deadline = session_row.last_seen_at + timedelta(
        seconds=settings.auth_session_idle_timeout_seconds
    )
    absolute_deadline = session_row.created_at + timedelta(
        seconds=settings.auth_session_absolute_timeout_seconds
    )

    if now > idle_deadline or now > absolute_deadline:
        await db.delete(session_row)
        return None

    session_row.last_seen_at = now

    return session_row.user_id


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == _hash_token(token))
    )


def set_session_cookie(response: Response, *, token: str) -> None:
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=token,
        max_age=settings.auth_session_absolute_timeout_seconds,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
