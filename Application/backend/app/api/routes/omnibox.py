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
    """What one line would be filed as, without writing anything.

    A read, so the client can call it while the student types and show which
    module the line is heading for. An omnibox that files silently is the one
    shape of this feature worth not building.
    """
    preview = build_preview(db, user_id, text)
    if preview is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return preview


@router.post("/{user_id}", response_model=OmniboxResult, responses=responses["user_both"])
def file_line(user_id: VerifiedUserId, request: OmniboxRequest, db: DBSession):
    """File the line into whichever module it belongs to."""
    try:
        result = file_it(db, user_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, OMNIBOX_MODULE.get(result.kind, "tasks"))
    return result
