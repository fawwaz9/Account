"""Verifying a Google ID token and reading the account details it vouches for."""

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.Users.schemas.user import UserCreate
from app.config import settings


class GoogleUnavailable(RuntimeError):
    """Raised when Google cannot be reached to check a token; not the caller's fault.

    Deliberately not a ValueError, so routes report it as unavailable rather than as a
    rejected sign-in.
    """


def verify_google_token(token: str) -> UserCreate:
    """Verify a Google ID token and return the account details it vouches for.

    Checks the signature, expiry and audience (`GOOGLE_CLIENT_ID`) with Google's
    signing keys, and requires a verified email.

    Args:
        token: The ID token from Google Identity Services.

    Returns:
        A `UserCreate` with the email, Google subject id, and the profile name (or the
        email's local part when the token carries no name).

    Raises:
        ValueError: If the token is invalid, the email is unverified, or the email or
            subject is missing.
        GoogleUnavailable: If Google's signing keys could not be fetched.
    """
    try:
        payload = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise ValueError("Invalid Google token") from exc
    except GoogleAuthError as exc:
        # Fetching Google's signing keys is a network call, and a transport
        # failure there arrives as GoogleAuthError rather than ValueError -- so
        # it used to escape this function entirely and surface as a 500.
        raise GoogleUnavailable("Could not reach Google to verify the sign-in") from exc

    if not payload.get("email_verified", False):
        raise ValueError("Google email not verified")

    email = payload.get("email")
    subject = payload.get("sub")
    if not email or not subject:
        raise ValueError("Google token is missing an email address")

    # `name` rides on the profile scope and is simply absent without it, so
    # indexing for it turned a legitimate sign-in into a 500. The address is
    # the one thing a verified token is guaranteed to carry.
    name = payload.get("name") or email.split("@")[0]

    return UserCreate(name=name, email=email, google_id=subject)
