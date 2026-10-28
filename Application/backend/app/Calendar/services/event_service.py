"""Service functions for calendar events and the dates they fall on.

One row stores an event however often it repeats; `list_occurrences` expands the
rules in memory for exactly the window asked for, subtracting skipped dates and,
for course events, term blackouts. Shifts, grade blocks and the load figures all
read the calendar through it.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import CourseModel, EventModel, UserModel
from app.Calendar.schemas.event import (
    Event as EventSchema,
    EventCreate,
    EventOccurrence,
    EventUpdate,
    Recurrence,
)
from app.Calendar.utils.recurrence import occurrences
from app.Calendar.services.blackout_service import blackout_dates
from app.Calendar.utils.rule_columns import apply_recurrence, recurrence_of, rule_of

#: Longest window one read may ask for. A year of a daily event is already
#: within MAX_OCCURRENCES; beyond that a caller is scanning, not rendering.
MAX_WINDOW_DAYS = 400


def attach_recurrence(event: EventModel) -> EventModel:
    """Set the nested `recurrence` the response schema expects on an event row.

    Only the instance changes; `skipped_dates` is left as stored ISO strings, since
    assigning dates to the JSON column would fail at the next commit.

    Args:
        event: The event row.

    Returns:
        The same row, with `recurrence` attached.
    """
    event.recurrence = recurrence_of(event)

    # Deliberately *not* parsed onto the instance. `skipped_dates` is a real JSON
    # column, and assigning date objects to it marks the row dirty with values
    # json.dumps cannot serialize -- so the next commit on that session dies with
    # "Object of type date is not JSON serializable". Editing an event that had a
    # cancelled date did exactly that. The column holds ISO strings and the schema
    # declares list[date], so Pydantic converts them on the way out instead.
    return event


def parse_date(value) -> date:
    """Return a date from a stored ISO string, passing a date through unchanged.

    Args:
        value: A `date`, or an ISO YYYY-MM-DD string.

    Returns:
        The value as a `date`.
    """
    return value if isinstance(value, date) else date.fromisoformat(value)


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    """Return whether a user row with this id exists.

    Args:
        db: Open database session.
        user_id: Id to look up.

    Returns:
        True when the user row exists.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
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


def get_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> EventModel | None:
    """Return one of the user's events with its recurrence attached, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        event_id: The event to fetch.

    Returns:
        The event with `recurrence` set, or None when it is missing or another user's.
    """
    event = (
        db.query(EventModel)
        .filter(EventModel.id == event_id, EventModel.user_id == user_id)
        .first()
    )
    return None if event is None else attach_recurrence(event)


