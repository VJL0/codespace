from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, ClassVar, final

import httpx2
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from joserfc.errors import JoseError
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.requests import Request

from app.modules.auth.models import OAuthProvider
from app.modules.users.emails import EmailNotValidError, normalize_email


class OAuthProviderError(Exception):
    """The provider flow failed: a denied consent, a mismatched state, a
    rejected code exchange, an invalid ID token, an unreachable provider or
    missing claims."""


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
    """One provider's OAuth flow. The flow and its checks are final; a provider
    supplies its client config, its identity and any ID token claim checks."""

    provider: ClassVar[OAuthProvider]

    def __init__(self, oauth: OAuth) -> None:
        self.client: StarletteOAuth2App = oauth.register(
            name=self.provider.value, **self.client_config()
        )

    @abstractmethod
    def client_config(self) -> dict[str, Any]: ...

    @abstractmethod
    async def fetch_identity(self, token: dict[str, Any]) -> OAuthIdentity: ...

    def id_token_claims_options(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """ID token claim checks beyond the `aud` check every provider gets.

        These replace Authlib's defaults, so this keeps its `iss` check against
        the discovery document's issuer, and makes it essential. Override it
        for a provider whose tokens carry another issuer. Authlib pops
        `validate` hooks out of the options, so build a fresh dict on every
        call.
        """

        # Plain OAuth 2.0 (GitHub) has no discovery document and no ID token.
        if "issuer" not in metadata:
            return {}

        return {"iss": {"essential": True, "values": [metadata["issuer"]]}}

    @final
    def _audience_is_this_client(self, claims: Any, audience: str | list[str]) -> bool:
        """Authlib `aud` validator. Authlib only checks `aud` when asked to;
        OIDC Core 3.1.3.7 requires it to list this client, and no other
        audience this client doesn't trust."""

        return audience in (self.client.client_id, [self.client.client_id])

    @final
    async def authorization_url(
        self,
        request: Request,
        redirect_uri: str,
        *,
        link_user_id: uuid.UUID | None = None,
    ) -> str:
        """Start a sign-in, or linking for `link_user_id`; return the provider
        URL to send the browser to. The flow's state goes in the OAuth cookie."""

        try:
            # Always show the account picker: signing out here doesn't end the
            # provider session, so this is how a user switches accounts.
            authorization = await self.client.create_authorization_url(
                redirect_uri, prompt="select_account"
            )
            # Authlib keeps the extra key alongside state, PKCE verifier and
            # nonce, and ignores it when it exchanges the code.
            await self.client.save_authorize_data(
                request,
                redirect_uri=redirect_uri,
                link_user_id=str(link_user_id) if link_user_id else None,
                **authorization,
            )
        except (AuthlibBaseError, httpx2.HTTPError) as exc:
            raise OAuthProviderError(repr(exc)) from exc

        return authorization["url"]

    @final
    async def link_user_id(self, request: Request) -> uuid.UUID | None:
        """The user this callback's flow links an account to; None for a
        sign-in, or when this browser started no such flow. Read it before
        resolve_identity(), which consumes the flow's state."""

        state = request.query_params.get("state")
        data = state and await self.client.framework.get_state_data(
            request.session, state
        )
        user_id = data.get("link_user_id") if data else None

        return uuid.UUID(user_id) if user_id else None

    @final
    def _verify_response_issuer(
        self, request: Request, metadata: dict[str, Any]
    ) -> None:
        """RFC 9207 mix-up defense for providers that advertise the `iss`
        authorization response parameter."""

        if not metadata.get("authorization_response_iss_parameter_supported"):
            return

        if request.query_params.get("iss") != metadata["issuer"]:
            raise OAuthProviderError("Authorization response issuer mismatch.")

    @final
    async def resolve_identity(self, request: Request) -> OAuthIdentity:
        try:
            metadata = await self.client.load_server_metadata()
            self._verify_response_issuer(request, metadata)
            token = await self.client.authorize_access_token(
                request,
                claims_options={
                    **self.id_token_claims_options(metadata),
                    "aud": {
                        "essential": True,
                        "validate": self._audience_is_this_client,
                    },
                },
            )
            return await self.fetch_identity(token)
        except (AuthlibBaseError, JoseError, httpx2.HTTPError, ValidationError) as exc:
            raise OAuthProviderError(repr(exc)) from exc
