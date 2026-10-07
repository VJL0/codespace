from __future__ import annotations

from collections.abc import Iterable

from authlib.integrations.starlette_client import OAuth

from app.modules.auth.exceptions import UnsupportedOAuthProviderError
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import OAuthProviderAdapter
from app.modules.auth.providers.github import GitHubOAuthAdapter
from app.modules.auth.providers.google import GoogleOAuthAdapter
from app.modules.auth.providers.microsoft import MicrosoftOAuthAdapter


class OAuthProviderRegistry:
    def __init__(self, adapters: Iterable[OAuthProviderAdapter]) -> None:
        self._adapters = {adapter.provider: adapter for adapter in adapters}

    def get(self, provider: OAuthProvider) -> OAuthProviderAdapter:
        adapter = self._adapters.get(provider)

        if adapter is None:
            raise UnsupportedOAuthProviderError(provider)

        return adapter


def create_oauth_provider_registry() -> OAuthProviderRegistry:
    oauth = OAuth()

    return OAuthProviderRegistry(
        [
            GoogleOAuthAdapter(oauth),
            MicrosoftOAuthAdapter(oauth),
            GitHubOAuthAdapter(oauth),
        ]
    )
