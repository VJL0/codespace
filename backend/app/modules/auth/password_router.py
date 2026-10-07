"""Email-and-password sign-up and sign-in, confirming it's the user with a
password or an emailed link, and managing the password itself: resetting,
adding, changing and removing it."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated

import httpx2
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import EmailSenderDep, HttpClientDep, SessionDep
from app.api.errors import api_error
from app.modules.auth import emails, service
from app.modules.auth.audit import audit
from app.modules.auth.dependencies import (
    CurrentSession,
    RecentlyAuthenticatedSession,
    SessionToken,
)
from app.modules.auth.models import EmailToken, EmailTokenPurpose
from app.modules.auth.passwords import check_password_policy
from app.modules.auth.rate_limit import email_key, ip_key, rate_limit
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
    renew_session,
    revoke_sessions,
    start_session,
)
from app.modules.auth.tokens import consume_email_token, issue_email_token
from app.modules.users.emails import EmailNotValidError, normalize_email
from app.modules.users.service import get_primary_email, get_verified_email

router = APIRouter()


class _Mailer:
    """Sends email after the response, so its timing doesn't reveal whether
    mail went out."""

    def __init__(
        self,
        db: SessionDep,
        email_sender: EmailSenderDep,
        background_tasks: BackgroundTasks,
    ) -> None:
        self._db = db
        self._email_sender = email_sender
        self._background_tasks = background_tasks

    def send(self, to: str, message: emails.Message, idempotency_key: str) -> None:
        self._background_tasks.add_task(
            self._email_sender.send,
            to=to,
            subject=message.subject,
            html=message.html,
            idempotency_key=idempotency_key,
        )

    async def send_link(
        self,
        purpose: EmailTokenPurpose,
        *,
        to: str,
        lifetime: timedelta,
        message: Callable[[str], emails.Message],
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> None:
        """Commit a single-use link for `purpose`, then email it to `to`."""

        token, secret = await issue_email_token(
            self._db,
            purpose,
            email=to,
            lifetime=lifetime,
            user_id=user_id,
            session_id=session_id,
        )
        await self._db.commit()

        self.send(to, message(secret), idempotency_key=f"{purpose}/{token.id}")


Mailer = Annotated[_Mailer, Depends()]


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


async def _use_link(
    db: AsyncSession,
    purpose: EmailTokenPurpose,
    secret: str,
    invalid_message: str,
    *,
    session_id: uuid.UUID | None = None,
) -> EmailToken:
    """Spend an emailed link's token, or refuse (400) one that's expired,
    used or someone else's."""

    token = await consume_email_token(db, purpose, secret, session_id=session_id)

    if token is None:
        raise api_error(status.HTTP_400_BAD_REQUEST, "invalid_token", invalid_message)

    # Spent now, whatever happens next: a link works once.
    await db.commit()

    return token


async def _use_password_link(
    db: AsyncSession,
    purpose: EmailTokenPurpose,
    body: PasswordTokenRequest,
    http_client: httpx2.AsyncClient,
) -> uuid.UUID:
    """Check the new password, then spend the link; return whose it is."""

    # The policy first, so a password it refuses doesn't spend the link.
    await check_password_policy(body.password, http_client)
    token = await _use_link(
        db,
        purpose,
        body.token,
        "This link has expired or was already used. Ask for a new one.",
    )
    assert token.user_id is not None  # reset and setup links are for an account

    return token.user_id


async def _confirm_password(
    db: AsyncSession, user_id: uuid.UUID, password: str, invalid_message: str
) -> None:
    """Refuse (401) a password that isn't the user's. Every such check for a
    user shares one rate limit, so no endpoint is a way around it."""

    await rate_limit(db, (f"reauth:user:{user_id}", 10, timedelta(minutes=15)))

    if not await service.password_matches(db, user_id, password):
        audit("auth.password.check_failed", user_id=user_id)
        raise api_error(
            status.HTTP_401_UNAUTHORIZED, "invalid_credentials", invalid_message
        )


# --- Signing up and in -------------------------------------------------------


