"""Briefing routes under `/api/briefing`: the digest of a student's day (Phase 4 item 6).

The same digest feeds the Today card, the push briefing and, after its schema
step, the BYOAI endpoint and MCP route (item 7). No money in any of them (D8).
"""

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Briefing.schemas.digest import Digest
from app.Briefing.services.digest_service import build_digest
from app.shared.errors import error_user, responses

router = APIRouter()


@router.get("/{user_id}/digest", response_model=Digest, responses=responses["user_404"])
def get_digest(user_id: VerifiedUserId, db: DBSession):
    """Get the caller's digest for today, with its plain-text rendering.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Today's calendar, work due and overdue, exams, deadline risk, the week's load
        and free time; no money.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    digest = build_digest(db, user_id)
    if digest is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return digest
