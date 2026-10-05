from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import SessionDep
from app.core.config import settings
from app.modules.auth.audit import audit
from app.modules.auth.dependencies import (
    AuthServiceDep,
    AuthSessionToken,
    CurrentSession,
    CurrentUser,
    OAuthProviderRegistryDep,
    OptionalSession,
    RecentlyAuthenticatedSession,
    SessionServiceDep,
)
from app.modules.auth.exceptions import (
    AccountExistsError,
    IdentityInUseError,
    LastSignInMethodError,
    OAuthAccountNotLinkedError,
    OAuthProviderError,
    ProviderAlreadyLinkedError,
    UnsupportedOAuthProviderError,
)
from app.modules.auth.models import OAuthProvider, UserSession
from app.modules.auth.providers.base import (
    OAuthIdentity,
    OAuthProviderAdapter,
    OAuthPurpose,
    OAuthTransaction,
)
from app.modules.auth.providers.registry import OAuthProviderRegistry
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.auth.schemas import (
    AuthorizationRead,
    CurrentUserRead,
    EmailRead,
    IdentityRead,
    SignInMethodsRead,
)
from app.modules.auth.service import AuthService
from app.modules.auth.session import (
    SessionService,
    delete_session_cookie,
    finish_sign_in,
    is_recently_authenticated,
    set_session_cookie,
)
from app.modules.users.repository import UserEmailRepository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me")
async def get_me(current_user: CurrentUser, db: SessionDep) -> CurrentUserRead:
    primary_email = await UserEmailRepository(db).get_primary(current_user.id)

    return CurrentUserRead(
        name=current_user.full_name,
        email=primary_email.email if primary_email else None,
        avatar_url=current_user.avatar_url,
    )


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


@router.post("/logout-all", status_code=204)
async def logout_all(
    current_user: CurrentUser, db: SessionDep, session_service: SessionServiceDep
) -> Response:
    """Sign out every browser, this one included."""

    await session_service.revoke_all_sessions(current_user)
    await db.commit()
    audit("auth.sessions.revoked_all", user_id=current_user.id)

    response = Response(status_code=204)
    delete_session_cookie(response)

    return response


@router.get("/methods")
async def get_sign_in_methods(
    current_session: CurrentSession, db: SessionDep, registry: OAuthProviderRegistryDep
) -> SignInMethodsRead:
    user_id = current_session.user_id
    accounts = await OAuthAccountRepository(db).list_for_user(user_id)
    emails = await UserEmailRepository(db).list_for_user(user_id)

    return SignInMethodsRead(
        identities=[
            IdentityRead(
                provider=account.provider,
                email_snapshot=account.email_snapshot,
                created_at=account.created_at,
            )
            for account in accounts
        ],
        emails=[
            EmailRead(
                email=email.email,
                is_primary=email.is_primary,
                verified=email.verified_at is not None,
            )
            for email in emails
        ],
        reauthentication_providers=[
            account.provider
            for account in accounts
            if registry.get(account.provider).forced_reauth_params() is not None
        ],
        recently_authenticated=is_recently_authenticated(current_session),
    )


@router.delete("/identities/{provider}", status_code=204)
async def unlink_oauth_account(
    provider: OAuthProvider,
    user_session: RecentlyAuthenticatedSession,
    db: SessionDep,
    auth_service: AuthServiceDep,
) -> Response:
    try:
        await auth_service.unlink_oauth_account(user_session.user, provider)
    except OAuthAccountNotLinkedError as exc:
        raise _api_error(
            status.HTTP_404_NOT_FOUND, "not_linked", "That account isn't linked."
        ) from exc
    except LastSignInMethodError as exc:
        raise _api_error(
            status.HTTP_409_CONFLICT,
            "last_method",
            "This is your only way to sign in. Add another one first.",
        ) from exc

    await db.commit()
    audit("auth.oauth.unlinked", user_id=user_session.user_id, provider=provider.value)

    return Response(status_code=204)


def _api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message})


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
    return f"{settings.app_url}/api/auth/{provider.value}/callback"


