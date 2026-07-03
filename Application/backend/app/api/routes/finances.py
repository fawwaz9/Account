from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.shared.errors import error_user, responses
from Application.backend.app.Users.services.user_service import get_user

router = APIRouter()


@router.get("/{user_id}/budgets", responses=responses["user_404"])
def list_budgets(user_id: UUID):
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return [{"id": "budget-1", "name": "Sample budget", "user_id": str(user_id)}]


@router.get("/{user_id}/goals", responses=responses["user_404"])
def list_goals(user_id: UUID):
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return [{"id": "goal-1", "name": "Sample goal", "user_id": str(user_id)}]
