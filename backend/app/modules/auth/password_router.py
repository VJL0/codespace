"""Email-and-password sign-up and sign-in, the reauthentication a password
or an emailed link provides, and managing the password itself: resetting,
adding, changing and removing it."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.api.deps import SessionDep
from app.api.errors import api_error
from app.modules.auth import emails
from app.modules.auth.audit import audit
from app.modules.auth.dependencies import (
    AuthServiceDep,
    AuthSessionToken,
    CurrentSession,
    EmailSenderDep,
    EmailTokensDep,
    HttpClientDep,
    PasswordServiceDep,
    RateLimiterDep,
    RecentlyAuthenticatedSession,
    SessionServiceDep,
)
from app.modules.auth.exceptions import (
    AccountExistsError,
    LastSignInMethodError,
    PasswordAlreadySetError,
    PasswordNotSetError,
)
from app.modules.auth.models import EmailTokenPurpose
from app.modules.auth.passwords import PasswordPolicyError, check_password_policy
from app.modules.auth.rate_limit import (
    RateLimitedError,
    RateLimiter,
    email_key,
    ip_key,
)
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    EmailRequest,
    LoginRequest,
    PasswordRequest,
    PasswordTokenRequest,
    RegisterCompleteRequest,
    TokenRequest,
)
from app.modules.auth.session import (
    delete_session_cookie,
    finish_sign_in,
    set_session_cookie,
)
from app.modules.auth.tokens import EmailTokenRepository
from app.modules.users.emails import EmailNotValidError, normalize_email
from app.modules.users.repository import UserEmailRepository

router = APIRouter()


async def _limit(
    limiter: RateLimiter,
    db: SessionDep,
    *buckets: tuple[str, int, timedelta],
) -> None:
    """Count the attempt in each (key, limit, window) bucket, committed
    whatever happens next; refuse with 429 once one is full."""

    try:
        for key, limit, window in buckets:
            await limiter.hit(key, limit=limit, window=window)
    except RateLimitedError as exc:
        await db.commit()
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many attempts. Wait a while and try again.",
            headers={"Retry-After": str(int(exc.retry_after.total_seconds()) + 1)},
        ) from exc

    await db.commit()


def _valid_email(address: str) -> str:
    try:
        normalize_email(address)
    except EmailNotValidError as exc:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_email",
            "Enter a valid email address.",
        ) from exc

    return address.strip()


async def _check_policy(password: str, http_client: HttpClientDep) -> None:
    try:
        await check_password_policy(password, http_client)
    except PasswordPolicyError as exc:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, str(exc)
        ) from exc


def _send(
    background_tasks: BackgroundTasks,
    email_sender: EmailSenderDep,
    *,
    to: str,
    message: emails.Message,
    idempotency_key: str,
) -> None:
    # After the response, so its timing doesn't reveal whether mail went out.
    background_tasks.add_task(
        email_sender.send,
        to=to,
        subject=message.subject,
        html=message.html,
        idempotency_key=idempotency_key,
    )


@router.post("/register", status_code=202)
async def register(
    body: EmailRequest,
    request: Request,
    db: SessionDep,
    limiter: RateLimiterDep,
    tokens: EmailTokensDep,
    email_sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> None:
    """Email-first sign-up: send a link that proves the address is theirs.
    No account, and no password, exists until it's opened.

    The response is the same whether or not the address has an account;
    only its owner learns which, from the email they get.
    """

    address = _valid_email(body.email)
    await _limit(
        limiter,
        db,
        (email_key("signup", address), 3, timedelta(hours=1)),
        (ip_key("signup", request), 20, timedelta(hours=1)),
    )

    if await UserEmailRepository(db).get_verified(normalize_email(address)):
        message = emails.account_exists()
        idempotency_key = f"account-exists/{uuid.uuid7()}"
    else:
        token, secret = tokens.issue(
            EmailTokenPurpose.SIGNUP, email=address, lifetime=timedelta(hours=1)
        )
        await db.commit()
        message = emails.signup(secret)
        idempotency_key = f"signup/{token.id}"

    _send(
        background_tasks,
        email_sender,
        to=address,
        message=message,
        idempotency_key=idempotency_key,
    )
    audit("auth.signup.requested")


@router.post("/register/complete", status_code=204)
async def complete_registration(
    body: RegisterCompleteRequest,
    response: Response,
    db: SessionDep,
    http_client: HttpClientDep,
    tokens: EmailTokensDep,
    passwords: PasswordServiceDep,
    session_service: SessionServiceDep,
    session_token: AuthSessionToken = None,
) -> None:
    # The policy first, so a password it refuses doesn't spend the link.
    await _check_policy(body.password, http_client)

    token = await tokens.consume(EmailTokenPurpose.SIGNUP, body.token)

    if token is None:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_token",
            "This link has expired or was already used. Sign up again.",
        )

    try:
        user = await passwords.create_account(
            address=token.email, name=body.name, password=body.password
        )
    except AccountExistsError as exc:
        await db.commit()
        raise api_error(
            status.HTTP_409_CONFLICT,
            "account_exists",
            "This email already has an account. Sign in instead.",
        ) from exc

    # Fresh: they just proved both the email and the password.
    await finish_sign_in(
        db,
        session_service,
        response,
        user=user,
        previous_token=session_token,
        fresh=True,
    )
    audit("auth.signup.completed", user_id=user.id)


@router.post("/login", status_code=204)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: SessionDep,
    limiter: RateLimiterDep,
    passwords: PasswordServiceDep,
    session_service: SessionServiceDep,
    session_token: AuthSessionToken = None,
) -> None:
    await _limit(
        limiter,
        db,
        (email_key("login", body.email), 10, timedelta(minutes=15)),
        (ip_key("login", request), 50, timedelta(minutes=15)),
    )

    user = await passwords.authenticate(body.email, body.password)

    if user is None:
        audit("auth.login.failed", method="password", reason="invalid_credentials")
        # One answer for an unknown email, an account without a password and
        # a wrong password alike.
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Incorrect email or password.",
        )

    await finish_sign_in(
        db,
        session_service,
        response,
        user=user,
        previous_token=session_token,
        fresh=True,
    )
    audit("auth.login.succeeded", user_id=user.id, method="password")


@router.post("/reauthenticate", status_code=204)
async def reauthenticate_with_password(
    body: PasswordRequest,
    response: Response,
    current_session: CurrentSession,
    db: SessionDep,
    limiter: RateLimiterDep,
    passwords: PasswordServiceDep,
    session_service: SessionServiceDep,
) -> None:
    await _limit(
        limiter,
        db,
        (f"reauth:user:{current_session.user_id}", 10, timedelta(minutes=15)),
    )

    if not await passwords.verify(current_session.user, body.password):
        audit(
            "auth.reauthentication.failed",
            user_id=current_session.user_id,
            method="password",
        )
        raise api_error(
            status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Incorrect password."
        )

    token = session_service.reauthenticate(current_session)
    await db.commit()
    set_session_cookie(response, token=token)
    audit("auth.reauthenticated", user_id=current_session.user_id, method="password")


@router.post("/reauthenticate/email", status_code=202)
async def send_reauthentication_email(
    current_session: CurrentSession,
    db: SessionDep,
    limiter: RateLimiterDep,
    tokens: EmailTokensDep,
    email_sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> None:
    """Email a link that confirms it's the user, usable only by this
    session: whoever opens it elsewhere can't reauthenticate theirs."""

    primary = await UserEmailRepository(db).get_primary(current_session.user_id)

    if primary is None:
        raise api_error(
            status.HTTP_409_CONFLICT, "no_email", "You have no email address to use."
        )

    await _limit(
        limiter,
        db,
        (f"reauth-email:user:{current_session.user_id}", 5, timedelta(hours=1)),
    )

    token, secret = tokens.issue(
        EmailTokenPurpose.REAUTHENTICATION,
        email=primary.email,
        lifetime=timedelta(minutes=15),
        user_id=current_session.user_id,
        session_id=current_session.id,
    )
    await db.commit()

    _send(
        background_tasks,
        email_sender,
        to=primary.email,
        message=emails.reauthentication(secret),
        idempotency_key=f"reauthentication/{token.id}",
    )


