"""Password hashing for the local (email + password) auth provider.

bcrypt is used directly rather than through passlib: passlib's bcrypt
backend is broken against bcrypt 4.x/5.x, and the surface needed here is
two functions.
"""

from functools import lru_cache

import bcrypt

# bcrypt refuses passwords longer than this outright rather than silently
# truncating them, so an over-long password would surface as a 500 unless it
# is rejected earlier. The schema layer enforces the same limit; this is the
# last line of defence.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed stored hash, or a password past the byte limit.
        return False


@lru_cache(maxsize=1)
def _placeholder_hash() -> str:
    return hash_password("timing-equalisation-placeholder")


def burn_one_verification() -> None:
    """Spend roughly one bcrypt verification's worth of time.

    Login calls this when no account matches so that an unregistered email
    and a wrong password take comparable time, and the endpoint does not
    leak which addresses have accounts through response timing.
    """
    bcrypt.checkpw(b"timing-equalisation-placeholder", _placeholder_hash().encode("utf-8"))
