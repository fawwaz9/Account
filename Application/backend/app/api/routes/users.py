from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.Auth.services.access import VerifiedUserId
from app.Auth.dependencies import CurrentUser
from app._database.dependencies import DBSession
from app.shared.errors import error_user, responses
from app.Users.schemas.academic_status import AcademicStatusUpdate
from app.Users.schemas.user import User, UserDetail, UserUpdate
from app.shared import audit
from app.Users.services.user_service import (
    delete_user,
    get_user,
    restore_user,
    update_academic_status,
    update_user,
)

router = APIRouter()

# response_model is load-bearing: without it FastAPI serializes the raw
# SQLAlchemy row, which now includes password_hash.
@router.get("/me", response_model=User)
def get_me(current_user: CurrentUser):
    return current_user


@router.get("/{user_id}/academic-status", response_model=User, responses=responses["user_404"])
def get_academic_status(user_id: VerifiedUserId, db: DBSession):
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return user


@router.patch("/{user_id}/academic-status", response_model=User, responses=responses["user_both"])
def edit_academic_status(user_id: VerifiedUserId, status: AcademicStatusUpdate, db: DBSession):
    """Set the term the student is currently in.

    Drives past/current/future on the grades page; while it is unset every
    course reads as current.
    """
    try:
        user = update_academic_status(db, user_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return user


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
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return updated_user


@router.delete("/{user_id}", response_model=UserDetail, responses=responses["user_404"])
def remove_user(user_id: VerifiedUserId, db: DBSession):
    """Schedule the account for deletion, and end every session at once.

    Nothing is removed today. The account and everything under it stay for the
    grace period, and the response carries `deletes_on` so the caller can say
    when it stops being recoverable. Signing in still works until then, which
    is what makes `POST /{user_id}/restore` reachable at all.
    """
    deleted_user = delete_user(db, user_id)
    if deleted_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    # The most consequential mutation in the app, even now that it is
    # reversible. If any single line in this log matters, it is this one.
    audit.deletion("user", user_id=user_id, target_id=user_id, detail=deleted_user.email)
    return deleted_user


@router.post("/{user_id}/restore", response_model=UserDetail, responses=responses["user_404"])
def undo_remove_user(user_id: VerifiedUserId, db: DBSession):
    """Cancel a pending deletion, while the grace period is still running."""
    restored = restore_user(db, user_id)
    if restored is None:
        raise HTTPException(
            status_code=404, detail="No pending deletion to restore"
        )

    audit.deletion(
        "user_restore", user_id=user_id, target_id=user_id, detail=restored.email
    )
    return restored