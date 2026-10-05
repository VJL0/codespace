from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.modules.auth.models import OAuthProvider


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
    identities: list[IdentityRead]
    emails: list[EmailRead]
    # Linked providers that can confirm it's the user by making them enter
    # their credentials again.
    reauthentication_providers: list[OAuthProvider]
    recently_authenticated: bool