def _frontend_redirect(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""

    return RedirectResponse(f"{settings.app_url}{path}{query}", status_code=303)


# Where each kind of flow returns the browser, and what its failure is called
# in the audit log.
_FLOW_PAGES = {
    OAuthPurpose.LOGIN: ("/login", "auth.login.failed"),
    OAuthPurpose.LINK: ("/settings", "auth.oauth.link_failed"),
    OAuthPurpose.REAUTHENTICATE: ("/settings", "auth.reauthentication.failed"),
}


def _failed_flow(
    provider: OAuthProvider, purpose: OAuthPurpose, error: str
) -> RedirectResponse:
    page, event = _FLOW_PAGES[purpose]
    audit(event, provider=provider.value, reason=error)

    return _frontend_redirect(page, error=error)


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


async def _authorization(
    adapter: OAuthProviderAdapter,
    request: Request,
    purpose: OAuthPurpose,
    user_session: UserSession,
) -> AuthorizationRead:
    try:
        url = await adapter.authorization_url(
            request,
            _redirect_uri(adapter.provider),
            purpose=purpose,
            user_id=user_session.user_id,
        )
    except OAuthProviderError as exc:
        logger.warning("OAuth start failed for %s: %s", adapter.provider.value, exc)
        raise _api_error(
            status.HTTP_502_BAD_GATEWAY,
            "oauth_failed",
            "The provider couldn't be reached. Try again.",
        ) from exc

    return AuthorizationRead(authorization_url=url)


@router.post("/{provider}/link")
async def start_oauth_link(
    provider: OAuthProvider,
    request: Request,
    user_session: RecentlyAuthenticatedSession,
    db: SessionDep,
    registry: OAuthProviderRegistryDep,
) -> AuthorizationRead:
    """Start linking a provider account; the SPA sends the browser to the
    returned URL. Requires a recent fresh authentication, so a stolen or
    unattended session can't attach someone else's account."""

    adapter = _get_adapter(registry, provider)

    if await OAuthAccountRepository(db).get_for_user(user_session.user_id, provider):
        raise _api_error(
            status.HTTP_409_CONFLICT,
            "provider_already_linked",
            "You already have an account with this provider linked.",
        )

    return await _authorization(adapter, request, OAuthPurpose.LINK, user_session)


@router.post("/{provider}/reauthenticate")
async def start_oauth_reauthentication(
    provider: OAuthProvider,
    request: Request,
    user_session: CurrentSession,
    db: SessionDep,
    registry: OAuthProviderRegistryDep,
) -> AuthorizationRead:
    """Start confirming it's the user, with a provider that will make them
    enter their credentials again."""

    adapter = _get_adapter(registry, provider)

    if adapter.forced_reauth_params() is None:
        raise _api_error(
            status.HTTP_400_BAD_REQUEST,
            "reauth_unsupported",
            "This provider can't confirm it's you.",
        )

    if not await OAuthAccountRepository(db).get_for_user(
        user_session.user_id, provider
    ):
        raise _api_error(
            status.HTTP_409_CONFLICT, "not_linked", "That account isn't linked."
        )

    return await _authorization(
        adapter, request, OAuthPurpose.REAUTHENTICATE, user_session
    )


@router.get("/{provider}/callback")
async def handle_oauth_callback(
    provider: OAuthProvider,
    request: Request,
    db: SessionDep,
    registry: OAuthProviderRegistryDep,
    auth_service: AuthServiceDep,
    session_service: SessionServiceDep,
    current_session: OptionalSession,
    session_token: AuthSessionToken = None,
) -> RedirectResponse:
    adapter = _get_adapter(registry, provider)
    transaction = await adapter.get_transaction(request)
    purpose = transaction.purpose if transaction else OAuthPurpose.LOGIN

    try:
        identity = await adapter.resolve_identity(request)
    except OAuthProviderError as exc:
        logger.warning("OAuth callback failed for %s: %s", provider.value, exc)
        return _failed_flow(provider, purpose, "oauth_failed")

    # resolve_identity() succeeding means the state matched a flow this
    # browser started, so its transaction was there.
    assert transaction is not None

    match purpose:
        case OAuthPurpose.LINK:
            return await _finish_link(
                identity, transaction, current_session, auth_service, db
            )
        case OAuthPurpose.REAUTHENTICATE:
            return await _finish_reauthentication(
                adapter,
                identity,
                transaction,
                current_session,
                auth_service,
                session_service,
                db,
            )

    try:
        user = await auth_service.sign_in_with_oauth(identity)
    except AccountExistsError:
        return _failed_flow(provider, purpose, "account_exists")

    response = _frontend_redirect("/")
    # Not fresh: the provider may have answered from its SSO session.
    await finish_sign_in(
        db,
        session_service,
        response,
        user=user,
        previous_token=session_token,
        fresh=False,
    )
    audit("auth.login.succeeded", user_id=user.id, provider=provider.value)

    return response


async def _finish_link(
    identity: OAuthIdentity,
    transaction: OAuthTransaction,
    current_session: UserSession | None,
    auth_service: AuthService,
    db: SessionDep,
) -> RedirectResponse:
    provider = identity.provider

    # Still signed in as whoever started the flow.
    if current_session is None or current_session.user_id != transaction.user_id:
        return _failed_flow(provider, transaction.purpose, "link_failed")

    try:
        await auth_service.link_oauth_account(current_session.user, identity)
    except IdentityInUseError:
        return _failed_flow(provider, transaction.purpose, "identity_in_use")
    except ProviderAlreadyLinkedError:
        return _failed_flow(provider, transaction.purpose, "provider_already_linked")

    await db.commit()
    audit("auth.oauth.linked", user_id=current_session.user_id, provider=provider.value)

    return _frontend_redirect("/settings", linked=provider.value)


async def _finish_reauthentication(
    adapter: OAuthProviderAdapter,
    identity: OAuthIdentity,
    transaction: OAuthTransaction,
    current_session: UserSession | None,
    auth_service: AuthService,
    session_service: SessionService,
    db: SessionDep,
) -> RedirectResponse:
    provider = identity.provider

    # The same person, signed in at the provider as one of their own linked
    # accounts, having entered their credentials just now.
    if (
        current_session is None
        or current_session.user_id != transaction.user_id
        or not await auth_service.owns_oauth_identity(current_session.user, identity)
        or not adapter.is_fresh(identity, transaction)
    ):
        return _failed_flow(provider, transaction.purpose, "reauth_failed")

    token = session_service.reauthenticate(current_session)
    await db.commit()
    audit(
        "auth.reauthenticated", user_id=current_session.user_id, provider=provider.value
    )

    response = _frontend_redirect("/settings", reauthenticated=provider.value)
    set_session_cookie(response, token=token)

    return response
