"""What other students' shared answers say about a course, under `/api/grades`.

One read per course, answering only through each figure's floor (Phase 3, D11), and
the caller's own office-hour check-ins (item 11). The course must be the caller's
own; nothing here returns another user's rows.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.class_figures import ClassFigures, OfficeHourCheckIn, OfficeHourCheckInOut
from app.Grades.services import class_figures_service as service
from app.Grades.services import office_hours_service

router = APIRouter()

COURSE_404 = {404: {"description": "Course not found"}}


@router.get("/{user_id}/courses/{course_id}/class-figures", response_model=ClassFigures, responses=COURSE_404)
def get_class_figures(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Read what past classes' shared answers say about one of the caller's courses.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        Each closed term's grade bands above the floor, and the caller's own grade
        and band to set beside them.

    Raises:
        HTTPException: 404 when the course is missing or another user's.
    """
    figures = service.class_figures(db, user_id, course_id)
    if figures is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return figures


@router.post("/{user_id}/courses/{course_id}/office-hours", response_model=OfficeHourCheckInOut,
             responses={**COURSE_404, 400: {"description": "Can't be counted"}})
def check_in(user_id: VerifiedUserId, course_id: UUID, body: OfficeHourCheckIn, db: DBSession):
    """Check in at a course's office hours, saying how the line is right now.

    A second tap within half an hour changes the first answer instead of adding one.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        body: How the line is.
        db: Request-scoped database session.

    Returns:
        The check-in, with the local weekday and hour it counts under.

    Raises:
        HTTPException: 400 when the course is transfer credit or its code can't be
            counted; 404 when the course is missing or another user's.
    """
    try:
        row = office_hours_service.check_in(db, user_id, course_id, body.wait)
    except office_hours_service.CheckInError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return row


@router.delete("/{user_id}/office-hours/{checkin_id}", responses={404: {"description": "Check-in not found"}})
def undo_check_in(user_id: VerifiedUserId, checkin_id: UUID, db: DBSession):
    """Take back one of the caller's office-hour check-ins.

    Args:
        user_id: The verified caller's id.
        checkin_id: The check-in.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the check-in is missing or another user's.
    """
    if not office_hours_service.remove(db, user_id, checkin_id):
        raise HTTPException(status_code=404, detail="Check-in not found")
    return {"deleted": True}
