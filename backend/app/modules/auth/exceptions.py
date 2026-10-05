class AccountExistsError(Exception):
    """Another account's user already owns this email."""


class OAuthProviderError(Exception):
    """The provider flow failed: a denied consent, a mismatched state, a
    rejected code exchange, an invalid ID token, an unreachable provider or
    missing claims."""


class UnsupportedOAuthProviderError(Exception):
    """No adapter is registered for this provider."""
