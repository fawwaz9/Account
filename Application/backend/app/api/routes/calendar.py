"""Calendar routes under /api/calendar: events, timetables, blackouts and the load.

Each handler parses the request, calls one Calendar service and maps its result
to a status: a service ValueError is a 400, a None is a 404.
"""

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
from app.Usage.services.usage_service import CREATE, record as record_usage

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
    """List every date every event falls on between two dates.

    Repeating events are expanded here, never stored per date. Tasks with due dates
    are fetched separately and merged by the client.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The occurrences by date, all-day items first, then by start time.

    Raises:
        HTTPException: 400 if the window is inverted or longer than 400 days; 404
            if the user does not exist.
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
    """List the caller's stored events: one per series, not one per date.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        course_id: Only this course's events; omit for all.

    Returns:
        The events, by start date and time.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    events = list_events(db, user_id, course_id)
    if events is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return events


@router.post("/{user_id}/events", response_model=Event, responses=responses["user_both"])
def add_event(user_id: VerifiedUserId, event: EventCreate, db: DBSession):
    """Create an event, one-off or repeating.

    Args:
        user_id: The verified caller's id.
        event: The event to create.
        db: Request-scoped database session.

    Returns:
        The created event.

    Raises:
        HTTPException: 400 if `course_id` is not one of the caller's courses; 404
            if the user does not exist.
    """
    try:
        created = create_event(db, user_id, event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, "calendar")
    return created


@router.get("/{user_id}/events/{event_id}", response_model=Event, responses=EVENT_404)
def get_single_event(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    """Get one of the caller's events.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.

    Returns:
        The event, with its repeat rule.

    Raises:
        HTTPException: 404 if the event is missing or not the caller's.
    """
    event = get_event(db, user_id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@router.patch("/{user_id}/events/{event_id}", response_model=Event, responses=EVENT_BOTH)
def edit_event(user_id: VerifiedUserId, event_id: UUID, event: EventUpdate, db: DBSession):
    """Change the fields sent on one of the caller's events.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        event: The fields to change; a null `recurrence` makes it a one-off.
        db: Request-scoped database session.

    Returns:
        The updated event.

    Raises:
        HTTPException: 400 if the course is not the caller's, the event would end
            at or before it starts, or the repeat would end before it starts; 404
            if the event is missing or not the caller's.
    """
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
    """Delete a whole series, or cancel just one date of it.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.
        on_date: Cancel only this occurrence; omit to delete the whole series.

    Returns:
        With `on_date`, the event with that date skipped; otherwise a copy of the
        deleted event.

    Raises:
        HTTPException: 400 if `on_date` is given for an event that does not repeat;
            404 if the event is missing or not the caller's.
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
    """Put back one cancelled date of a repeating event.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.
        on_date: The cancelled date to restore.

    Returns:
        The event, with the date no longer skipped.

    Raises:
        HTTPException: 404 if the event is missing or not the caller's.
    """
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
    """Get a course's timetable: its lecture, lab and discussion events.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The class events, by start time.

    Raises:
        HTTPException: 404 if the course is missing or not the caller's.
    """
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
    """Replace a course's timetable with the meetings given.

    PUT because it is the whole timetable: sending it twice leaves one timetable.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        schedule: The meetings and, optionally, the term dates.
        db: Request-scoped database session.

    Returns:
        The new class events.

    Raises:
        HTTPException: 400 if the term dates are missing or inverted, or a first
            meeting falls outside the term; 404 if the course is missing or not
            the caller's.
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
    """List the gaps between the caller's commitments, longest first, in study hours.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The free blocks; days already past, and the part of today already gone,
        are left out.

    Raises:
        HTTPException: 400 if the window is inverted or longer than 400 days; 404
            if the user does not exist.
    """
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
    """Get what a window costs in hours, with booked and estimated time apart.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The window's load.

    Raises:
        HTTPException: 400 if the window is inverted or longer than 400 days; 404
            if the user does not exist.
    """
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
    """Get how exams, deadlines and due tasks spread across the weeks of a window.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        Every Monday-to-Sunday week the window touches, with the heaviest weight.

    Raises:
        HTTPException: 400 if the window is inverted or longer than 400 days; 404
            if the user does not exist.
    """
    try:
        strip = crunch(db, user_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if strip is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return strip


@router.get("/{user_id}/blackouts", response_model=list[TermBlackout], responses=responses["user_404"])
def get_blackouts(user_id: VerifiedUserId, db: DBSession):
    """List the caller's term blackouts, the breaks when classes do not run.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The blackouts, earliest first.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    rows = list_blackouts(db, user_id)
    if rows is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return rows


@router.post("/{user_id}/blackouts", response_model=TermBlackout, status_code=201, responses=responses["user_both"])
def add_blackout(user_id: VerifiedUserId, data: TermBlackoutCreate, db: DBSession):
    """Add a term blackout; class events of every course skip its dates.

    Args:
        user_id: The verified caller's id.
        data: The label and the inclusive date range.
        db: Request-scoped database session.

    Returns:
        The created blackout, with a 201.

    Raises:
        HTTPException: 400 if the range is longer than 120 days; 404 if the user
            does not exist.
    """
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
    """Change the fields sent on one of the caller's blackouts.

    Args:
        user_id: The verified caller's id.
        blackout_id: The blackout.
        data: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated blackout.

    Raises:
        HTTPException: 400 if the range would be inverted or longer than 120 days;
            404 if the blackout is missing or not the caller's.
    """
    try:
        row = update_blackout(db, user_id, blackout_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Blocked period not found")
    return row


@router.delete("/{user_id}/blackouts/{blackout_id}", status_code=204, responses=responses["user_404"])
def remove_blackout(user_id: VerifiedUserId, blackout_id: UUID, db: DBSession):
    """Delete one of the caller's blackouts.

    Args:
        user_id: The verified caller's id.
        blackout_id: The blackout.
        db: Request-scoped database session.

    Returns:
        Nothing, with a 204.

    Raises:
        HTTPException: 404 if the blackout is missing or not the caller's.
    """
    if delete_blackout(db, user_id, blackout_id) is None:
        raise HTTPException(status_code=404, detail="Blocked period not found")
    return None
