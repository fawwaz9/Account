"""End-of-term reviews (Phase 2 item 13, D25), under /api/grades.

Every route reads and writes only the caller's own reviews. None returns an
aggregate: the counts live in a table the API's role can't read. The daily
recount has its own door, for the scheduler alone.
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

COURSE_404 = {404: {"description": "Course not found"}}
COURSE_BOTH = {**COURSE_404, 400: {"description": "Can't be saved"}}
NO_COURSE = "Course not found"


@router.get("/{user_id}/term-reviews", response_model=TermReviews, responses=responses["user_404"])
def get_term_reviews(user_id: VerifiedUserId, db: DBSession):
    found = service.overview(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.put("/{user_id}/term-reviews/{course_id}", response_model=TermReview, responses=COURSE_BOTH)
def save_term_review(user_id: VerifiedUserId, course_id: UUID, body: TermReviewIn, db: DBSession):
    try:
        saved = service.save(db, user_id, course_id, body)
    except service.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return saved


@router.post("/{user_id}/term-reviews/{course_id}/skip", response_model=TermReview, responses=COURSE_BOTH)
def skip_term_review(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    try:
        skipped = service.skip(db, user_id, course_id)
    except service.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if skipped is None:
        raise HTTPException(status_code=404, detail=NO_COURSE)
    return skipped


@router.delete("/{user_id}/term-reviews/{course_id}", responses=COURSE_404)
def delete_term_review(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    if not service.remove(db, user_id, course_id):
        raise HTTPException(status_code=404, detail="No review of that course")
    audit.deletion("term_review", user_id=user_id, target_id=course_id)
    return {"deleted": True}


@internal.post("/distributions/recount")
def recount(db: DBSession, x_cron_secret: str | None = Header(default=None)):
    """Called by the scheduler once a day; by nobody else. Answers with how
    many rows were written -- never with what is in them.

    Like reminder dispatch: missing without CRON_SECRET (404), refused for any
    other caller (403), compared in constant time.
    """
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"rows": distributions.recount(db)}
