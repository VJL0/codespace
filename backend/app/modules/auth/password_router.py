"""Email-and-password sign-up and sign-in, and the reauthentication a
password or an emailed link provides."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.api.deps import SessionDep
from app.api.errors import api_error
from app.modules.auth import emails
from app.modules.auth.audit import audit
from app.modules.auth.dependencies import (
    AuthSessionToken,
    CurrentSession,
    EmailSenderDep,
    EmailTokensDep,
    HttpClientDep,
    PasswordServiceDep,
    RateLimiterDep,
    SessionServiceDep,
)
from app.modules.auth.exceptions import AccountExistsError
from app.modules.auth.models import EmailTokenPurpose
from app.modules.auth.passwords import PasswordPolicyError, check_password_policy
from app.modules.auth.rate_limit import (
    RateLimitedError,
    RateLimiter,
    email_key,
    ip_key,
)
from app.modules.auth.schemas import (
    EmailRequest,
    LoginRequest,
    PasswordRequest,
    RegisterCompleteRequest,
    TokenRequest,
)
from app.modules.auth.session import finish_sign_in, set_session_cookie
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