@router.post("/reauthenticate/email/complete", status_code=204)
async def complete_email_reauthentication(
    body: TokenRequest,
    response: Response,
    current_session: CurrentSession,
    db: SessionDep,
    tokens: EmailTokensDep,
    session_service: SessionServiceDep,
) -> None:
    token = await tokens.consume(
        EmailTokenPurpose.REAUTHENTICATION, body.token, session_id=current_session.id
    )

    if token is None:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_token",
            "This link has expired, was already used, or is for another browser.",
        )

    new_token = session_service.reauthenticate(current_session)
    await db.commit()
    set_session_cookie(response, token=new_token)
    audit("auth.reauthenticated", user_id=current_session.user_id, method="email")


@router.post("/password/forgot", status_code=202)
async def forgot_password(
    body: EmailRequest,
    request: Request,
    db: SessionDep,
    limiter: RateLimiterDep,
    tokens: EmailTokensDep,
    passwords: PasswordServiceDep,
    email_sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> None:
    """Email a reset link to a verified address whose account has a password.

    The response is the same either way, so this doesn't reveal accounts.
    """

    address = _valid_email(body.email)
    await _limit(
        limiter,
        db,
        (email_key("reset", address), 3, timedelta(hours=1)),
        (ip_key("reset", request), 20, timedelta(hours=1)),
    )
    audit("auth.password.reset_requested")

    email = await UserEmailRepository(db).get_verified(normalize_email(address))

    if email is None or not await passwords.has_password(email.user_id):
        return

    # Only the newest link works.
    await tokens.revoke(EmailTokenPurpose.PASSWORD_RESET, email.user_id)
    token, secret = tokens.issue(
        EmailTokenPurpose.PASSWORD_RESET,
        email=email.email,
        lifetime=timedelta(minutes=30),
        user_id=email.user_id,
    )
    await db.commit()

    _send(
        background_tasks,
        email_sender,
        to=email.email,
        message=emails.password_reset(secret),
        idempotency_key=f"password-reset/{token.id}",
    )


async def _use_password_token(
    purpose: EmailTokenPurpose,
    body: PasswordTokenRequest,
    http_client: HttpClientDep,
    tokens: EmailTokenRepository,
) -> uuid.UUID:
    """Check the new password, then spend the link; return whose it is."""

    # The policy first, so a password it refuses doesn't spend the link.
    await _check_policy(body.password, http_client)

    token = await tokens.consume(purpose, body.token)

    if token is None or token.user_id is None:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_token",
            "This link has expired or was already used. Ask for a new one.",
        )

    return token.user_id


