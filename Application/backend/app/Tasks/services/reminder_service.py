"""Service functions for reminders: things that notify at a moment rather than wait.

The open app asks what is due and this module answers from the stored times,
stamping `fired_at` the first time each reminder is shown; pushing to devices is
the Notifications scheduler's job, which stamps `pushed_at`. `remind_at` is naive
local wall time, so every comparison is against the user's own local now.
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
    """Return the user row, or None when it does not exist.

    Args:
        db: Open database session.
        user_id: Id to look up.

    Returns:
        The user row, or None.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def course_codes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Return the user's course ids mapped to their codes, for labelling reminders.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Course id to code, for every course the user has.
    """
    rows = (
        db.query(CourseModel.id, CourseModel.code)
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    return {row.id: row.code for row in rows}


def as_schema(row: ReminderModel, codes: dict, now: datetime) -> Reminder:
    """Build a reminder's response from its row, working out whether it is due.

    Args:
        row: The reminder row.
        codes: The user's course ids mapped to codes.
        now: The user's local now, naive.

    Returns:
        The reminder, with `due` True when `remind_at` has passed and it is not
        dismissed.
    """
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
    """Return the user's reminders, earliest first.

    Args:
        db: Open database session.
        user_id: Whose reminders.
        include_dismissed: Also return dismissed reminders.
        at: The moment to judge `due` against, aware or naive UTC; defaults to now.

    Returns:
        The reminders; None when the user does not exist.
    """
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
    """Return the reminders that should be on screen now, marking new ones as shown.

    `fired_at` is set the first time a reminder is returned and never again, so one
    left undismissed does not read as new each time the app opens. Commits when it
    stamps anything.

    Args:
        db: Open database session.
        user_id: Whose reminders.
        at: The moment to judge against; defaults to now.

    Returns:
        Undismissed reminders whose time has passed on the user's clock, earliest
        first; None when the user does not exist.
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
    """Return the user's course with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        course_id: The course to fetch.

    Returns:
        The course, or None when it is missing or another user's.
    """
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def create_reminder(db: Session, user_id: uuid.UUID, data: ReminderCreate):
    """Create a reminder for the user.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose reminder.
        data: The reminder; its title is stripped.

    Returns:
        The new reminder; None when the user does not exist.

    Raises:
        ValueError: If `course_id` is not one of the user's courses.
    """
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
    """Return the user's reminder row with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        reminder_id: The reminder to fetch.

    Returns:
        The reminder row, or None when it is missing or another user's.
    """
    return (
        db.query(ReminderModel)
        .filter(ReminderModel.id == reminder_id, ReminderModel.user_id == user_id)
        .first()
    )


def update_reminder(
    db: Session, user_id: uuid.UUID, reminder_id: uuid.UUID, data: ReminderUpdate
):
    """Change the fields sent on one of the user's reminders.

    Moving `remind_at` re-arms it: `fired_at`, `pushed_at` and `dismissed_at` are
    cleared so it is shown and pushed again. Commits.

    Args:
        db: Open database session.
        user_id: Whose reminder.
        reminder_id: The reminder.
        data: The fields to change.

    Returns:
        The updated reminder; None when it is not the user's.

    Raises:
        ValueError: If a new `course_id` is not one of the user's courses.
    """
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
    """Mark one of the user's reminders as dismissed; the row is kept as a record.

    Dismissing twice keeps the first time. Commits when it changes anything.

    Args:
        db: Open database session.
        user_id: Whose reminder.
        reminder_id: The reminder.

    Returns:
        The reminder as it now stands; None when it is not the user's.
    """
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
    """Delete one of the user's reminders.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose reminder.
        reminder_id: The reminder.

    Returns:
        A copy of the deleted reminder; None when it is not the user's.
    """
    row = get_reminder(db, user_id, reminder_id)
    if row is None:
        return None

    user = owned_user(db, user_id)
    removed = as_schema(row, course_codes(db, user_id), local_now(user))
    db.delete(row)
    db.commit()
    return removed
