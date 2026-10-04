from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app._database.dependencies import DBSession
from app._database.identity import act_as
from app.Auth.services.session_service import TokenClaims, decode_access_token, is_revoked
from app.Users.services import user_service

bearer_scheme = HTTPBearer(auto_error=True)


def get_token_claims(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> TokenClaims:
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


def get_current_user_id(
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
) -> UUID:
    return claims.user_id


def get_current_user(
    db: DBSession,
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
):
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
