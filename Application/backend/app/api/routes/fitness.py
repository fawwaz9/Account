"""Fitness routes under `/api/fitness` beyond teams (Phase 3 items 6-8 and 13).

Every route reads and writes the caller's own rows; what the caller sees of anyone
else comes through a definer function, and only among their own connections.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Fitness.schemas.fitness import Activity, ActivityIn, Exertion, GoalIn, GymBuddies, GymBuddyIn
from app.Fitness.services import exertion_service, gym_buddy_service
from app.shared.errors import error_user, responses

router = APIRouter()


@router.get("/{user_id}/gym-buddy", response_model=GymBuddies)
def get_gym_buddy(user_id: VerifiedUserId, db: DBSession):
    """Read the caller's gym-buddy status and the connections looking too.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The status, and partners and teammates also looking, while the caller is.
    """
    return gym_buddy_service.read(db, user_id)


@router.put("/{user_id}/gym-buddy", response_model=GymBuddies)
def save_gym_buddy(user_id: VerifiedUserId, body: GymBuddyIn, db: DBSession):
    """Say whether the caller is looking for someone to train with.

    Args:
        user_id: The verified caller's id.
        body: Looking or not, when, and a note.
        db: Request-scoped database session.

    Returns:
        The saved status and the connections looking too.
    """
    return gym_buddy_service.save(db, user_id, body)


@router.get("/{user_id}/exertion", response_model=Exertion, responses=responses["user_404"])
def get_exertion(user_id: VerifiedUserId, db: DBSession):
    """Read this week's exertion points against the goal, the weeks before, and a suggestion.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The week, the goal, a suggested goal with its reason, 8 weeks before, and the
        last 28 days' activities.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = exertion_service.summary(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.put("/{user_id}/exertion/goal", response_model=Exertion, responses=responses["user_404"])
def set_goal(user_id: VerifiedUserId, body: GoalIn, db: DBSession):
    """Set the weekly exertion goal, or clear it with null.

    Args:
        user_id: The verified caller's id.
        body: The goal.
        db: Request-scoped database session.

    Returns:
        The summary with the new goal.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = exertion_service.set_goal(db, user_id, body.goal)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/activities", response_model=Activity)
def log_activity(user_id: VerifiedUserId, body: ActivityIn, db: DBSession):
    """Log an activity; its points are worked out now and never rewritten.

    Args:
        user_id: The verified caller's id.
        body: What, when and how long.
        db: Request-scoped database session.

    Returns:
        The activity with its points.
    """
    return exertion_service.log(db, user_id, body)


@router.delete("/{user_id}/activities/{activity_id}", responses={404: {"description": "Activity not found"}})
def delete_activity(user_id: VerifiedUserId, activity_id: UUID, db: DBSession):
    """Delete one of the caller's activities.

    Args:
        user_id: The verified caller's id.
        activity_id: The activity.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when it is missing or another user's.
    """
    if not exertion_service.delete(db, user_id, activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"deleted": True}
