from __future__ import annotations

import enum
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import httpx2
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from joserfc.errors import JoseError
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.modules.auth.exceptions import OAuthProviderError, ReauthUnsupportedError
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
    # When the person last entered credentials at the provider (OIDC
    # `auth_time`), if it says.
    auth_time: datetime | None = None

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


class OAuthPurpose(enum.StrEnum):
    LOGIN = "login"
    LINK = "link"
    REAUTHENTICATE = "reauthenticate"


@dataclass(frozen=True)
class OAuthTransaction:
    """What a browser's provider flow was started for.

    Kept by Authlib with the flow's state, in the signed OAuth cookie, so
    it's bound to that browser and that flow, and gone once the callback
    consumes it.
    """

    purpose: OAuthPurpose
    # The signed-in user who started a link or reauthentication.
    user_id: uuid.UUID | None
    started_at: datetime


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

    def forced_reauth_params(self) -> dict[str, str] | None:
        """Authorization parameters that make the provider ask for the
        person's credentials even with a live provider session, and report
        when they did in `auth_time`; None if the provider can't."""

        return None

    def is_fresh(self, identity: OAuthIdentity, transaction: OAuthTransaction) -> bool:
        """Whether the person entered credentials at the provider during
        this flow, as opposed to the provider's SSO answering for them.

        `auth_time` is checked, not just requested: someone at an unattended
        browser could strip the forcing parameter from the URL.
        """

        if self.forced_reauth_params() is None or identity.auth_time is None:
            return False

        # auth_time has one-second precision, and the provider's clock and
        # ours differ a little.
        return identity.auth_time >= transaction.started_at - timedelta(minutes=1)

    def _audience_is_this_client(self, claims: Any, audience: str | list[str]) -> bool:
        # Authlib only checks `aud` when asked to. OIDC Core 3.1.3.7: it must
        # list this client, and no other audience this client doesn't trust.
        return audience in (self.client.client_id, [self.client.client_id])

    async def authorization_url(
        self,
        request: Request,
        redirect_uri: str,
        *,
        purpose: OAuthPurpose = OAuthPurpose.LOGIN,
        user_id: uuid.UUID | None = None,
    ) -> str:
        """Start a flow for `purpose`; return the provider URL to send the
        browser to. The flow's state and transaction go in the OAuth cookie."""

        # Always show the account picker: signing out here doesn't end the
        # provider session, so this is how a user switches accounts.
        params = {"prompt": "select_account"}

        if purpose is OAuthPurpose.REAUTHENTICATE:
            forced = self.forced_reauth_params()

            if forced is None:
                raise ReauthUnsupportedError(self.provider)

            params |= forced

        try:
            authorization = await self.client.create_authorization_url(
                redirect_uri, **params
            )
            # Authlib keeps the extra keys alongside state, PKCE verifier and
            # nonce, and ignores them when it exchanges the code.
            await self.client.save_authorize_data(
                request,
                redirect_uri=redirect_uri,
                purpose=purpose.value,
                user_id=str(user_id) if user_id else None,
                started_at=time.time(),
                **authorization,
            )
        except (AuthlibBaseError, httpx2.HTTPError) as exc:
            raise OAuthProviderError(repr(exc)) from exc

        return authorization["url"]

    async def start_authorization(
        self, request: Request, redirect_uri: str
    ) -> RedirectResponse:
        return RedirectResponse(
            await self.authorization_url(request, redirect_uri), status_code=302
        )

    async def get_transaction(self, request: Request) -> OAuthTransaction | None:
        """The transaction of the flow this callback answers, or None when
        this browser started no such flow. Read it before resolve_identity(),
        which consumes it."""

        state = request.query_params.get("state")
        data = state and await self.client.framework.get_state_data(
            request.session, state
        )

        if not data:
            return None

        user_id = data.get("user_id")

        return OAuthTransaction(
            purpose=OAuthPurpose(data.get("purpose", OAuthPurpose.LOGIN)),
            user_id=uuid.UUID(user_id) if user_id else None,
            started_at=datetime.fromtimestamp(data.get("started_at", 0), UTC),
        )

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
