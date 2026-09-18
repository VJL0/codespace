from __future__ import annotations

from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import DbSession
from app.core.config import settings
from app.modules.auth.service import upsert_google_user
from app.modules.auth.session import create_session, set_session_cookie

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "code_challenge_method": "S256",
    },
)


@router.get("/login")
async def google_login(request: Request) -> RedirectResponse:
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/callback")
async def google_callback(request: Request, db: DbSession) -> RedirectResponse:
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google sign-in failed.",
        ) from exc

    claims = token.get("userinfo")

    if claims is None or not claims.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return account details.",
        )

    if not claims.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is not verified.",
        )

    user = await upsert_google_user(
        db,
        google_sub=claims["sub"],
        email=claims["email"],
        full_name=claims.get("name"),
        avatar_url=claims.get("picture"),
    )
    session_token = await create_session(db, user_id=user.id)
    await db.commit()

    response = RedirectResponse(url=str(settings.frontend_url))
    set_session_cookie(response, token=session_token)

    return response
