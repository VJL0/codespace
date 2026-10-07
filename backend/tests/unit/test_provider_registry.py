"""The OAuth provider registry: which adapter handles which provider."""

from __future__ import annotations

import pytest

from app.modules.auth.exceptions import UnsupportedOAuthProviderError
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.registry import (
    OAuthProviderRegistry,
    create_oauth_provider_registry,
)


@pytest.mark.parametrize("provider", list(OAuthProvider))
def test_every_provider_has_an_adapter(provider: OAuthProvider) -> None:
    # A provider added to the enum (and so to the login route) needs an adapter.
    adapter = create_oauth_provider_registry().get(provider)

    assert adapter.provider is provider
    assert adapter.client.name == provider.value


def test_missing_adapter_is_reported() -> None:
    with pytest.raises(UnsupportedOAuthProviderError):
        OAuthProviderRegistry([]).get(OAuthProvider.GOOGLE)
