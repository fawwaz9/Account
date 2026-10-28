"""Fitness routes under `/api/fitness` beyond teams (Phase 3 items 6-8 and 13).

Every route reads and writes the caller's own rows; what the caller sees of anyone
else comes through a definer function, and only among their own connections.
"""
from fastapi import APIRouter

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Fitness.schemas.fitness import GymBuddies, GymBuddyIn
from app.Fitness.services import gym_buddy_service

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
