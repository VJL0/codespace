from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import SessionDep
from app.core.config import settings
from app.modules.auth.dependencies import (
    AuthServiceDep,
    AuthSessionToken,
    CurrentUser,
    OAuthProviderRegistryDep,
    SessionServiceDep,
)
from app.modules.auth.exceptions import (
    AccountExistsError,
    OAuthProviderError,
    UnsupportedOAuthProviderError,
)
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import OAuthProviderAdapter
from app.modules.auth.providers.registry import OAuthProviderRegistry
from app.modules.auth.schemas import CurrentUserRead
from app.modules.auth.session import delete_session_cookie, set_session_cookie

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me")
async def get_me(current_user: CurrentUser) -> CurrentUserRead:
    return CurrentUserRead.model_validate(current_user)


@router.post("/logout", status_code=204)
async def logout(
    db: SessionDep,
    session_service: SessionServiceDep,
    session_token: AuthSessionToken = None,
) -> Response:
    if session_token is not None:
        await session_service.revoke_session(session_token)
        await db.commit()

    response = Response(status_code=204)
    delete_session_cookie(response)

    return response


def _get_adapter(
    registry: OAuthProviderRegistry, provider: OAuthProvider
) -> OAuthProviderAdapter:
    try:
        return registry.get(provider)
    except UnsupportedOAuthProviderError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Unknown sign-in provider."
        ) from exc


def _redirect_uri(provider: OAuthProvider) -> str:
    return f"{settings.api_url}/api/auth/{provider.value}/callback"


def _frontend_redirect(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""

    return RedirectResponse(f"{settings.frontend_url}{path}{query}", status_code=303)


@router.get("/{provider}/login")
async def start_oauth_login(
    provider: OAuthProvider, request: Request, registry: OAuthProviderRegistryDep
) -> RedirectResponse:
    adapter = _get_adapter(registry, provider)

    try:
        return await adapter.start_authorization(request, _redirect_uri(provider))
    except OAuthProviderError as exc:
        logger.warning("OAuth start failed for %s: %s", provider.value, exc)
        return _frontend_redirect("/login", error="oauth_failed")


@router.get("/{provider}/callback")
async def handle_oauth_callback(
    provider: OAuthProvider,
    request: Request,
    db: SessionDep,
    registry: OAuthProviderRegistryDep,
    auth_service: AuthServiceDep,
    session_service: SessionServiceDep,
    session_token: AuthSessionToken = None,
) -> RedirectResponse:
    adapter = _get_adapter(registry, provider)

    try:
        identity = await adapter.resolve_identity(request)
    except OAuthProviderError as exc:
        logger.warning("OAuth callback failed for %s: %s", provider.value, exc)
        return _frontend_redirect("/login", error="oauth_failed")

    if not identity.email_verified:
        return _frontend_redirect("/login", error="email_unverified")

    try:
        user = await auth_service.sign_in_with_oauth(identity)
    except AccountExistsError:
        return _frontend_redirect("/login", error="account_exists")

    if session_token is not None:
        await session_service.revoke_session(session_token)

    new_session_token = session_service.create_session(user=user)
    await db.commit()

    response = _frontend_redirect("/")
    set_session_cookie(response, token=new_session_token)

    return response
