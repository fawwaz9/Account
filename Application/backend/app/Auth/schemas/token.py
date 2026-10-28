"""Request and response bodies for issuing session tokens."""

from uuid import UUID

from pydantic import BaseModel


class GoogleAuthRequest(BaseModel):
    """Request body for signing in with Google.

    Attributes:
        id_token: The Google ID token (a JWT) from Google Identity Services.
    """
    id_token: str


class TokenResponse(BaseModel):
    """A session token, returned by every sign-in route.

    Attributes:
        access_token: Signed JWT to send as `Authorization: Bearer <token>`.
        token_type: Always "bearer".
    """
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """A session token's claims as a schema; nothing reads it (see `session_service`).

    Attributes:
        sub: The internal user id, not Google's.
        exp: Expiry time in Unix seconds.
    """
    sub: UUID  # our internal user_id, not Google's
    exp: int
