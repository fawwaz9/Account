from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.shared.errors import error_user, responses
from Application.backend.app.Users.services.user_service import get_user

router = APIRouter()


@router.get("/{user_id}/events", responses=responses["user_404"])
def list_events(user_id: UUID):
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return [
        {"id": "event-1", "title": "Sample event", "user_id": str(user_id)}
    ]
