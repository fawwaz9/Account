from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Calendar.schemas.event import (
    ClassScheduleCreate,
    Event,
    EventCreate,
    EventOccurrence,
    EventUpdate,
)
from app.Calendar.services.class_schedule_service import (
    get_class_schedule,
    set_class_schedule,
)
from app.Calendar.services.event_service import (
    create_event,
    delete_event,
    get_event,
    list_events,
    list_occurrences,
    restore_occurrence,
    skip_occurrence,
    update_event,
)
from app.Calendar.schemas.blackout import (
    TermBlackout,
    TermBlackoutCreate,
    TermBlackoutUpdate,
)
from app.Calendar.services.blackout_service import (
    create_blackout,
    delete_blackout,
    list_blackouts,
    update_blackout,
)
from app.Calendar.schemas.load import CrunchStrip, FreeBlock, WeekLoad
from app.Calendar.services.load_service import crunch, free_blocks, week_load
from app.shared import audit
from app.shared.errors import error_course, error_user, responses

router = APIRouter()

EVENT_404 = {404: {"description": "Event not found"}}
EVENT_BOTH = {**EVENT_404, 400: {"description": "Invalid event data"}}


@router.get("/{user_id}/agenda", response_model=list[EventOccurrence], responses=responses["user_both"])
def agenda(
    user_id: VerifiedUserId,
    db: DBSession,
    start: date = Query(..., description="First date of the window, inclusive"),
    end: date = Query(..., description="Last date of the window, inclusive"),
):
    """Every date every event falls on between `start` and `end`.

    Repeats are expanded here rather than stored, so this is the only endpoint
    that knows how often something happens. Tasks with due dates are fetched
    separately and merged by the client -- a deadline is one record, kept where
    it is edited.
    """
    try:
        occurrences = list_occurrences(db, user_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if occurrences is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return occurrences


@router.get("/{user_id}/events", response_model=list[Event], responses=responses["user_404"])
def get_events(user_id: VerifiedUserId, db: DBSession, course_id: UUID | None = None):
    """The stored events themselves -- one row per series, not per occurrence."""
    events = list_events(db, user_id, course_id)
    if events is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return events


@router.post("/{user_id}/events", response_model=Event, responses=responses["user_both"])
def add_event(user_id: VerifiedUserId, event: EventCreate, db: DBSession):
    try:
        created = create_event(db, user_id, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.get("/{user_id}/events/{event_id}", response_model=Event, responses=EVENT_404)
def get_single_event(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    event = get_event(db, user_id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@router.patch("/{user_id}/events/{event_id}", response_model=Event, responses=EVENT_BOTH)
def edit_event(user_id: VerifiedUserId, event_id: UUID, event: EventUpdate, db: DBSession):
    try:
        updated = update_event(db, user_id, event_id, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return updated


@router.delete("/{user_id}/events/{event_id}", response_model=Event, responses=EVENT_BOTH)
def remove_event(
    user_id: VerifiedUserId,
    event_id: UUID,
    db: DBSession,
    on_date: date | None = Query(
        default=None,
        description="Cancel just this occurrence. Omit to delete the whole series.",
    ),
):
    """Delete a series, or cancel one date of it.

    "No lecture next Monday" and "no lectures ever again" are different
    instructions, and without `on_date` the second is the only one expressible.
    """
    if on_date is not None:
        try:
            event = skip_occurrence(db, user_id, event_id, on_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")

        return event

    deleted = delete_event(db, user_id, event_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Event not found")

    audit.deletion("event", user_id=user_id, target_id=event_id, detail=deleted.title)
    return deleted


@router.post("/{user_id}/events/{event_id}/restore", response_model=Event, responses=EVENT_404)
def restore_event_occurrence(
    user_id: VerifiedUserId,
    event_id: UUID,
    db: DBSession,
    on_date: date = Query(..., description="The cancelled date to put back"),
):
    event = restore_occurrence(db, user_id, event_id, on_date)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@router.get(
    "/{user_id}/courses/{course_id}/class-schedule",
    response_model=list[Event],
    responses=responses["course_404"],
)
def course_class_schedule(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    schedule = get_class_schedule(db, user_id, course_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return schedule


@router.put(
    "/{user_id}/courses/{course_id}/class-schedule",
    response_model=list[Event],
    responses=responses["course_both"],
)
def set_course_class_schedule(
    user_id: VerifiedUserId,
    course_id: UUID,
    schedule: ClassScheduleCreate,
    db: DBSession,
):
    """Put a course's class times on the calendar, replacing any already there.

    PUT rather than POST because it is the course's whole timetable: sending it
    twice leaves one timetable, not two overlapping copies.
    """
    try:
        events = set_class_schedule(db, user_id, course_id, schedule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if events is None:
        raise HTTPException(status_code=404, detail=error_course["not_found"])

    return events


@router.get("/{user_id}/free-blocks", response_model=list[FreeBlock], responses=responses["user_both"])
def get_free_blocks(
    user_id: VerifiedUserId,
    db: DBSession,
    start: date = Query(..., description="First date of the window, inclusive"),
    end: date = Query(..., description="Last date of the window, inclusive"),
):
    """The gaps between commitments, longest first, inside your study hours."""
    try:
        blocks = free_blocks(db, user_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if blocks is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return blocks


@router.get("/{user_id}/week-load", response_model=WeekLoad, responses=responses["user_both"])
def get_week_load(
    user_id: VerifiedUserId,
    db: DBSession,
    start: date = Query(..., description="First date of the window, inclusive"),
    end: date = Query(..., description="Last date of the window, inclusive"),
):
    """What the window costs in hours, booked and estimated kept apart."""
    try:
        load = week_load(db, user_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if load is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return load


@router.get("/{user_id}/crunch", response_model=CrunchStrip, responses=responses["user_both"])
def get_crunch(
    user_id: VerifiedUserId,
    db: DBSession,
    start: date = Query(..., description="First date of the window, inclusive"),
    end: date = Query(..., description="Last date of the window, inclusive"),
):
    """How the term's weight is spread across its weeks."""
    try:
        strip = crunch(db, user_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if strip is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return strip


@router.get("/{user_id}/blackouts", response_model=list[TermBlackout], responses=responses["user_404"])
def get_blackouts(user_id: VerifiedUserId, db: DBSession):
    """Stretches of term when classes do not run."""
    rows = list_blackouts(db, user_id)
    if rows is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return rows


@router.post("/{user_id}/blackouts", response_model=TermBlackout, status_code=201, responses=responses["user_both"])
def add_blackout(user_id: VerifiedUserId, data: TermBlackoutCreate, db: DBSession):
    try:
        row = create_blackout(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return row


@router.patch("/{user_id}/blackouts/{blackout_id}", response_model=TermBlackout, responses=responses["user_both"])
def edit_blackout(
    user_id: VerifiedUserId, blackout_id: UUID, data: TermBlackoutUpdate, db: DBSession
):
    try:
        row = update_blackout(db, user_id, blackout_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Blocked period not found")
    return row


@router.delete("/{user_id}/blackouts/{blackout_id}", status_code=204, responses=responses["user_404"])
def remove_blackout(user_id: VerifiedUserId, blackout_id: UUID, db: DBSession):
    if delete_blackout(db, user_id, blackout_id) is None:
        raise HTTPException(status_code=404, detail="Blocked period not found")
    return None
