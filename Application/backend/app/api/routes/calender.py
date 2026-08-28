from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.shared.errors import error_user, responses
from app.Users.services.user_service import get_user

router = APIRouter()


@router.get("/{user_id}/events", responses=responses["user_404"])
def list_events(user_id: VerifiedUserId, db: DBSession):
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return [
        {"id": "event-1", "title": "Sample event", "user_id": str(user_id)}
    ]