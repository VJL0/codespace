from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import OAuthProviderAdapter
from app.modules.auth.providers.github import GitHubOAuthAdapter
from app.modules.auth.providers.google import GoogleOAuthAdapter
from app.modules.auth.providers.microsoft import MicrosoftOAuthAdapter

OAuthProviders = dict[OAuthProvider, OAuthProviderAdapter]


def create_oauth_providers() -> OAuthProviders:
    oauth = OAuth()
    adapters = [
        GoogleOAuthAdapter(oauth),
        MicrosoftOAuthAdapter(oauth),
        GitHubOAuthAdapter(oauth),
    ]

    return {adapter.provider: adapter for adapter in adapters}
