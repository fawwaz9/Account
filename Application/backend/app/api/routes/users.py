"""User routes under `/api/users`: profile, academic status, edits and deletion."""

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
    attach_year_suggestion,
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
def get_me(current_user: CurrentUser, db: DBSession):
    """Return the signed-in user's profile, with the suggested first-year anchor.

    Args:
        current_user: The signed-in user.
        db: Request-scoped database session.

    Returns:
        The user, never including the password hash.
    """
    # Attached here too, not only on the academic-status route. Settings takes
    # its user from /me, so the year suggestion it offers is read from this
    # payload -- without this the field is always null and the control that
    # depends on it can never appear.
    return attach_year_suggestion(db, current_user)


@router.get("/{user_id}/academic-status", response_model=User, responses=responses["user_404"])
def get_academic_status(user_id: VerifiedUserId, db: DBSession):
    """Return the user with their academic status and suggested first-year anchor.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The user.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return attach_year_suggestion(db, user)


@router.patch("/{user_id}/academic-status", response_model=User, responses=responses["user_both"])
def edit_academic_status(user_id: VerifiedUserId, status: AcademicStatusUpdate, db: DBSession):
    """Set the student's current term, which decides past, current and future.

    Args:
        user_id: The verified caller's id.
        status: The fields to change; omitted ones stay.
        db: Request-scoped database session.

    Returns:
        The updated user.

    Raises:
        HTTPException: 404 when the user does not exist.
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
    """Return the user with every course and its grades.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The user and their courses; the courses carry no computed summary fields.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return user


@router.patch("/{user_id}", response_model=UserDetail, responses=responses["user_both"])
def edit_user(user_id: VerifiedUserId, user: UserUpdate, db: DBSession):
    """Change the user's name, email or preferences; Settings saves through this.

    Preferences are merged key by key; a new email is no longer verified.

    Args:
        user_id: The verified caller's id.
        user: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated user with every course and its grades.

    Raises:
        HTTPException: 400 when another account has the email; 404 when the user does
            not exist.
    """
    try:
        updated_user = update_user(db, user_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated_user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return updated_user


@router.delete("/{user_id}", response_model=UserDetail, responses=responses["user_404"])
def remove_user(user_id: VerifiedUserId, db: DBSession):
    """Schedule the account for deletion and sign out every session at once.

    Nothing is removed now; the account stays recoverable through `POST
    /{user_id}/restore` until `deletes_on`, and signing in still works meanwhile.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The user, with `deleted_at` and `deletes_on` set.

    Raises:
        HTTPException: 404 when the user does not exist.
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
    """Cancel a pending account deletion while the grace period runs.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The restored user.

    Raises:
        HTTPException: 404 when there is no pending deletion.
    """
    restored = restore_user(db, user_id)
    if restored is None:
        raise HTTPException(
            status_code=404, detail="No pending deletion to restore"
        )

    audit.deletion(
        "user_restore", user_id=user_id, target_id=user_id, detail=restored.email
    )
    return restored