@router.post("/register", status_code=202)
async def register(
    body: EmailRequest, request: Request, db: SessionDep, mailer: Mailer
) -> None:
    """Email-first sign-up: send a link that proves the address is theirs.
    No account, and no password, exists until it's opened.

    The response is the same whether or not the address has an account;
    only its owner learns which, from the email they get.
    """

    address = _valid_email(body.email)
    await rate_limit(
        db,
        (email_key("signup", address), 3, timedelta(hours=1)),
        (ip_key("signup", request), 20, timedelta(hours=1)),
    )

    if await get_verified_email(db, address):
        mailer.send(
            address,
            emails.account_exists(),
            idempotency_key=f"account-exists/{uuid.uuid7()}",
        )
    else:
        await mailer.send_link(
            EmailTokenPurpose.SIGNUP,
            to=address,
            lifetime=timedelta(hours=1),
            message=emails.signup,
        )

    audit("auth.signup.requested")


@router.post("/register/complete", status_code=204)
async def complete_registration(
    body: RegisterCompleteRequest,
    response: Response,
    db: SessionDep,
    http_client: HttpClientDep,
    session_token: SessionToken = None,
) -> None:
    # The policy first, so a password it refuses doesn't spend the link.
    await check_password_policy(body.password, http_client)
    token = await _use_link(
        db,
        EmailTokenPurpose.SIGNUP,
        body.token,
        "This link has expired or was already used. Sign up again.",
    )
    user = await service.create_password_account(
        db, address=token.email, name=body.name, password=body.password
    )

    # Fresh: they just proved both the email and the password.
    await start_session(
        db, response, user=user, fresh=True, previous_token=session_token
    )
    audit("auth.signup.completed", user_id=user.id)


@router.post("/login", status_code=204)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: SessionDep,
    session_token: SessionToken = None,
) -> None:
    await rate_limit(
        db,
        (email_key("login", body.email), 10, timedelta(minutes=15)),
        (ip_key("login", request), 50, timedelta(minutes=15)),
    )

    user = await service.authenticate(db, body.email, body.password)

    if user is None:
        audit("auth.login.failed", method="password", reason="invalid_credentials")
        # One answer for an unknown email, an account without a password and
        # a wrong password alike.
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Incorrect email or password.",
        )

    await start_session(
        db, response, user=user, fresh=True, previous_token=session_token
    )
    audit("auth.login.succeeded", user_id=user.id, method="password")


# --- Confirming it's the user --------------------------------------------------


@router.post("/reauthenticate", status_code=204)
async def reauthenticate_with_password(
    body: PasswordRequest,
    response: Response,
    current_session: CurrentSession,
    db: SessionDep,
) -> None:
    user_id = current_session.user_id
    await _confirm_password(db, user_id, body.password, "Incorrect password.")
    await renew_session(db, response, current_session)
    audit("auth.reauthenticated", user_id=user_id, method="password")


@router.post("/reauthenticate/email", status_code=202)
async def send_reauthentication_email(
    current_session: CurrentSession, db: SessionDep, mailer: Mailer
) -> None:
    """Email a link that confirms it's the user, usable only by this
    session: whoever opens it elsewhere can't reauthenticate theirs."""

    user_id = current_session.user_id
    primary = await get_primary_email(db, user_id)

    if primary is None:
        raise api_error(
            status.HTTP_409_CONFLICT, "no_email", "You have no email address to use."
        )

    await rate_limit(db, (f"reauth-email:user:{user_id}", 5, timedelta(hours=1)))
    await mailer.send_link(
        EmailTokenPurpose.REAUTHENTICATION,
        to=primary.email,
        lifetime=timedelta(minutes=15),
        message=emails.reauthentication,
        user_id=user_id,
        session_id=current_session.id,
    )


@router.post("/reauthenticate/email/complete", status_code=204)
async def complete_email_reauthentication(
    body: TokenRequest,
    response: Response,
    current_session: CurrentSession,
    db: SessionDep,
) -> None:
    await _use_link(
        db,
        EmailTokenPurpose.REAUTHENTICATION,
        body.token,
        "This link has expired, was already used, or is for another browser.",
        session_id=current_session.id,
    )
    await renew_session(db, response, current_session)
    audit("auth.reauthenticated", user_id=current_session.user_id, method="email")


