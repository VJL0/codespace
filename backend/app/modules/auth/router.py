from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbSession
from app.modules.auth.dependencies import AuthSessionToken, CurrentUser
from app.modules.auth.session import clear_session_cookie, revoke_session

router = APIRouter()


class CurrentUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    email: str
    full_name: str | None
    avatar_url: str | None


@router.get("/me")
async def get_me(current_user: CurrentUser) -> CurrentUserRead:
    return CurrentUserRead.model_validate(current_user)


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
