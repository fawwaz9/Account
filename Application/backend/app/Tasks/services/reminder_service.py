"""Reminders: the things that notify rather than wait.

A task sits on a list until it is dealt with. A reminder has no life before or
after its moment -- being told is the point, and ticking it off is not -- which
is why it is a table of its own rather than a flag on a task.

**Where the delivery actually happens, and its limit.** There is no scheduler
and no push infrastructure. The client asks what is due, and the server answers
from the stored times. So a reminder fires when the app is open and not before,
and the interface says so plainly rather than letting anything important be
trusted to it. That is a real constraint, recorded here because the alternative
-- a service worker, VAPID keys and a process that outlives the request -- is a
large amount of infrastructure for a locally-run app.

**Time zones.** `remind_at` is naive *local wall time*, unlike `completed_at`
which is naive UTC. Nine o'clock means nine o'clock where the student is, and
must survive a clock change. Everything here therefore compares against local
now, resolved through the timezone preference, and never against `utc_now()`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app._database.models import CourseModel, ReminderModel, UserModel, utc_now
from app.Tasks.schemas.reminder import Reminder, ReminderCreate, ReminderUpdate
# Both live in `shared.dates` now: the same rule anchors free time, the
# finance months and the jobs figures, and three copies would drift.
from app.shared.dates import local_now, zone_of


def owned_user(db: Session, user_id: uuid.UUID) -> UserModel | None:
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def course_codes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (
        db.query(CourseModel.id, CourseModel.code)
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    return {row.id: row.code for row in rows}


def as_schema(row: ReminderModel, codes: dict, now: datetime) -> Reminder:
    return Reminder(
        id=row.id,
        title=row.title,
        notes=row.notes,
        remind_at=row.remind_at,
        course_id=row.course_id,
        fired_at=row.fired_at,
        pushed_at=row.pushed_at,
        dismissed_at=row.dismissed_at,
        created_at=row.created_at,
        course_code=codes.get(row.course_id),
        due=row.dismissed_at is None and row.remind_at <= now,
    )


def list_reminders(
    db: Session,
    user_id: uuid.UUID,
    include_dismissed: bool = False,
    at: datetime | None = None,
):
    user = owned_user(db, user_id)
    if user is None:
        return None

    query = db.query(ReminderModel).filter(ReminderModel.user_id == user_id)
    if not include_dismissed:
        query = query.filter(ReminderModel.dismissed_at.is_(None))

    rows = query.order_by(ReminderModel.remind_at).all()
    codes = course_codes(db, user_id)
    now = local_now(user, at)
    return [as_schema(row, codes, now) for row in rows]


def due_reminders(db: Session, user_id: uuid.UUID, at: datetime | None = None):
    """What should be on screen now, and marking that it has been.

    `fired_at` is set once and never re-set. A reminder surfaced on Monday and
    still not dismissed on Wednesday is the same reminder, and re-stamping it
    would make it read as new every time the page was opened -- which is how a
    notification becomes something you learn to ignore.
    """
    user = owned_user(db, user_id)
    if user is None:
        return None

    now = local_now(user, at)
    rows = (
        db.query(ReminderModel)
        .filter(
            ReminderModel.user_id == user_id,
            ReminderModel.dismissed_at.is_(None),
            ReminderModel.remind_at <= now,
        )
        .order_by(ReminderModel.remind_at)
        .all()
    )

    newly = [row for row in rows if row.fired_at is None]
    for row in newly:
        row.fired_at = utc_now()
    if newly:
        db.commit()

    codes = course_codes(db, user_id)
    return [as_schema(row, codes, now) for row in rows]


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def create_reminder(db: Session, user_id: uuid.UUID, data: ReminderCreate):
    user = owned_user(db, user_id)
    if user is None:
        return None

    if data.course_id is not None and owned_course(db, user_id, data.course_id) is None:
        raise ValueError("Course not found")

    row = ReminderModel(
        id=uuid.uuid4(),
        user_id=user_id,
        title=data.title.strip(),
        notes=data.notes,
        remind_at=data.remind_at,
        course_id=data.course_id,
        created_at=utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return as_schema(row, course_codes(db, user_id), local_now(user))


def get_reminder(db: Session, user_id: uuid.UUID, reminder_id: uuid.UUID):
    return (
        db.query(ReminderModel)
        .filter(ReminderModel.id == reminder_id, ReminderModel.user_id == user_id)
        .first()
    )


def update_reminder(
    db: Session, user_id: uuid.UUID, reminder_id: uuid.UUID, data: ReminderUpdate
):
    row = get_reminder(db, user_id, reminder_id)
    if row is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("course_id") is not None:
        if owned_course(db, user_id, update_data["course_id"]) is None:
            raise ValueError("Course not found")

    moved = "remind_at" in update_data
    for key, value in update_data.items():
        setattr(row, key, value)

    # Moving the time makes it a reminder that has not fired yet, whatever it
    # did before -- otherwise pushing one to tomorrow leaves it looking like it
    # already went off, and it would never be surfaced again.
    if moved:
        row.fired_at = None
        row.pushed_at = None
        row.dismissed_at = None

    db.commit()
    db.refresh(row)
    user = owned_user(db, user_id)
    return as_schema(row, course_codes(db, user_id), local_now(user))


def dismiss_reminder(db: Session, user_id: uuid.UUID, reminder_id: uuid.UUID):
    """Acknowledge it. The row stays: what you were reminded of is a record."""
    row = get_reminder(db, user_id, reminder_id)
    if row is None:
        return None

    if row.dismissed_at is None:
        row.dismissed_at = utc_now()
        db.commit()
        db.refresh(row)

    user = owned_user(db, user_id)
    return as_schema(row, course_codes(db, user_id), local_now(user))


def delete_reminder(db: Session, user_id: uuid.UUID, reminder_id: uuid.UUID):
    row = get_reminder(db, user_id, reminder_id)
    if row is None:
        return None

    user = owned_user(db, user_id)
    removed = as_schema(row, course_codes(db, user_id), local_now(user))
    db.delete(row)
    db.commit()
    return removed
