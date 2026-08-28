from uuid import UUID

from pydantic import BaseModel


class GoogleAuthRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: UUID  # our internal user_id, not Google's
    exp: int