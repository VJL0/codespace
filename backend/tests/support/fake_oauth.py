"""An in-process stand-in for Google, Microsoft and GitHub.

The app's Authlib clients are pointed at it through an httpx2 MockTransport, so
a test runs the real OAuth flow (discovery, PKCE, token exchange, ID token
signature and claim checks, GitHub API calls) without leaving the process.
The token endpoint enforces what the real providers do: single-use codes, the
exact redirect URI, client authentication and the PKCE verifier.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
from joserfc import jwt
from joserfc.jwk import RSAKey

GOOGLE_ISSUER = "https://accounts.google.com"
MICROSOFT_PERSONAL_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
MICROSOFT_ORG_TENANT = "aaaabbbb-0000-cccc-1111-dddd2222eeee"

GOOGLE_DISCOVERY = {
    "issuer": GOOGLE_ISSUER,
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
    "id_token_signing_alg_values_supported": ["RS256"],
    "code_challenge_methods_supported": ["plain", "S256"],
    "authorization_response_iss_parameter_supported": True,
}

MICROSOFT_DISCOVERY = {
    "issuer": "https://login.microsoftonline.com/{tenantid}/v2.0",
    "authorization_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    "id_token_signing_alg_values_supported": ["RS256"],
}

# Key IDs the fake signs with. Like Microsoft's real JWKS, its keys carry an
# `issuer`: a templated one for work/school tenants, a fixed one for
# personal accounts.
GOOGLE_KEY = "google"
MICROSOFT_ORG_KEY = "microsoft-org"
MICROSOFT_PERSONAL_KEY = "microsoft-personal"
KEY_IDS = (GOOGLE_KEY, MICROSOFT_ORG_KEY, MICROSOFT_PERSONAL_KEY)


def generate_keys() -> dict[str, RSAKey]:
    return {
        kid: RSAKey.generate_key(2048, parameters={"kid": kid, "use": "sig"})
        for kid in KEY_IDS
    }


@dataclass
class _Grant:
    provider: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    nonce: str | None
    id_token_claims: dict[str, Any]
    signing_key: str
    github_user: dict[str, Any] | None
    github_emails: list[dict[str, Any]] | None


@dataclass
class FakeOAuthServer:
    keys: dict[str, RSAKey]
    credentials: dict[str, tuple[str, str]]
    """provider -> (client_id, client_secret) the app must authenticate with."""

    unavailable_hosts: set[str] = field(default_factory=set)
    """Hosts that answer 503, as a provider outage would."""

    requests: list[httpx2.Request] = field(default_factory=list)
    _codes: dict[str, _Grant] = field(default_factory=dict)
    _access_tokens: dict[str, _Grant] = field(default_factory=dict)

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def authorize(
        self,
        authorize_url: str,
        *,
        claims: dict[str, Any] | None = None,
        signing_key: str | None = None,
        iss: str | None = GOOGLE_ISSUER,
        github_user: dict[str, Any] | None = None,
        github_emails: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> str:
        """Approve the authorization request the app redirected to.

        Returns the callback URL the provider would send the browser to. `iss`
        is the RFC 9207 response parameter, which only Google sends.
        """

        url = urlsplit(authorize_url)
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        provider = {
            "accounts.google.com": "google",
            "login.microsoftonline.com": "microsoft",
            "github.com": "github",
        }[url.hostname or ""]

        response: dict[str, str] = {"state": params["state"]}

        if error is not None:
            response["error"] = error
        else:
            code = secrets.token_urlsafe(16)
            self._codes[code] = _Grant(
                provider=provider,
                client_id=params["client_id"],
                redirect_uri=params["redirect_uri"],
                code_challenge=params["code_challenge"],
                nonce=params.get("nonce"),
                id_token_claims=claims or {},
                signing_key=signing_key
                or {"google": GOOGLE_KEY, "microsoft": MICROSOFT_ORG_KEY}.get(
                    provider, ""
                ),
                github_user=github_user,
                github_emails=github_emails,
            )
            response["code"] = code

        if provider == "google" and iss is not None:
            response["iss"] = iss

        return f"{params['redirect_uri']}?{urlencode(response)}"

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)

        if request.url.host in self.unavailable_hosts:
            return httpx2.Response(503, text="Service Unavailable")

        route = (request.method, request.url.host, request.url.path)

        match route:
            case ("GET", "accounts.google.com", "/.well-known/openid-configuration"):
                return httpx2.Response(200, json=GOOGLE_DISCOVERY)
            case (
                "GET",
                "login.microsoftonline.com",
                "/common/v2.0/.well-known/openid-configuration",
            ):
                return httpx2.Response(200, json=MICROSOFT_DISCOVERY)
            case ("GET", "www.googleapis.com", "/oauth2/v3/certs"):
                return httpx2.Response(200, json=self._jwks(GOOGLE_KEY))
            case ("GET", "login.microsoftonline.com", "/common/discovery/v2.0/keys"):
                return httpx2.Response(
                    200, json=self._jwks(MICROSOFT_ORG_KEY, MICROSOFT_PERSONAL_KEY)
                )
            case (
                ("POST", "oauth2.googleapis.com", "/token")
                | ("POST", "login.microsoftonline.com", "/common/oauth2/v2.0/token")
                | ("POST", "github.com", "/login/oauth/access_token")
            ):
                return self._token(request)
            case ("GET", "api.github.com", "/user"):
                grant = self._bearer_grant(request)
                return (
                    httpx2.Response(200, json=grant.github_user)
                    if grant
                    else _unauthorized()
                )
            case ("GET", "api.github.com", "/user/emails"):
                grant = self._bearer_grant(request)
                return (
                    httpx2.Response(200, json=grant.github_emails)
                    if grant
                    else _unauthorized()
                )

        return httpx2.Response(404, json={"error": f"no fake route for {route}"})

    def _jwks(self, *kids: str) -> dict[str, Any]:
        keys = []

        for kid in kids:
            key = self.keys[kid].as_dict(private=False)

            if kid == MICROSOFT_ORG_KEY:
                key["issuer"] = "https://login.microsoftonline.com/{tenantid}/v2.0"
            elif kid == MICROSOFT_PERSONAL_KEY:
                key["issuer"] = (
                    f"https://login.microsoftonline.com/{MICROSOFT_PERSONAL_TENANT}/v2.0"
                )

            keys.append(key)

        return {"keys": keys}

    def _token(self, request: httpx2.Request) -> httpx2.Response:
        form = {
            key: values[0] for key, values in parse_qs(request.content.decode()).items()
        }
        grant = self._codes.pop(form.get("code", ""), None)

        if grant is None:
            return _invalid_grant("unknown or reused authorization code")

        client_id, client_secret = self.credentials[grant.provider]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        if request.headers.get("authorization") != f"Basic {basic}":
            return httpx2.Response(401, json={"error": "invalid_client"})

        if form.get("redirect_uri") != grant.redirect_uri:
            return _invalid_grant("redirect_uri mismatch")

        verifier = form.get("code_verifier", "")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )

        if challenge != grant.code_challenge:
            return _invalid_grant("PKCE verification failed")

        access_token = secrets.token_urlsafe(16)
        self._access_tokens[access_token] = grant
        body: dict[str, Any] = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        if grant.provider != "github":
            body["id_token"] = self._id_token(grant)

        return httpx2.Response(200, json=body)

    def _id_token(self, grant: _Grant) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "aud": grant.client_id,
            "iat": now,
            "exp": now + 3600,
            "nonce": grant.nonce,
            **grant.id_token_claims,
        }

        if "iss" not in claims:
            claims["iss"] = (
                GOOGLE_ISSUER
                if grant.provider == "google"
                else f"https://login.microsoftonline.com/{claims.get('tid')}/v2.0"
            )

        key = self.keys[grant.signing_key]
        header = {"alg": "RS256", "kid": grant.signing_key}

        return jwt.encode(header, claims, key)

    def _bearer_grant(self, request: httpx2.Request) -> _Grant | None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")

        return self._access_tokens.get(token) if scheme.lower() == "bearer" else None


def _invalid_grant(description: str) -> httpx2.Response:
    return httpx2.Response(
        400, json={"error": "invalid_grant", "error_description": description}
    )


def _unauthorized() -> httpx2.Response:
    return httpx2.Response(401, content=json.dumps({"message": "Bad credentials"}))
