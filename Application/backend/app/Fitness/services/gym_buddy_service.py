"""Gym buddies (Phase 3 item 13): your status, and connections looking too.

Only within existing connections, mutual partners and teammates, and only while
you're visible yourself; nobody else is ever shown. The cross-user read lives in
`_database/connections.py`.
"""
import uuid

from sqlalchemy.orm import Session

from app._database import connections
from app._database.models import GymBuddyModel, utc_now
from app.Fitness.schemas.fitness import GymBuddies, GymBuddyIn, GymBuddyOut


def _clean(value: str | None) -> str | None:
    """Return text stripped, or None when blank."""
    value = (value or "").strip()
    return value or None


def via_line(ways: list[str]) -> str:
    """Return how you know someone as read: "partner" first, then teams alphabetically."""
    return ", ".join(sorted(set(ways), key=lambda way: (way != "partner", way.casefold(), way)))


def read(db: Session, user_id: uuid.UUID) -> GymBuddies:
    """Return the caller's status and the connections looking too.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The status (not looking when never set) and the looking connections.
    """
    mine = db.query(GymBuddyModel).filter_by(user_id=user_id).first()
    buddies = [GymBuddyOut(name=b.name, times=b.times, note=b.note, via=via_line(b.via))
               for b in connections.gym_buddies(db, user_id)]
    if mine is None:
        return GymBuddies(buddies=buddies)
    return GymBuddies(looking=mine.looking, times=mine.times, note=mine.note, buddies=buddies)


def save(db: Session, user_id: uuid.UUID, data: GymBuddyIn) -> GymBuddies:
    """Set whether the caller is looking, with when and a note.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The new status.

    Returns:
        The status and the connections looking too, as `read` gives them.

    Note:
        Commits.
    """
    mine = db.query(GymBuddyModel).filter_by(user_id=user_id).first()
    if mine is None:
        mine = GymBuddyModel(user_id=user_id)
        db.add(mine)
    mine.looking, mine.times, mine.note, mine.updated_at = data.looking, _clean(data.times), _clean(data.note), utc_now()
    db.commit()
    return read(db, user_id)