def list_events(db: Session, user_id: uuid.UUID, course_id: uuid.UUID | None = None):
    """Return the user's event rows, by start date and time.

    Args:
        db: Open database session.
        user_id: Whose events.
        course_id: Only events of this course; None for all.

    Returns:
        The rows with recurrence attached; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(EventModel).filter(EventModel.user_id == user_id)
    if course_id is not None:
        query = query.filter(EventModel.course_id == course_id)

    events = query.order_by(EventModel.starts_on, EventModel.start_time).all()
    return [attach_recurrence(event) for event in events]


def create_event(db: Session, user_id: uuid.UUID, data: EventCreate):
    """Create an event for the user, one-off or repeating.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose event.
        data: The event; its title is stripped and its skipped dates
            de-duplicated.

    Returns:
        The new row with recurrence attached; None when the user does not exist.

    Raises:
        ValueError: If `course_id` is not one of the user's courses.
    """
    if not user_exists(db, user_id):
        return None

    # A course id from another account would otherwise attach this user's event
    # to someone else's course, which is how the cross-tenant category bug
    # (audit #7) worked.
    if data.course_id is not None and owned_course(db, user_id, data.course_id) is None:
        raise ValueError("Course not found")

    event = EventModel(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=data.course_id,
        title=data.title.strip(),
        kind=data.kind.value,
        location=data.location,
        notes=data.notes,
        starts_on=data.starts_on,
        start_time=data.start_time,
        end_time=data.end_time,
        # Blocked at setup, rather than only by cancelling occurrences one at a
        # time afterwards: a class you already know does not run on the 14th
        # should never have appeared on the 14th.
        skipped_dates=sorted({day.isoformat() for day in (data.skipped_dates or [])}),
    )
    apply_recurrence(event, data.recurrence)

    db.add(event)
    db.commit()
    db.refresh(event)
    return attach_recurrence(event)


def update_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, data: EventUpdate):
    """Change the fields sent on one of the user's events.

    The start and end times, and the repeat's end against the start, are checked
    once the patch is merged. Commits.

    Args:
        db: Open database session.
        user_id: Whose event.
        event_id: The event.
        data: The fields to change; a null `recurrence` makes it a one-off.

    Returns:
        The updated row with recurrence attached; None when it is not the user's.

    Raises:
        ValueError: If a new `course_id` is not one of the user's courses, the
            event would end at or before it starts, or the repeat would end
            before `starts_on`.
    """
    event = get_event(db, user_id, event_id)
    if event is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    recurrence_given = "recurrence" in update_data
    update_data.pop("recurrence", None)

    if update_data.get("course_id") is not None:
        if owned_course(db, user_id, update_data["course_id"]) is None:
            raise ValueError("Course not found")

    if "kind" in update_data and update_data["kind"] is not None:
        update_data["kind"] = update_data["kind"].value

    if "title" in update_data and update_data["title"] is not None:
        update_data["title"] = update_data["title"].strip()

    # skipped_dates is a JSON column, so date objects cannot go into it -- that
    # exact assignment once made editing any event with a cancelled date fail
    # with "Object of type date is not JSON serializable". Serialised here, and
    # rewritten whole rather than appended to, since SQLAlchemy does not track
    # mutation inside a JSON value.
    if "skipped_dates" in update_data:
        blocked = update_data.pop("skipped_dates") or []
        event.skipped_dates = sorted({day.isoformat() for day in blocked})

    for key, value in update_data.items():
        setattr(event, key, value)

    # A partial update can move the start past the repeat's end, or shorten a
    # meeting from the other side, so the pair is only checkable once both have
    # landed.
    if event.start_time is not None and event.end_time is not None:
        if event.end_time <= event.start_time:
            raise ValueError("An event cannot end before it starts")

    if recurrence_given:
        apply_recurrence(event, data.recurrence)

    if event.recur_until is not None and event.recur_until < event.starts_on:
        raise ValueError("A repeat cannot end before the event starts")

    db.commit()
    db.refresh(event)
    return attach_recurrence(event)


def delete_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID):
    """Delete one of the user's events, the whole series if it repeats.

    Its members and invite links go with it. Commits.

    Args:
        db: Open database session.
        user_id: Whose event.
        event_id: The event.

    Returns:
        A copy of the deleted event; None when it is not the user's.
    """
    event = get_event(db, user_id, event_id)
    if event is None:
        return None

    # A detached copy taken before the delete: attach_recurrence has already
    # marked the instance dirty, and SQLAlchemy would then flush an UPDATE for a
    # row that is gone (StaleDataError -- the same trap the grades and money
    # modules each hit once).
    snapshot = EventSchema.model_validate(event)
    db.delete(event)
    db.commit()
    return snapshot


def skip_occurrence(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, on_date: date):
    """Cancel one date of a repeating event without ending the series.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose event.
        event_id: The series.
        on_date: The date to cancel.

    Returns:
        The event with the date added to `skipped_dates`; None when it is not the
        user's.

    Raises:
        ValueError: If the event does not repeat (delete it instead).
    """
    event = get_event(db, user_id, event_id)
    if event is None:
        return None

    if not rule_of(event).repeats:
        raise ValueError("This event happens once; delete it instead")

    skipped = {parse_date(value) for value in (event.skipped_dates or [])}
    skipped.add(on_date)
    # Rewritten whole rather than appended to: SQLAlchemy does not track
    # mutation inside a JSON column, so an in-place append never reaches the
    # database.
    event.skipped_dates = sorted(day.isoformat() for day in skipped)

    db.commit()
    db.refresh(event)
    return attach_recurrence(event)


def restore_occurrence(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, on_date: date):
    """Undo a skip, putting one cancelled date of a series back.

    Restoring a date that was never skipped changes nothing. Commits.

    Args:
        db: Open database session.
        user_id: Whose event.
        event_id: The series.
        on_date: The date to restore.

    Returns:
        The event; None when it is not the user's.
    """
    event = get_event(db, user_id, event_id)
    if event is None:
        return None

    skipped = {parse_date(value) for value in (event.skipped_dates or [])}
    skipped.discard(on_date)
    event.skipped_dates = sorted(day.isoformat() for day in skipped)

    db.commit()
    db.refresh(event)
    return attach_recurrence(event)


def list_occurrences(
    db: Session,
    user_id: uuid.UUID,
    window_start: date,
    window_end: date,
) -> list[EventOccurrence] | None:
    """Return every date every one of the user's events falls on in a window.

    Skipped dates are left out, and term blackouts are left out of every event that
    belongs to a course. Two queries however many series there are.

    Args:
        db: Open database session.
        user_id: Whose events.
        window_start: First date, inclusive.
        window_end: Last date, inclusive.

    Returns:
        The occurrences by date, all-day items first within a day, then by start
        time; None when the user does not exist.

    Raises:
        ValueError: If the window ends before it starts or spans more than
            `MAX_WINDOW_DAYS` days.
    """
    if not user_exists(db, user_id):
        return None

    if window_end < window_start:
        raise ValueError("The window ends before it starts")

    if (window_end - window_start).days > MAX_WINDOW_DAYS:
        raise ValueError(f"A window cannot be longer than {MAX_WINDOW_DAYS} days")

    events = (
        db.query(EventModel)
        .filter(
            EventModel.user_id == user_id,
            # Nothing that starts after the window can occur inside it, whatever
            # its rule. The other end cannot be filtered in SQL: a weekly event
            # from September is still running in March.
            EventModel.starts_on <= window_end,
        )
        .all()
    )

    codes = course_codes(db, user_id)
    # Term blackouts -- a reading break, a stat holiday -- subtracted from
    # anything belonging to a course. Deliberately not from everything that
    # repeats: this same engine drives recurring payments and repeating tasks,
    # and rent is still due during reading break.
    blackouts = blackout_dates(db, user_id)
    materialised: list[EventOccurrence] = []

    for event in events:
        skipped = [parse_date(value) for value in (event.skipped_dates or [])]
        if event.course_id is not None and blackouts:
            # The engine already takes a set of dates to skip, so a blackout
            # needs no concept of its own down there.
            skipped = list(set(skipped) | blackouts)
        rule = rule_of(event)
        for on_date in occurrences(rule, event.starts_on, window_start, window_end, skipped):
            materialised.append(
                EventOccurrence(
                    event_id=event.id,
                    on_date=on_date,
                    title=event.title,
                    kind=event.kind,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    location=event.location,
                    notes=event.notes,
                    course_id=event.course_id,
                    course_code=codes.get(event.course_id),
                    job_id=event.job_id,
                    repeats=rule.repeats,
                    grade_id=event.grade_id,
                )
            )

    # All-day items first within a date, then by clock time, so a day column
    # reads top to bottom the way the day runs.
    materialised.sort(key=lambda item: (item.on_date, item.start_time is not None, item.start_time))
    return materialised


def course_codes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Return the user's course ids mapped to their codes, in one query.

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
