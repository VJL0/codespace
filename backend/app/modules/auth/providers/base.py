from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx2
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from joserfc.errors import JoseError
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.modules.auth.exceptions import OAuthProviderError
from app.modules.auth.models import OAuthProvider
from app.modules.users.emails import EmailNotValidError, normalize_email


class OAuthIdentity(BaseModel):
    provider: OAuthProvider
    provider_user_id: str = Field(min_length=1)
    # Optional: sign-in rests on provider_user_id alone, and a provider may
    # send no email (Microsoft often doesn't) or an unverified one.
    email: str | None = None
    email_verified: bool = False
    full_name: str | None = None
    avatar_url: str | None = None

    @field_validator("email")
    @classmethod
    def drop_invalid_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        try:
            normalize_email(value)
        except EmailNotValidError:
            return None

        return value.strip()

    @property
    def verified_email(self) -> str | None:
        """The email, if the provider vouches that this account owns it."""

        return self.email if self.email_verified else None


class OAuthProviderAdapter(ABC):
    provider: ClassVar[OAuthProvider]

    def __init__(self, oauth: OAuth) -> None:
        self.client: StarletteOAuth2App = oauth.register(
            name=self.provider.value, **self.client_config()
        )

    @abstractmethod
    def client_config(self) -> dict[str, Any]: ...

    @abstractmethod
    async def fetch_identity(self, token: dict[str, Any]) -> OAuthIdentity: ...

    def id_token_claims_options(self) -> dict[str, Any]:
        """ID token claim checks beyond the `aud` check every provider gets.

        These replace Authlib's defaults, so an OIDC provider must check `iss`
        here. Authlib pops `validate` hooks out of the options, so build a
        fresh dict on every call.
        """

        return {}

    def _audience_is_this_client(self, claims: Any, audience: str | list[str]) -> bool:
        # Authlib only checks `aud` when asked to. OIDC Core 3.1.3.7: it must
        # list this client, and no other audience this client doesn't trust.
        return audience in (self.client.client_id, [self.client.client_id])

    async def start_authorization(
        self, request: Request, redirect_uri: str
    ) -> RedirectResponse:
        try:
            # Always show the account picker: signing out here doesn't end the
            # provider session, so this is how a user switches accounts.
            return await self.client.authorize_redirect(
                request, redirect_uri, prompt="select_account"
            )
        except (AuthlibBaseError, httpx2.HTTPError) as exc:
            raise OAuthProviderError(repr(exc)) from exc

    async def _verify_response_issuer(self, request: Request) -> None:
        """RFC 9207 mix-up defense for providers that advertise the `iss`
        authorization response parameter."""

        metadata = await self.client.load_server_metadata()

        if not metadata.get("authorization_response_iss_parameter_supported"):
            return

        if request.query_params.get("iss") != metadata["issuer"]:
            raise OAuthProviderError("Authorization response issuer mismatch.")

    async def resolve_identity(self, request: Request) -> OAuthIdentity:
        try:
            await self._verify_response_issuer(request)
            token = await self.client.authorize_access_token(
                request,
                claims_options={
                    **self.id_token_claims_options(),
                    "aud": {
                        "essential": True,
                        "validate": self._audience_is_this_client,
                    },
                },
            )
            return await self.fetch_identity(token)
        except (AuthlibBaseError, JoseError, httpx2.HTTPError, ValidationError) as exc:
            raise OAuthProviderError(repr(exc)) from exc
