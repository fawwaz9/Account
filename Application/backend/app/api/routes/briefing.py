"""Briefing routes under `/api/briefing`: the digest of a student's day (Phase 4 item 6).

The same digest feeds the Today card, the push briefing and, after its schema
step, the BYOAI endpoint and MCP route (item 7). No money in any of them (D8).
"""

from fastapi import APIRouter, HTTPException, Response, status

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from pydantic import BaseModel, Field

from app.Briefing.schemas.assistant import AssistantTokenMade, AssistantTokenStatus
from app.Briefing.schemas.digest import Digest
from app.Briefing.services import assistant_service
from app.Briefing.services.digest_service import build_digest
from app.shared.dates import user_for
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


# Phase 4 item 7 (D4): the assistant token, managed under the user's own session.

@router.get("/{user_id}/assistant-token", response_model=AssistantTokenStatus, responses=responses["user_404"])
def get_assistant_token(user_id: VerifiedUserId, db: DBSession):
    """Get whether the caller has an assistant token, and what to recognise it by.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Enabled or not, the prefix, when it was made and last used; never the token.
    """
    row = assistant_service.status(db, user_id)
    if row is None:
        return AssistantTokenStatus(enabled=False)
    return AssistantTokenStatus(enabled=True, prefix=row.prefix, created_at=row.created_at,
                                last_used_at=row.last_used_at)


@router.post("/{user_id}/assistant-token", response_model=AssistantTokenMade, status_code=201,
             responses=responses["user_404"])
def make_assistant_token(user_id: VerifiedUserId, db: DBSession):
    """Make a new assistant token for the caller, replacing any old one; shown once.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The token, its prefix and when it was made. Only its hash is kept.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    made = assistant_service.make(db, user_id)
    if made is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    token, row = made
    return AssistantTokenMade(token=token, prefix=row.prefix, created_at=row.created_at)


@router.delete("/{user_id}/assistant-token", status_code=204, responses=responses["user_404"])
def revoke_assistant_token(user_id: VerifiedUserId, db: DBSession):
    """Revoke the caller's assistant token; it stops working at once.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        No content, whether or not there was a token.
    """
    assistant_service.revoke(db, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class BriefingSchedule(BaseModel):
    """When the daily briefing push goes out (Phase 4 item 6).

    Attributes:
        hour: The local hour, 0-23; null turns it off.
    """
    hour: int | None = Field(default=None, ge=0, le=23)


@router.put("/{user_id}/schedule", response_model=BriefingSchedule, responses=responses["user_404"])
def set_briefing_schedule(user_id: VerifiedUserId, body: BriefingSchedule, db: DBSession):
    """Set the local hour of the daily briefing push, or turn it off with null.

    Its own route rather than the preferences patch, where a null means "no opinion"
    and so could never turn it off.

    Args:
        user_id: The verified caller's id.
        body: The hour, or null.
        db: Request-scoped database session.

    Returns:
        The schedule as stored.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    user = user_for(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    # Reassigned whole: SQLAlchemy does not see a mutation inside a JSON column.
    user.preferences = {**(user.preferences or {}), "briefing_hour": body.hour}
    db.commit()
    return BriefingSchedule(hour=body.hour)
