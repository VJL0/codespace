class AccountExistsError(Exception):
    """Another user already owns this verified email."""


class OAuthProviderError(Exception):
    """The provider flow failed: a denied consent, a mismatched state, a
    rejected code exchange, an invalid ID token, an unreachable provider or
    missing claims."""


class UnsupportedOAuthProviderError(Exception):
    """No adapter is registered for this provider."""


class ReauthUnsupportedError(Exception):
    """The provider can't be made to ask for credentials again."""


class IdentityInUseError(Exception):
    """The provider account is already linked to another user."""


class ProviderAlreadyLinkedError(Exception):
    """The user already has an account with this provider."""


class OAuthAccountNotLinkedError(Exception):
    """The user has no account with this provider."""


class LastSignInMethodError(Exception):
    """Removing this would leave the user no way to sign in."""
