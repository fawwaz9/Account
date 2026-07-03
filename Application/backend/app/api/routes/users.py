from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.shared.errors import error_user, responses
from app.Users.schemas.user import User, UserCreate, UserDetail, UserUpdate
from app.Users.services.user_service import (
    create_user,
    delete_user,
    get_all_users,
    get_user,
    update_user,
)

router = APIRouter()


@router.get("", response_model=list[User])
def list_users():
    return get_all_users()


@router.post("", response_model=UserDetail, responses=responses["user_400"])
def add_user(user: UserCreate):
    try:
        return create_user(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{user_id}", response_model=UserDetail, responses=responses["user_404"])
def get_single_user(user_id: UUID):
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return user


@router.patch("/{user_id}", response_model=UserDetail, responses=responses["user_both"])
def edit_user(user_id: UUID, user: UserUpdate):
    try:
        updated_user = update_user(user_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if updated_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return updated_user


@router.delete("/{user_id}", response_model=UserDetail, responses=responses["user_404"])
def remove_user(user_id: UUID):
    deleted_user = delete_user(user_id)
    if deleted_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return deleted_user
