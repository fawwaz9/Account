from fastapi import APIRouter, HTTPException, status

from app._database.dependencies import DBSession
from app.Auth.schemas.credentials import LoginRequest, RegisterRequest
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
