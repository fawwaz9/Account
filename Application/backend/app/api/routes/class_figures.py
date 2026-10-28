"""What other students' shared answers say about a course, under `/api/grades`.

One read per course, answering only through each figure's floor (Phase 3, D11). The
course must be the caller's own; nothing here returns another user's rows.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.class_figures import ClassFigures
from app.Grades.services import class_figures_service as service

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
