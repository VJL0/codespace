from email_validator import EmailNotValidError, validate_email

__all__ = ["EmailNotValidError", "normalize_email"]


def normalize_email(address: str) -> str:
    """The comparison key for an email address; raises EmailNotValidError.

    The one canonical form used for every lookup and uniqueness check. It
    applies Unicode and IDNA normalization and lowercases the domain, but
    keeps the local part's case, which only the receiving server may
    interpret, and applies no provider-specific rules such as Gmail's dots.
    """

    return validate_email(address.strip(), check_deliverability=False).normalized