# --- Managing the password ------------------------------------------------------


@router.post("/password/forgot", status_code=202)
async def forgot_password(
    body: EmailRequest, request: Request, db: SessionDep, mailer: Mailer
) -> None:
    """Email a reset link to a verified address whose account has a password.

    The response is the same either way, so this doesn't reveal accounts.
    """

    address = _valid_email(body.email)
    await rate_limit(
        db,
        (email_key("reset", address), 3, timedelta(hours=1)),
        (ip_key("reset", request), 20, timedelta(hours=1)),
    )
    audit("auth.password.reset_requested")

    email = await get_verified_email(db, address)

    if email is None or not await service.has_password(db, email.user_id):
        return

    await mailer.send_link(
        EmailTokenPurpose.PASSWORD_RESET,
        to=email.email,
        lifetime=timedelta(minutes=30),
        message=emails.password_reset,
        user_id=email.user_id,
    )


@router.post("/password/reset", status_code=204)
async def reset_password(
    body: PasswordTokenRequest,
    response: Response,
    db: SessionDep,
    http_client: HttpClientDep,
) -> None:
    """Replace the password and sign out every session: whoever knew the old
    password is out. No automatic sign-in; the user signs in with the new
    one."""

    user_id = await _use_password_link(
        db, EmailTokenPurpose.PASSWORD_RESET, body, http_client
    )
    await service.set_password(db, user_id, body.password)
    await revoke_sessions(db, user_id)
    await db.commit()

    delete_session_cookie(response)
    audit("auth.password.reset", user_id=user_id)


@router.post("/password/setup", status_code=202)
async def start_password_setup(
    user_session: RecentlyAuthenticatedSession, db: SessionDep, mailer: Mailer
) -> None:
    """Add a password to an account that signs in with providers only, by a
    link to its primary email: the password and the email go together, as
    the email is what signing in with it and resetting it use."""

    user_id = user_session.user_id
    await service.ensure_no_password(db, user_id)
    primary = await get_primary_email(db, user_id)

    if primary is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "no_email",
            "A password needs an email address to sign in with.",
        )

    await rate_limit(db, (f"password-setup:user:{user_id}", 5, timedelta(hours=1)))
    await mailer.send_link(
        EmailTokenPurpose.PASSWORD_SETUP,
        to=primary.email,
        lifetime=timedelta(minutes=30),
        message=emails.password_setup,
        user_id=user_id,
    )


@router.post("/password/setup/complete", status_code=204)
async def complete_password_setup(
    body: PasswordTokenRequest, db: SessionDep, http_client: HttpClientDep
) -> None:
    user_id = await _use_password_link(
        db, EmailTokenPurpose.PASSWORD_SETUP, body, http_client
    )
    await service.ensure_no_password(db, user_id)
    await service.set_password(db, user_id, body.password)
    await db.commit()
    audit("auth.password.added", user_id=user_id)


@router.post("/password/change", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    current_session: CurrentSession,
    db: SessionDep,
    http_client: HttpClientDep,
) -> None:
    """Change the password, given the current one; every other session is
    signed out, and this one renewed."""

    user_id = current_session.user_id
    await _confirm_password(
        db, user_id, body.current_password, "Your current password is incorrect."
    )
    await check_password_policy(body.new_password, http_client)
    await service.set_password(db, user_id, body.new_password)
    await revoke_sessions(db, user_id, keep=current_session.id)
    # Knowing the current password was a fresh authentication.
    await renew_session(db, response, current_session)
    audit("auth.password.changed", user_id=user_id)


@router.delete("/password", status_code=204)
async def remove_password(
    user_session: RecentlyAuthenticatedSession, db: SessionDep
) -> None:
    await service.remove_password(db, user_session.user_id)
    await db.commit()
    audit("auth.password.removed", user_id=user_session.user_id)
