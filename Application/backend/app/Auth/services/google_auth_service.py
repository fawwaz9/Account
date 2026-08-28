from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.Users.schemas.user import UserCreate
from app.config import settings


def verify_google_token(token: str) -> UserCreate:
    try:
        payload = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise ValueError("Invalid Google token") from exc

    if not payload.get("email_verified", False):
        raise ValueError("Google email not verified")

    return UserCreate(
        name=payload["name"],
        email=payload["email"],
        google_id=payload["sub"],
    )