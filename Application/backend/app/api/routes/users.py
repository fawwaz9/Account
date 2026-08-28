from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.Auth.services.access import VerifiedUserId
from app.Auth.dependencies import CurrentUser
from app._database.dependencies import DBSession
from app.shared.errors import error_user, responses
from app.Users.schemas.user import UserDetail, UserUpdate
from app.Users.services.user_service import (
    delete_user,
    get_user,
    update_user,
)

router = APIRouter()

@router.get("/me")
def get_me(current_user: CurrentUser):
    return current_user


@router.get("/{user_id}", response_model=UserDetail, responses=responses["user_404"])
def get_single_user(user_id: VerifiedUserId, db: DBSession):
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return user


@router.patch("/{user_id}", response_model=UserDetail, responses=responses["user_both"])
def edit_user(user_id: VerifiedUserId, user: UserUpdate, db: DBSession):
    try:
        updated_user = update_user(db, user_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if updated_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return updated_user


@router.delete("/{user_id}", response_model=UserDetail, responses=responses["user_404"])
def remove_user(user_id: VerifiedUserId, db: DBSession):
    deleted_user = delete_user(db, user_id)
    if deleted_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return deleted_user