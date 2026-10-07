from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.modules.auth.models import OAuthProvider

EmailAddress = Annotated[str, StringConstraints(max_length=254)]
# Bounded here only against abuse; the policy's limit is checked after
# normalization.
Password = Annotated[str, StringConstraints(max_length=1024)]


class CurrentUserRead(BaseModel):
    name: str | None
    # The primary verified email; a user who signed in with a provider that
    # vouched for none has no email.
    email: str | None
    avatar_url: str | None


class AuthorizationRead(BaseModel):
    """Where to send the browser to continue at the provider."""

    authorization_url: str


class IdentityRead(BaseModel):
    provider: OAuthProvider
    email_snapshot: str | None
    created_at: datetime


class EmailRead(BaseModel):
    email: str
    is_primary: bool
    verified: bool


class SignInMethodsRead(BaseModel):
    has_password: bool
    identities: list[IdentityRead]
    emails: list[EmailRead]
    recently_authenticated: bool


class EmailRequest(BaseModel):
    email: EmailAddress


class LoginRequest(BaseModel):
    email: EmailAddress
    password: Password


class PasswordRequest(BaseModel):
    password: Password


class TokenRequest(BaseModel):
    token: str


class PasswordTokenRequest(BaseModel):
    """An emailed link's secret, with the password to set."""

    token: str
    password: Password


class RegisterCompleteRequest(BaseModel):
    token: str
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    password: Password


class ChangePasswordRequest(BaseModel):
    current_password: Password
    new_password: Password
