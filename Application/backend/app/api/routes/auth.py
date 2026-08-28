from fastapi import APIRouter, HTTPException, status

from app._database.dependencies import DBSession
from app.Auth.schemas.token import GoogleAuthRequest, TokenResponse
from app.Auth.services.google_auth_service import verify_google_token
from app.Auth.services.session_service import create_access_token
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