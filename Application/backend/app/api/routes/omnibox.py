"""Omnibox routes under /api/omnibox: preview and file one typed line.

The line is routed to Grades, Finances or Tasks by `omnibox_service` and filed
through that module's own service.
"""

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Omnibox.schemas.omnibox import OmniboxPreview, OmniboxRequest, OmniboxResult
from app.Omnibox.services.omnibox_service import build_preview, file_it
from app.shared.errors import error_user, responses
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

#: Which room a filed line landed in, for the usage counts.
OMNIBOX_MODULE = {"grade": "grades", "expense": "budget", "task": "tasks"}


@router.get("/{user_id}", response_model=OmniboxPreview, responses=responses["user_404"])
def preview_line(
    user_id: VerifiedUserId,
    db: DBSession,
    text: str = Query(..., min_length=1, max_length=300),
):
    """Show what one typed line would be filed as, without writing anything.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        text: The typed line, 1-300 characters.

    Returns:
        The reading: which module, what would be created, and why not if it cannot.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    preview = build_preview(db, user_id, text)
    if preview is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return preview


@router.post("/{user_id}", response_model=OmniboxResult, responses=responses["user_both"])
def file_line(user_id: VerifiedUserId, request: OmniboxRequest, db: DBSession):
    """File one typed line as a task, an expense or a grade.

    Args:
        user_id: The verified caller's id.
        request: The typed line.
        db: Request-scoped database session.

    Returns:
        What was created and where.

    Raises:
        HTTPException: 400 if the line cannot be filed (no course for a grade, no
            account for an expense, nothing left for a task title) or the owning
            service refuses it; 404 if the user does not exist.
    """
    try:
        result = file_it(db, user_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, OMNIBOX_MODULE.get(result.kind, "tasks"))
    return result