@router.post("/password/reset", status_code=204)
async def reset_password(
    body: PasswordTokenRequest,
    response: Response,
    db: SessionDep,
    http_client: HttpClientDep,
    tokens: EmailTokensDep,
    passwords: PasswordServiceDep,
    session_service: SessionServiceDep,
) -> None:
    """Replace the password and sign out every session: whoever knew the old
    password is out. No automatic sign-in; the user signs in with the new
    one."""

    user_id = await _use_password_token(
        EmailTokenPurpose.PASSWORD_RESET, body, http_client, tokens
    )

    await passwords.set_password(user_id, body.password, replace=True)
    await session_service.revoke_all_sessions(user_id)
    await db.commit()

    delete_session_cookie(response)
    audit("auth.password.reset", user_id=user_id)


@router.post("/password/setup", status_code=202)
async def start_password_setup(
    user_session: RecentlyAuthenticatedSession,
    db: SessionDep,
    limiter: RateLimiterDep,
    tokens: EmailTokensDep,
    passwords: PasswordServiceDep,
    email_sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> None:
    """Add a password to an account that signs in with providers only, by a
    link to its primary email: the password and the email go together, as
    the email is what signing in with it and resetting it use."""

    if await passwords.has_password(user_session.user_id):
        raise api_error(
            status.HTTP_409_CONFLICT, "password_exists", "You already have a password."
        )

    primary = await UserEmailRepository(db).get_primary(user_session.user_id)

    if primary is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "no_email",
            "A password needs an email address to sign in with.",
        )

    await _limit(
        limiter,
        db,
        (f"password-setup:user:{user_session.user_id}", 5, timedelta(hours=1)),
    )

    await tokens.revoke(EmailTokenPurpose.PASSWORD_SETUP, user_session.user_id)
    token, secret = tokens.issue(
        EmailTokenPurpose.PASSWORD_SETUP,
        email=primary.email,
        lifetime=timedelta(minutes=30),
        user_id=user_session.user_id,
    )
    await db.commit()

    _send(
        background_tasks,
        email_sender,
        to=primary.email,
        message=emails.password_setup(secret),
        idempotency_key=f"password-setup/{token.id}",
    )


@router.post("/password/setup/complete", status_code=204)
async def complete_password_setup(
    body: PasswordTokenRequest,
    db: SessionDep,
    http_client: HttpClientDep,
    tokens: EmailTokensDep,
    passwords: PasswordServiceDep,
) -> None:
    user_id = await _use_password_token(
        EmailTokenPurpose.PASSWORD_SETUP, body, http_client, tokens
    )

    try:
        await passwords.set_password(user_id, body.password, replace=False)
    except PasswordAlreadySetError as exc:
        await db.commit()
        raise api_error(
            status.HTTP_409_CONFLICT, "password_exists", "You already have a password."
        ) from exc

    await db.commit()
    audit("auth.password.added", user_id=user_id)


@router.post("/password/change", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    current_session: CurrentSession,
    db: SessionDep,
    http_client: HttpClientDep,
    limiter: RateLimiterDep,
    passwords: PasswordServiceDep,
    session_service: SessionServiceDep,
) -> None:
    """Change the password, given the current one; every other session is
    signed out, and this one renewed."""

    await _limit(
        limiter,
        db,
        (f"reauth:user:{current_session.user_id}", 10, timedelta(minutes=15)),
    )

    if not await passwords.verify(current_session.user, body.current_password):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Your current password is incorrect.",
        )

    await _check_policy(body.new_password, http_client)
    await passwords.set_password(
        current_session.user_id, body.new_password, replace=True
    )
    await session_service.revoke_other_sessions(current_session)
    # Knowing the current password was a fresh authentication.
    token = session_service.reauthenticate(current_session)
    await db.commit()

    set_session_cookie(response, token=token)
    audit("auth.password.changed", user_id=current_session.user_id)


@router.delete("/password", status_code=204)
async def remove_password(
    user_session: RecentlyAuthenticatedSession,
    db: SessionDep,
    auth_service: AuthServiceDep,
) -> None:
    try:
        await auth_service.remove_password(user_session.user)
    except PasswordNotSetError as exc:
        raise api_error(
            status.HTTP_404_NOT_FOUND, "no_password", "You have no password."
        ) from exc
    except LastSignInMethodError as exc:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "last_method",
            "This is your only way to sign in. Link another account first.",
        ) from exc

    await db.commit()
    audit("auth.password.removed", user_id=user_session.user_id)
