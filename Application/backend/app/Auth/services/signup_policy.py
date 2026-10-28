"""Who may create an account: the `ALLOWED_SIGNUP_EMAILS` allowlist.

It gates creating an account, through both the password and the Google routes, and
never signing in, so removing an address takes nobody's data away. Unset means open,
so a fresh clone can create its first account; `warn_if_open` logs that at startup.
"""
import logging
import os

logger = logging.getLogger("app.signup")


def allowed_emails() -> set[str]:
    """Return the addresses allowed to create an account, lower-cased.

    Read from `ALLOWED_SIGNUP_EMAILS` on every call, comma-separated with each entry
    stripped.

    Returns:
        The allowed addresses; empty means anyone may sign up.
    """
    raw = os.getenv("ALLOWED_SIGNUP_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def may_sign_up(email: str) -> bool:
    """Return whether an email address may create an account.

    Args:
        email: The address signing up; compared stripped and lower-cased.

    Returns:
        True when the allowlist is empty or contains the address.
    """
    allowed = allowed_emails()
    if not allowed:
        return True
    return (email or "").strip().lower() in allowed


def warn_if_open() -> None:
    """Log a warning at startup when the allowlist is unset, so anyone can sign up."""
    if not allowed_emails():
        logger.warning(
            "ALLOWED_SIGNUP_EMAILS is not set: anyone who can reach this server "
            "can create an account. Set it to the invited addresses."
        )
