from __future__ import annotations

import uuid
from typing import Any

from app.core.config import settings
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import (
    OAuthIdentity,
    OAuthProviderAdapter,
    OAuthProviderError,
)


def _is_guid(value: Any) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except TypeError, ValueError:
        return False


class MicrosoftOAuthAdapter(OAuthProviderAdapter):
    provider = OAuthProvider.MICROSOFT

    def client_config(self) -> dict[str, Any]:
        return {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "server_metadata_url": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            "client_kwargs": {
                "scope": "openid email profile",
                "code_challenge_method": "S256",
            },
        }

    def id_token_claims_options(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"iss": {"essential": True, "validate": self._issuer_is_trusted}}

    def _issuer_is_trusted(self, claims: Any, issuer: str) -> bool:
        """Multitenant issuer validation, as Microsoft specifies it.

        /common publishes the issuer "https://login.microsoftonline.com/{tenantid}/v2.0",
        so `iss` must equal it with the token's own `tid` substituted, and so must
        the `issuer` of the JWKS key that signed the token.
        """

        tenant_id = claims.get("tid")

        if not _is_guid(tenant_id):
            return False

        jwks = self.client.server_metadata.get("jwks", {})
        signing_key = next(
            (
                key
                for key in jwks.get("keys", [])
                if key.get("kid") == claims.header.get("kid")
            ),
            None,
        )

        if signing_key is None:
            return False

        expected = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        key_issuer = signing_key.get("issuer", "").replace("{tenantid}", tenant_id)

        return issuer == expected and key_issuer == expected

    async def fetch_identity(self, token: dict[str, Any]) -> OAuthIdentity:
        claims = token.get("userinfo")

        if claims is None:
            raise OAuthProviderError("Microsoft returned no ID token.")

        object_id = claims.get("oid")

        if object_id is None:
            raise OAuthProviderError("Microsoft returned no `oid` claim.")

        # Microsoft requires `tid` in the key for a user's data, so this is
        # MSAL's home account ID, "<oid>.<tid>". `oid` rather than `sub`: `sub`
        # is pairwise per app registration, `oid` is shared across them.
        return OAuthIdentity(
            provider=self.provider,
            provider_user_id=f"{object_id}.{claims['tid']}",
            email=claims.get("email"),
            # Microsoft has no `email_verified`; `xms_edov` is its equivalent,
            # an optional claim the app registration must request.
            email_verified=claims.get("xms_edov", False),
            full_name=claims.get("name"),
        )
