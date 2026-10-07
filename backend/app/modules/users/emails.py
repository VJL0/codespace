from email_validator import EmailNotValidError, validate_email

__all__ = ["EmailNotValidError", "normalize_email"]


def normalize_email(address: str) -> str:
    """The key for email lookups and uniqueness; raises EmailNotValidError.

    Lowercases the domain and normalizes Unicode. Keeps the local part's
    case, except role names like postmaster@. Strips whitespace, which
    the library rejects. Skips DNS: the emailed link proves the address.
    """

    return validate_email(address.strip(), check_deliverability=False).normalized
