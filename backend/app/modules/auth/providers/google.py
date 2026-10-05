from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.modules.auth.exceptions import OAuthProviderError
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import OAuthIdentity, OAuthProviderAdapter


class GoogleOAuthAdapter(OAuthProviderAdapter):
    provider = OAuthProvider.GOOGLE

    def client_config(self) -> dict[str, Any]:
        return {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
            "client_kwargs": {
                "scope": "openid email profile",
                "code_challenge_method": "S256",
            },
        }

    def id_token_claims_options(self) -> dict[str, Any]:
        # Google documents both forms; Authlib's default allows only the first.
        return {
            "iss": {
                "essential": True,
                "values": ["https://accounts.google.com", "accounts.google.com"],
            },
        }

    def forced_reauth_params(self) -> dict[str, str]:
        # Google has no prompt=login; max_age=0 makes it reauthenticate, and
        # OIDC then requires `auth_time` in the ID token.
        return {"max_age": "0"}

    async def fetch_identity(self, token: dict[str, Any]) -> OAuthIdentity:
        claims = token.get("userinfo")

        if claims is None:
            raise OAuthProviderError("Google returned no ID token.")

        return OAuthIdentity(
            provider=self.provider,
            provider_user_id=claims.get("sub"),
            email=claims.get("email"),
            email_verified=claims.get("email_verified", False),
            full_name=claims.get("name"),
            auth_time=claims.get("auth_time"),
            avatar_url=claims.get("picture"),
        )
