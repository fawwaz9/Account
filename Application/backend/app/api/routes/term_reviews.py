"""End-of-term review routes under `/api/grades`, and the scheduler's recount.

Every user route reads and writes the caller's own reviews only and returns no
aggregate; `internal` holds `POST /api/internal/distributions/recount`, which only
the scheduler may call.
"""
import hmac
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from app._database import distributions
from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.config import settings
from app.Grades.schemas.term_review import TermReview, TermReviewIn, TermReviews
from app.Grades.services import term_review_service as service
from app.shared import audit
from app.shared.errors import error_user, responses

router = APIRouter()
internal = APIRouter()
"""Routes mounted under `/api/internal`, for the scheduler."""

COURSE_404 = {404: {"description": "Course not found"}}
COURSE_BOTH = {**COURSE_404, 400: {"description": "Can't be saved"}}
NO_COURSE = "Course not found"


@router.get("/{user_id}/term-reviews", response_model=TermReviews, responses=responses["user_404"])
def get_term_reviews(user_id: VerifiedUserId, db: DBSession):
    """List the student's finished courses in their review window, with any reviews.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The courses and how many still await an answer.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = service.overview(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.put("/{user_id}/term-reviews/{course_id}", response_model=TermReview, responses=COURSE_BOTH)
def save_term_review(user_id: VerifiedUserId, course_id: UUID, body: TermReviewIn, db: DBSession):
    """Answer, or change, the review of a finished course, including the grade opt-in.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        body: The answers and the opt-in.
        db: Request-scoped database session.

    Returns:
        The saved review.

    Raises:
        HTTPException: 400 when the course is outside its window, the answers have
            locked, or a grade cannot be contributed; 404 when the course is missing or
            another user's.
    """
    try:
        saved = service.save(db, user_id, course_id, body)
    except service.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return saved


@router.post("/{user_id}/term-reviews/{course_id}/skip", response_model=TermReview, responses=COURSE_BOTH)
def skip_term_review(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Decline to review a course, so it is not asked about again.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The skipped review.

    Raises:
        HTTPException: 400 when it was already answered or is outside its window; 404
            when the course is missing or another user's.
    """
    try:
        skipped = service.skip(db, user_id, course_id)
    except service.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if skipped is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return skipped


@router.delete("/{user_id}/term-reviews/{course_id}", responses=COURSE_404)
def delete_term_review(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Delete the review of a course, grade contribution included; audit-logged.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when there is no review of that course.
    """
    if not service.remove(db, user_id, course_id):
        raise HTTPException(status_code=404, detail="No review of that course")
    audit.deletion("term_review", user_id=user_id, target_id=course_id)
    return {"deleted": True}


@internal.post("/distributions/recount")
def recount(db: DBSession, x_cron_secret: str | None = Header(default=None)):
    """Rebuild the sealed grade distributions; for the daily scheduler only.

    Args:
        db: Request-scoped database session; no acting user is needed.
        x_cron_secret: The `X-Cron-Secret` header, compared in constant time with
            `CRON_SECRET`.

    Returns:
        `{"rows": n}`, how many band rows were written, never their contents.

    Raises:
        HTTPException: 404 when `CRON_SECRET` is not configured; 403 when the header is
            missing or wrong.
    """
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"rows": distributions.recount(db)}
