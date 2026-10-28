"""Service functions for term blackouts: breaks when no class runs.

A blackout is a date range that cancels every occurrence of the user's
course-linked events inside it, where an event's own `skipped_dates` cancels one
date of one series. Repeating payments, tasks and shifts are never affected.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import TermBlackoutModel
from app.Calendar.schemas.blackout import (
    TermBlackout,
    TermBlackoutCreate,
    TermBlackoutUpdate,
)
from app.Tasks.services.task_service import user_exists

#: A guard on one row, not on the year. A range longer than this is a typo --
#: someone meaning 2026 and typing 2062 -- and expanding it would hand the
#: recurrence engine a set with tens of thousands of dates in it.
MAX_BLACKOUT_DAYS = 120


def as_schema(row: TermBlackoutModel) -> TermBlackout:
    """Build a blackout's response from its row, counting the days it covers.

    Args:
        row: The stored blackout.

    Returns:
        The blackout with its inclusive day count.
    """
    return TermBlackout(
        id=row.id,
        label=row.label,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        days=(row.ends_on - row.starts_on).days + 1,
    )


def list_blackouts(db: Session, user_id: uuid.UUID) -> list[TermBlackout] | None:
    """Return the user's blackouts, earliest first.

    Args:
        db: Open database session.
        user_id: Whose blackouts.

    Returns:
        The blackouts; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None
    rows = (
        db.query(TermBlackoutModel)
        .filter(TermBlackoutModel.user_id == user_id)
        .order_by(TermBlackoutModel.starts_on)
        .all()
    )
    return [as_schema(row) for row in rows]


def blackout_dates(db: Session, user_id: uuid.UUID) -> set[date]:
    """Return every date any of the user's blackouts covers, as one flat set.

    The recurrence engine subtracts these like skipped dates. Each range is capped
    at `MAX_BLACKOUT_DAYS` when expanded.

    Args:
        db: Open database session.
        user_id: Whose blackouts.

    Returns:
        The covered dates; empty when there are none.
    """
    covered: set[date] = set()
    rows = (
        db.query(TermBlackoutModel)
        .filter(TermBlackoutModel.user_id == user_id)
        .all()
    )
    for row in rows:
        span = min((row.ends_on - row.starts_on).days, MAX_BLACKOUT_DAYS)
        for offset in range(span + 1):
            covered.add(row.starts_on + timedelta(days=offset))
    return covered


def create_blackout(db: Session, user_id: uuid.UUID, data: TermBlackoutCreate):
    """Create a blackout for the user.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose blackout.
        data: The label (stripped) and the inclusive date range.

    Returns:
        The new blackout; None when the user does not exist.

    Raises:
        ValueError: If the range is longer than `MAX_BLACKOUT_DAYS` days.
    """
    if not user_exists(db, user_id):
        return None

    span = (data.ends_on - data.starts_on).days + 1
    if span > MAX_BLACKOUT_DAYS:
        raise ValueError(
            f"A blocked period cannot be longer than {MAX_BLACKOUT_DAYS} days"
        )

    row = TermBlackoutModel(
        id=uuid.uuid4(),
        user_id=user_id,
        label=data.label.strip(),
        starts_on=data.starts_on,
        ends_on=data.ends_on,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return as_schema(row)


def update_blackout(
    db: Session, user_id: uuid.UUID, blackout_id: uuid.UUID, data: TermBlackoutUpdate
):
    """Change the fields sent on one of the user's blackouts.

    The merged range is checked once both ends are in place; null fields are
    ignored. Commits, or rolls back on a refusal.

    Args:
        db: Open database session.
        user_id: Whose blackout.
        blackout_id: The blackout.
        data: The fields to change.

    Returns:
        The updated blackout; None when it is not the user's.

    Raises:
        ValueError: If the range would end before it starts, or be longer than
            `MAX_BLACKOUT_DAYS` days.
    """
    row = (
        db.query(TermBlackoutModel)
        .filter(
            TermBlackoutModel.id == blackout_id,
            TermBlackoutModel.user_id == user_id,
        )
        .first()
    )
    if row is None:
        return None

    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value.strip() if key == "label" else value)

    # Checked after both ends are applied: a partial update can move either one
    # independently, so the pair is only valid once both are in place.
    if row.ends_on < row.starts_on:
        db.rollback()
        raise ValueError("A blocked period ends before it starts")
    if (row.ends_on - row.starts_on).days + 1 > MAX_BLACKOUT_DAYS:
        db.rollback()
        raise ValueError(
            f"A blocked period cannot be longer than {MAX_BLACKOUT_DAYS} days"
        )

    db.commit()
    db.refresh(row)
    return as_schema(row)


def delete_blackout(db: Session, user_id: uuid.UUID, blackout_id: uuid.UUID):
    """Delete one of the user's blackouts.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose blackout.
        blackout_id: The blackout.

    Returns:
        A copy of the deleted blackout; None when it is not the user's.
    """
    row = (
        db.query(TermBlackoutModel)
        .filter(
            TermBlackoutModel.id == blackout_id,
            TermBlackoutModel.user_id == user_id,
        )
        .first()
    )
    if row is None:
        return None

    removed = as_schema(row)
    db.delete(row)
    db.commit()
    return removed
