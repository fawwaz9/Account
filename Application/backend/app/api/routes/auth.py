from fastapi import APIRouter, HTTPException, status

from app._database.dependencies import DBSession
from app.Auth.dependencies import CurrentUser
from app.Auth.schemas.credentials import LoginRequest, RegisterRequest, SetPasswordRequest
from app.Auth.schemas.token import GoogleAuthRequest, TokenResponse
from app.Auth.services.google_auth_service import verify_google_token
from app.Auth.services.session_service import create_access_token
from app.shared.errors import error_auth, responses
from app.Users.services import user_service

router = APIRouter()


@router.post("/google", response_model=TokenResponse)
def login_with_google(payload: GoogleAuthRequest, db: DBSession):
    try:
        user_data = verify_google_token(payload.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = user_service.get_or_create_user_by_google_id(db, user_data)
    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses=responses["auth_409"],
)
def register_with_email(payload: RegisterRequest, db: DBSession):
    """Create a local email + password account and sign the user straight in."""
    try:
        user = user_service.create_local_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse, responses=responses["auth_401"])
def login_with_email(payload: LoginRequest, db: DBSession):
    user = user_service.authenticate_local_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_auth["invalid_credentials"],
        )

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, responses=responses["auth_password"])
def set_account_password(payload: SetPasswordRequest, current_user: CurrentUser, db: DBSession):
    """Add a first password, or change an existing one, for the signed-in user.

    This is how a Google-only account gains password sign-in: prove who you
    are with Google first, then set a password. Doing it from an
    unauthenticated endpoint would let anyone who knows an address claim the
    account.
    """
    try:
        user_service.set_password(db, current_user, payload.new_password, payload.current_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
