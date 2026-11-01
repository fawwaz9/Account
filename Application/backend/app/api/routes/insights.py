"""Insight routes under `/api/insights`: the term simulator (Phase 4 item 9).

Cross-room by design; each figure still comes from its own room's engine, and the
academic part renders only from study hours set directly (§13.19).
"""

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Insights.schemas.term_sim import TermDefaults, TermIn, TermResult
from app.Insights.services.term_sim_service import defaults, simulate
from app.shared.errors import error_user, responses

router = APIRouter()


@router.get("/{user_id}/term/defaults", response_model=TermDefaults, responses=responses["user_404"])
def get_term_defaults(user_id: VerifiedUserId, db: DBSession):
    """Get where each term-simulator slider starts, from the caller's own figures.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Class, study and work hours over the next four weeks, recent workouts, and
        the exertion goal.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = defaults(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/term", response_model=TermResult, responses=responses["user_404"])
def simulate_term(user_id: VerifiedUserId, body: TermIn, db: DBSession):
    """Simulate one week of the term across the rooms; nothing is stored.

    Args:
        user_id: The verified caller's id.
        body: The sliders.
        db: Request-scoped database session.

    Returns:
        The 168-hour fit, the money and exertion figures, and what directly set study
        hours cover.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = simulate(db, user_id, body)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found
