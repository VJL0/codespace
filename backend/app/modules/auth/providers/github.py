from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import (
    OAuthIdentity,
    OAuthProviderAdapter,
    OAuthProviderError,
)

GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
}


class GitHubOAuthAdapter(OAuthProviderAdapter):
    """GitHub is plain OAuth 2.0 (no ID token), so the profile comes from the API."""

    provider = OAuthProvider.GITHUB

    def client_config(self) -> dict[str, Any]:
        return {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "authorize_url": "https://github.com/login/oauth/authorize",
            "access_token_url": "https://github.com/login/oauth/access_token",
            "api_base_url": "https://api.github.com/",
            "client_kwargs": {
                "scope": "read:user user:email",
                "code_challenge_method": "S256",
            },
        }

    async def fetch_identity(self, token: dict[str, Any]) -> OAuthIdentity:
        user_response = await self.client.get(
            "user", token=token, headers=GITHUB_API_HEADERS
        )
        user_response.raise_for_status()
        profile = user_response.json()

        # /user only shows the public email; /user/emails says which is
        # primary and whether GitHub verified it.
        emails_response = await self.client.get(
            "user/emails",
            token=token,
            headers=GITHUB_API_HEADERS,
            params={"per_page": 100},
        )
        emails_response.raise_for_status()
        primary_email = next(
            (entry for entry in emails_response.json() if entry.get("primary")),
            {},
        )

        # The numeric `id` is durable; `login` can be renamed and reassigned.
        github_user_id = profile.get("id")

        if github_user_id is None:
            raise OAuthProviderError("GitHub returned no user ID.")

        return OAuthIdentity(
            provider=self.provider,
            provider_user_id=str(github_user_id),
            email=primary_email.get("email"),
            email_verified=primary_email.get("verified", False),
            full_name=profile.get("name"),
            avatar_url=profile.get("avatar_url"),
        )
