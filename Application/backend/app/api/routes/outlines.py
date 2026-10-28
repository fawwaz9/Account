"""Course outline routes under `/api/grades` (Phase 3 item 2, D12).

A student offers their own course's outline for the owner's review, takes the offer
back, and fills an empty course from a reviewed outline for the same course and
term. The course in the path must be the caller's own.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.outline import OutlineStatus
from app.Grades.services import outline_service as service

router = APIRouter()

NO_COURSE = "Course not found"
COURSE_404 = {404: {"description": NO_COURSE}}
COURSE_BOTH = {**COURSE_404, 400: {"description": "Not possible for this course"}}


@router.get("/{user_id}/courses/{course_id}/outline", response_model=OutlineStatus, responses=COURSE_404)
def get_outline(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Read what the caller can do with outlines on one of their courses.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        Whether its outline can be offered, the caller's own offer, and any reviewed
        outline for its course and term.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    found = service.status(db, user_id, course_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return found


@router.post("/{user_id}/courses/{course_id}/outline/offer", response_model=OutlineStatus, responses=COURSE_BOTH)
def offer_outline(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Offer this course's outline to classmates, for the owner's review.

    Shares the weights and the assessments' names, categories and due dates, never a
    score or a note; offering again replaces the earlier offer.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The outline status, with the offer pending.

    Raises:
        HTTPException: 400 when the outline can't be offered (the message says why);
            404 when the course is missing or another user's.
    """
    try:
        found = service.offer(db, user_id, course_id)
    except service.OutlineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return found


@router.delete("/{user_id}/courses/{course_id}/outline/offer", responses={404: {"description": "No offer"}})
def withdraw_outline(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Take back the caller's offer of a course's outline; an approved one stays shared.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when there is no offer, or the course is missing or another
            user's.
    """
    if not service.withdraw(db, user_id, course_id):
        raise HTTPException(status_code=404, detail="No offer of this course's outline")
    return {"deleted": True}


@router.post("/{user_id}/courses/{course_id}/outline/apply", response_model=OutlineStatus, responses=COURSE_BOTH)
def apply_outline(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Fill an empty course from the reviewed outline for its course and term.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The outline status after filling it.

    Raises:
        HTTPException: 400 when there's no reviewed outline or the course already has
            grades; 404 when the course is missing or another user's.
    """
    try:
        found = service.apply(db, user_id, course_id)
    except service.OutlineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return found
