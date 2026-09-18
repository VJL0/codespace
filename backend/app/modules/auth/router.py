from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import DbSession
from app.modules.auth.dependencies import AuthSessionToken
from app.modules.auth.session import clear_session_cookie, revoke_session

router = APIRouter()


@router.post("/logout", status_code=204)
async def logout(
    db: DbSession,
    session_token: AuthSessionToken = None,
) -> Response:
    if session_token is not None:
        await revoke_session(db, session_token)
        await db.commit()

    response = Response(status_code=204)
    clear_session_cookie(response)

    return response
