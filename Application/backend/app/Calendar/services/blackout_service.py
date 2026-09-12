"""Stretches of term when classes do not run.

Kept apart from an event's own `skipped_dates`, which cancels one lecture on one
date. This is the other case: a reading break applies to every class at once,
and entering it on each of six courses is how one of them ends up wrong.
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
    return TermBlackout(
        id=row.id,
        label=row.label,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        days=(row.ends_on - row.starts_on).days + 1,
    )


def list_blackouts(db: Session, user_id: uuid.UUID) -> list[TermBlackout] | None:
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
    """Every date any blackout covers, as a flat set.

    Ranges are stored, dates are what the recurrence engine subtracts -- it
    already takes a set of skipped dates, so expanding here means the engine
    needs no idea that blackouts exist.
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
