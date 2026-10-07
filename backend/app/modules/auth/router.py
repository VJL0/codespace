"""Sessions, the signed-in user and their sign-in methods, and signing in
with or linking a Google, Microsoft or GitHub account."""

from __future__ import annotations

import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OAuthProvidersDep, SessionDep
from app.api.errors import api_error
from app.core.config import settings
from app.modules.auth import service
from app.modules.auth.audit import audit
from app.modules.auth.dependencies import (
    CurrentSession,
    CurrentUser,
    OptionalSession,
    RecentlyAuthenticatedSession,
    SessionToken,
)
from app.modules.auth.models import OAuthProvider, UserSession
from app.modules.auth.providers.base import OAuthIdentity, OAuthProviderError
from app.modules.auth.schemas import (
    AuthorizationRead,
    CurrentUserRead,
    EmailRead,
    IdentityRead,
    SignInMethodsRead,
)
from app.modules.auth.session import (
    delete_session_cookie,
    is_recently_authenticated,
    revoke_session,
    revoke_sessions,
    start_session,
)
from app.modules.users.service import get_primary_email, list_emails

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me")
async def get_me(current_user: CurrentUser, db: SessionDep) -> CurrentUserRead:
    primary_email = await get_primary_email(db, current_user.id)

    return CurrentUserRead(
        name=current_user.full_name,
        email=primary_email.email if primary_email else None,
        avatar_url=current_user.avatar_url,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response, db: SessionDep, session_token: SessionToken = None
) -> None:
    if session_token is not None:
        await revoke_session(db, session_token)
        await db.commit()

    delete_session_cookie(response)


@router.post("/logout-all", status_code=204)
async def logout_all(
    response: Response, current_user: CurrentUser, db: SessionDep
) -> None:
    """Sign out every browser, this one included."""

    await revoke_sessions(db, current_user.id)
    await db.commit()
    delete_session_cookie(response)
    audit("auth.sessions.revoked_all", user_id=current_user.id)


@router.get("/methods")
async def get_sign_in_methods(
    current_session: CurrentSession, db: SessionDep
) -> SignInMethodsRead:
    user_id = current_session.user_id

    return SignInMethodsRead(
        has_password=await service.has_password(db, user_id),
        identities=[
            IdentityRead(
                provider=account.provider,
                email_snapshot=account.email_snapshot,
                created_at=account.created_at,
            )
            for account in await service.list_oauth_accounts(db, user_id)
        ],
        emails=[
            EmailRead(
                email=email.email,
                is_primary=email.is_primary,
                verified=email.verified_at is not None,
            )
            for email in await list_emails(db, user_id)
        ],
        recently_authenticated=is_recently_authenticated(current_session),
    )


@router.delete("/identities/{provider}", status_code=204)
async def unlink_oauth_account(
    provider: OAuthProvider,
    user_session: RecentlyAuthenticatedSession,
    db: SessionDep,
) -> None:
    await service.unlink_oauth_account(db, user_session.user_id, provider)
    await db.commit()
    audit("auth.oauth.unlinked", user_id=user_session.user_id, provider=provider.value)


# --- Provider flows ------------------------------------------------------------


def _redirect_uri(provider: OAuthProvider) -> str:
    return f"{settings.app_url}/api/auth/{provider.value}/callback"


def _frontend_redirect(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""

    return RedirectResponse(f"{settings.app_url}{path}{query}", status_code=303)


def _failed_flow(
    provider: OAuthProvider, error: str, *, linking: bool
) -> RedirectResponse:
    """Back to the page the flow started from, with `error` for it to show."""

    page, event = (
        ("/settings", "auth.oauth.link_failed")
        if linking
        else ("/login", "auth.login.failed")
    )
    audit(event, provider=provider.value, reason=error)

    return _frontend_redirect(page, error=error)


@router.get("/{provider}/login")
async def start_oauth_login(
    provider: OAuthProvider, request: Request, providers: OAuthProvidersDep
) -> RedirectResponse:
    try:
        url = await providers[provider].authorization_url(
            request, _redirect_uri(provider)
        )
    except OAuthProviderError as exc:
        logger.warning("OAuth start failed for %s: %s", provider.value, exc)
        return _frontend_redirect("/login", error="oauth_failed")

    return RedirectResponse(url, status_code=302)


@router.post("/{provider}/link")
async def start_oauth_link(
    provider: OAuthProvider,
    request: Request,
    user_session: RecentlyAuthenticatedSession,
    db: SessionDep,
    providers: OAuthProvidersDep,
) -> AuthorizationRead:
    """Start linking a provider account; the SPA sends the browser to the
    returned URL. Requires a recent fresh authentication, so a stolen or
    unattended session can't attach someone else's account."""

    await service.ensure_provider_unlinked(db, user_session.user_id, provider)

    try:
        url = await providers[provider].authorization_url(
            request, _redirect_uri(provider), link_user_id=user_session.user_id
        )
    except OAuthProviderError as exc:
        logger.warning("OAuth start failed for %s: %s", provider.value, exc)
        raise api_error(
            status.HTTP_502_BAD_GATEWAY,
            "oauth_failed",
            "The provider couldn't be reached. Try again.",
        ) from exc

    return AuthorizationRead(authorization_url=url)


@router.get("/{provider}/callback")
async def handle_oauth_callback(
    provider: OAuthProvider,
    request: Request,
    db: SessionDep,
    providers: OAuthProvidersDep,
    current_session: OptionalSession,
    session_token: SessionToken = None,
) -> RedirectResponse:
    adapter = providers[provider]
    # Read first: resolve_identity() consumes the flow's state.
    link_user_id = await adapter.link_user_id(request)

    try:
        identity = await adapter.resolve_identity(request)
    except OAuthProviderError as exc:
        logger.warning("OAuth callback failed for %s: %s", provider.value, exc)
        return _failed_flow(provider, "oauth_failed", linking=link_user_id is not None)

    if link_user_id is not None:
        return await _finish_link(db, identity, link_user_id, current_session)

    try:
        user = await service.sign_in_with_oauth(db, identity)
    except HTTPException as exc:
        # A refused sign-in goes back to the SPA by its code, as `?error=`.
        return _failed_flow(provider, exc.detail["code"], linking=False)

    response = _frontend_redirect("/")
    # Not fresh: the provider may have answered from its SSO session.
    await start_session(
        db, response, user=user, fresh=False, previous_token=session_token
    )
    audit("auth.login.succeeded", user_id=user.id, provider=provider.value)

    return response


async def _finish_link(
    db: AsyncSession,
    identity: OAuthIdentity,
    link_user_id: uuid.UUID,
    current_session: UserSession | None,
) -> RedirectResponse:
    provider = identity.provider

    # Still signed in as whoever started the flow.
    if current_session is None or current_session.user_id != link_user_id:
        return _failed_flow(provider, "link_failed", linking=True)

    try:
        await service.link_oauth_account(db, current_session.user, identity)
    except HTTPException as exc:
        return _failed_flow(provider, exc.detail["code"], linking=True)

    await db.commit()
    audit("auth.oauth.linked", user_id=current_session.user_id, provider=provider.value)

    return _frontend_redirect("/settings", linked=provider.value)
