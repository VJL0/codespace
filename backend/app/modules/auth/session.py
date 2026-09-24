from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import UserSession

if TYPE_CHECKING:
    from fastapi import Response

TOKEN_BYTES = 32
SESSION_COOKIE_NAME = "__Host-Http-session"
SESSION_ABSOLUTE_TIMEOUT = timedelta(days=14)


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

    idle_deadline = session_row.last_seen_at + timedelta(minutes=30)
    absolute_deadline = session_row.created_at + SESSION_ABSOLUTE_TIMEOUT

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
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(SESSION_ABSOLUTE_TIMEOUT.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
