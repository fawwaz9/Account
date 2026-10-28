"""FastAPI dependencies that authenticate a request from its bearer token.

`CurrentUser` is the signed-in user; resolving it verifies the token, makes the
request's database session act as that user (`act_as`) and refuses revoked
sessions. Routes taking a `user_id` in the path use `VerifiedUserId` from
`access.py`, which builds on it.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app._database.dependencies import DBSession
from app._database.identity import act_as
from app.Auth.services.session_service import TokenClaims, decode_access_token, is_revoked
from app.Users.services import user_service

bearer_scheme = HTTPBearer(auto_error=True)
"""Reads `Authorization: Bearer <token>`, refusing requests that lack it."""


def get_token_claims(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> TokenClaims:
    """Verify the request's bearer token and return its claims.

    Args:
        credentials: The `Authorization: Bearer` credentials.

    Returns:
        The user id and session epoch the token carries.

    Raises:
        HTTPException: 401 "Session expired" or "Invalid session token" when the token
            does not verify.
    """
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


def get_current_user_id(
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
) -> UUID:
    """Return the user id from a verified token, without loading the user.

    Neither the session's acting user nor revocation is checked; use `CurrentUser` for
    anything that reads data.

    Args:
        claims: Claims of the already-verified bearer token.

    Returns:
        The token's user id.
    """
    return claims.user_id


def get_current_user(
    db: DBSession,
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
):
    """Return the signed-in user, after making the session act as them.

    Args:
        db: Request-scoped database session.
        claims: The verified token's claims.

    Returns:
        The user row.

    Raises:
        HTTPException: 401 when the user no longer exists, or the token's session epoch
            has been revoked.

    Note:
        `act_as` runs before the first query, so every query in the request runs as this
        user under row security.
    """
    # Before the first query of the request: under row-level security this is
    # the identity every query in it runs as, the user lookup just below
    # included. The token is already verified, so this is the caller.
    act_as(db, claims.user_id)
    user = user_service.get_user(db, claims.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Checked here rather than in get_current_user_id because this is where the
    # user row is already loaded -- every authenticated route reaches it through
    # CurrentUser or VerifiedUserId, so revocation costs no extra query.
    if is_revoked(claims.session_epoch, user.session_epoch):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked. Please sign in again.",
        )

    return user


CurrentUser = Annotated[object, Depends(get_current_user)]
"""Route parameter type for the signed-in `UserModel`; typed as `object`."""
