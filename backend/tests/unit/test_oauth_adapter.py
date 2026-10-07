"""The checks every OAuth provider adapter gets without asking for them."""

from __future__ import annotations

from typing import Any

from authlib.integrations.starlette_client import OAuth

from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.base import OAuthIdentity, OAuthProviderAdapter


class MinimalAdapter(OAuthProviderAdapter):
    provider = OAuthProvider.GOOGLE

    def client_config(self) -> dict[str, Any]:
        return {"client_id": "client-id", "client_secret": "client-secret"}

    async def fetch_identity(self, token: dict[str, Any]) -> OAuthIdentity:
        raise NotImplementedError


def test_an_oidc_provider_checks_the_discovery_issuer_by_default() -> None:
    options = MinimalAdapter(OAuth()).id_token_claims_options(
        {"issuer": "https://idp.example"}
    )

    assert options == {"iss": {"essential": True, "values": ["https://idp.example"]}}


def test_a_provider_without_discovery_has_no_id_token_checks() -> None:
    assert MinimalAdapter(OAuth()).id_token_claims_options({}) == {}
