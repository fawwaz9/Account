"""Events, and the dates they land on.

Storage is one row per event, however often it repeats. Everything that reads a
week or a month goes through `list_occurrences`, which expands the rules in
memory for exactly the window asked for.
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
    """Expose the rule columns as the nested object the schema declares.

    Set on the instance rather than as a model property for the same reason the
    grades module does it: models.py is imported by this service, so a property
    reaching back into it would be a circular import.
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
    return value if isinstance(value, date) else date.fromisoformat(value)


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def get_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> EventModel | None:
    event = (
        db.query(EventModel)
        .filter(EventModel.id == event_id, EventModel.user_id == user_id)
        .first()
    )
    return None if event is None else attach_recurrence(event)


def list_events(db: Session, user_id: uuid.UUID, course_id: uuid.UUID | None = None):
    if not user_exists(db, user_id):
        return None

    query = db.query(EventModel).filter(EventModel.user_id == user_id)
    if course_id is not None:
        query = query.filter(EventModel.course_id == course_id)

    events = query.order_by(EventModel.starts_on, EventModel.start_time).all()
    return [attach_recurrence(event) for event in events]


def create_event(db: Session, user_id: uuid.UUID, data: EventCreate):
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
    """Cancel one date of a series without ending the series.

    Deleting the event is the only other option, and "no lecture next Monday"
    must not mean "no lectures ever again".
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
    """Undo a skip."""
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
    """Every date every event falls on in the window, in order.

    One query for the events, one for the course codes, then pure arithmetic --
    so a month costs two round trips however many series it contains.
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
    """course id -> code, in one query rather than one per event."""
    rows = (
        db.query(CourseModel.id, CourseModel.code)
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    return {row.id: row.code for row in rows}
