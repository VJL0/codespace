from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import (
    OAuthIdentity,
    OAuthProviderAdapter,
    OAuthProviderError,
)


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

    def id_token_claims_options(self, metadata: dict[str, Any]) -> dict[str, Any]:
        # Google documents both forms; its discovery document lists only the first.
        return {
            "iss": {
                "essential": True,
                "values": ["https://accounts.google.com", "accounts.google.com"],
            },
        }

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
            avatar_url=claims.get("picture"),
        )
