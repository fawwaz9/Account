"""Password hashing and checking for email-and-password accounts, using bcrypt."""

from functools import lru_cache

import bcrypt

# bcrypt refuses passwords longer than this outright rather than silently
# truncating them, so an over-long password would surface as a 500 unless it
# is rejected earlier. The schema layer enforces the same limit; this is the
# last line of defence.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Return a bcrypt hash of a password, with a fresh salt.

    Args:
        password: The password; at most `MAX_PASSWORD_BYTES` bytes in UTF-8.

    Returns:
        The hash as text, for `users.password_hash`.

    Raises:
        ValueError: If the password exceeds `MAX_PASSWORD_BYTES` bytes, which bcrypt
            refuses.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a password matches a stored bcrypt hash.

    Args:
        password: The password as typed.
        password_hash: The stored hash.

    Returns:
        True on a match; False on a mismatch, a malformed hash or an over-long
        password.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed stored hash, or a password past the byte limit.
        return False


@lru_cache(maxsize=1)
def _placeholder_hash() -> str:
    """Return a hash of a fixed placeholder, computed once, for timing equalisation."""
    return hash_password("timing-equalisation-placeholder")


def burn_one_verification() -> None:
    """Spend about one bcrypt verification's time, as a real check would.

    Note:
        Login calls this when no account matches, so response timing does not reveal
        which addresses have accounts.
    """
    bcrypt.checkpw(b"timing-equalisation-placeholder", _placeholder_hash().encode("utf-8"))
