"""Session tokens: minting and verifying the HS256 JWTs signed-in requests carry.

Each token carries the user id, its expiry and the account's session epoch when it
was minted; bumping `users.session_epoch` revokes every token minted before.
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

import jwt

from app.config import JWT_ALGORITHM, settings

#: Claim carrying the session epoch the token was minted under. Tokens issued
#: before this claim existed have no value for it, and are read as epoch 0 --
#: which is every existing account's starting epoch, so they stay valid until
#: something actually revokes them.
EPOCH_CLAIM = "sev"

#: One wording for every way a token can fail to parse, so a caller cannot tell
#: a malformed token from a forged one.
INVALID_TOKEN = "Invalid session token"


class TokenClaims(NamedTuple):
    """What a verified session token asserts.

    Attributes:
        user_id: The signed-in user.
        session_epoch: The account's session epoch when the token was minted.
    """

    user_id: UUID
    session_epoch: int


def create_access_token(user_id: UUID, session_epoch: int = 0) -> str:
    """Mint a signed session token for a user.

    Args:
        user_id: The user the token signs in.
        session_epoch: The account's current `session_epoch`.

    Returns:
        An HS256 JWT with `sub`, `iat`, `exp` (now plus `JWT_EXPIRE_MINUTES`) and the
        epoch claim.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        EPOCH_CLAIM: session_epoch,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims:
    """Verify a session token and return its claims.

    Args:
        token: The bearer token.

    Returns:
        The user id and session epoch it carries; a token without the epoch claim
        reads as epoch 0.

    Raises:
        ValueError: "Session expired" for an expired token; `INVALID_TOKEN` for any
            other failure: a bad signature, another algorithm, a missing `sub` or `exp`,
            or a malformed id or epoch.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            # Required, not optional: a token missing `sub` used to raise KeyError
            # below and surface as a 500 rather than a 401, and `exp` being absent
            # meant a token that never expired verified happily. `iat` is not
            # required, so tokens minted before it was added keep working.
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError(INVALID_TOKEN) from exc

    try:
        user_id = UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(INVALID_TOKEN) from exc

    epoch = payload.get(EPOCH_CLAIM, 0)
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        raise ValueError(INVALID_TOKEN)

    return TokenClaims(user_id=user_id, session_epoch=epoch)


def is_revoked(token_epoch: int, user_epoch: int | None) -> bool:
    """Return whether a token's epoch differs from the account's current one.

    Args:
        token_epoch: The epoch the token was minted under.
        user_epoch: The account's `session_epoch`; None reads as 0.

    Returns:
        True when they differ in either direction, which means the token is refused.
    """
    return token_epoch != (user_epoch or 0)
