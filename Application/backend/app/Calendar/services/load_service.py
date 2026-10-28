"""Service functions for the week's load: free time, hours committed, and crunch.

Three readings of one window, all derived from stored events and tasks with no
writes: the gaps between commitments, the hours those commitments and the tasks
due come to, and how exams and deadlines spread across the weeks of a term.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import UserModel

from app.Calendar.schemas.event import CLASS_KINDS, EventKind

#: Lecture, lab, discussion, as stored values.
CLASS_KIND_VALUES = {kind.value for kind in CLASS_KINDS}
from app.Calendar.schemas.load import CrunchStrip, CrunchWeek, FreeBlock, WeekLoad
from app.Calendar.services.event_service import list_occurrences
from app.Tasks.services.task_service import list_tasks
from app.Tasks.services.estimates_service import estimate_ratio
from app.Users.services.user_service import get_preferences
from app.shared.dates import user_now, user_today

#: How heavily each kind of dated thing lands on a week.
#:
#: A final outweighs a midterm outweighs a deadline, because one exam really can
#: outweigh three assignments and a straight count would show a week holding two
#: finals as lighter than a week holding three quizzes. Classes carry no weight:
#: they are the background the term runs against, not the thing that stacks up.
CRUNCH_WEIGHTS: dict[str, int] = {
    EventKind.FINAL.value: 5,
    EventKind.MIDTERM.value: 3,
    EventKind.DEADLINE.value: 1,
}

#: A task with a due date lands like a deadline, because that is what it is.
TASK_WEIGHT = 1


def minutes_between(start: time, end: time) -> int:
    """Return the minutes between two clock times; negative when `end` is earlier.

    Args:
        start: Earlier clock time.
        end: Later clock time.

    Returns:
        Whole minutes from `start` to `end`, ignoring seconds.
    """
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def study_window(db: Session, user_id: uuid.UUID) -> tuple[time, time, int]:
    """Return the hours worth offering as free, and the shortest gap worth offering.

    Args:
        db: Open database session.
        user_id: Whose preferences to read.

    Returns:
        The study day's start and end (local times) and the minimum free block in
        minutes; 08:00, 22:00 and 30 when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return time(8, 0), time(22, 0), 30
    preferences = get_preferences(user)
    return (
        preferences.study_day_start,
        preferences.study_day_end,
        preferences.min_free_block_minutes,
    )


def busy_spans(occurrences, on_date: date) -> list[tuple[time, time]]:
    """Return one day's timed commitments as merged spans, earliest first.

    Overlapping events merge so no gap is invented between them; all-day items
    block nothing, and an event with no end (or an end before its start) occupies
    only its start.

    Args:
        occurrences: Expanded occurrences, any dates.
        on_date: The day to read.

    Returns:
        Merged (start, end) local times.
    """
    spans = []
    for item in occurrences:
        if item.on_date != on_date or item.start_time is None:
            continue
        # An event with no end still occupies its start; treating it as
        # zero-length would let something be scheduled on top of it.
        end = item.end_time or item.start_time
        if minutes_between(item.start_time, end) <= 0:
            end = item.start_time
        spans.append((item.start_time, end))

    spans.sort()
    merged: list[tuple[time, time]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def free_blocks(
    db: Session, user_id: uuid.UUID, window_start: date, window_end: date,
    now: datetime | None = None,
) -> list[FreeBlock] | None:
    """Return the gaps between the user's commitments in a window, longest first.

    Gaps are clipped to the user's study window; days before today are skipped and
    today's gaps start no earlier than now, all on the user's clock. Only gaps of at
    least the user's minimum length are offered.

    Args:
        db: Open database session.
        user_id: Whose calendar.
        window_start: First day, inclusive.
        window_end: Last day, inclusive.
        now: The local moment to treat as now, naive; defaults to the user's now.

    Returns:
        The free blocks, longest first, then by date and start; None when the
        user does not exist.

    Raises:
        ValueError: If the window is inverted or longer than the calendar allows.
    """
    occurrences = list_occurrences(db, user_id, window_start, window_end)
    if occurrences is None:
        return None

    # The student's clock, not the server's. This line was `datetime.now()`,
    # which on Cloud Run is UTC -- so after 18:00 in Regina `today` was
    # already tomorrow and the day the client asked about was skipped as past,
    # leaving no free time for the rest of every evening. The window's hours
    # came from preferences all along, which is what made it read as
    # inconsistent rather than simply wrong.
    now = now or user_now(db, user_id)
    today = now.date()
    day_start, day_end, floor = study_window(db, user_id)
    blocks: list[FreeBlock] = []

    day = window_start
    while day <= window_end:
        if day < today:
            day += timedelta(days=1)
            continue

        cursor = day_start
        if day == today:
            # Clipped to the actual time, not rounded up to the next hour: an
            # odd-looking "14:37" is honest, and rounding would both discard up
            # to an hour of real time and need a special case near midnight.
            cursor = max(cursor, now.time().replace(second=0, microsecond=0))
        for start, end in busy_spans(occurrences, day):
            # Entirely before the window, or entirely after it.
            if end <= cursor:
                continue
            if start >= day_end:
                break
            if start > cursor:
                gap = minutes_between(cursor, min(start, day_end))
                if gap >= floor:
                    blocks.append(FreeBlock(
                        on_date=day, starts_at=cursor,
                        ends_at=min(start, day_end), minutes=gap,
                    ))
            cursor = max(cursor, end)

        if cursor < day_end:
            gap = minutes_between(cursor, day_end)
            if gap >= floor:
                blocks.append(FreeBlock(
                    on_date=day, starts_at=cursor, ends_at=day_end, minutes=gap,
                ))

        day += timedelta(days=1)

    blocks.sort(key=lambda block: (-block.minutes, block.on_date, block.starts_at))
    return blocks


def week_load(
    db: Session, user_id: uuid.UUID, window_start: date, window_end: date
) -> WeekLoad | None:
    """Return what a window costs in hours, with booked and estimated time apart.

    Booked time is every timed event occurrence, split into work and classes;
    estimated time is the estimates on open, unsnoozed tasks due in the window,
    scaled by the user's actual-to-estimate ratio when they apply it.

    Args:
        db: Open database session.
        user_id: Whose calendar and tasks.
        window_start: First day, inclusive.
        window_end: Last day, inclusive.

    Returns:
        The window's load; None when the user does not exist.

    Raises:
        ValueError: If the window is inverted or longer than the calendar allows.
    """
    occurrences = list_occurrences(db, user_id, window_start, window_end)
    if occurrences is None:
        return None

    booked = 0
    work = 0
    classes = 0
    events = 0
    for item in occurrences:
        events += 1
        if item.start_time is None:
            continue
        end = item.end_time or item.start_time
        minutes = max(0, minutes_between(item.start_time, end))
        booked += minutes
        if item.kind == EventKind.SHIFT.value:
            work += minutes
        elif item.kind in CLASS_KIND_VALUES:
            classes += minutes

    tasks = list_tasks(db, user_id, start=window_start, end=window_end) or []
    typed = sum(task.estimated_minutes or 0 for task in tasks)
    unestimated = sum(1 for task in tasks if not task.estimated_minutes)
    # Phase 1 D36: scaled by how long tasks really take, when asked for. The
    # typed total goes alongside, so the forecast can say what it did.
    ratio = estimate_ratio(db, user_id)
    applied = ratio.ratio if ratio.applied else None
    estimated = round(typed * applied) if applied else typed

    return WeekLoad(
        starts_on=window_start,
        ends_on=window_end,
        booked_minutes=booked,
        work_minutes=work,
        class_minutes=classes,
        estimated_minutes=estimated,
        typed_estimated_minutes=typed,
        estimate_ratio=applied,
        task_count=len(tasks),
        unestimated_tasks=unestimated,
        event_count=events,
    )


def week_of(day: date) -> date:
    """Return the Monday of the week a day falls in.

    Args:
        day: Any date.

    Returns:
        The Monday on or before `day`.
    """
    return day - timedelta(days=day.weekday())


def crunch(
    db: Session, user_id: uuid.UUID, window_start: date, window_end: date,
    today: date | None = None,
) -> CrunchStrip | None:
    """Return how heavily exams, deadlines and due tasks land on each week of a window.

    Every Monday-to-Sunday week the window touches appears, empty ones included.
    Finals weigh 5, midterms 3, deadline events and open tasks due 1; classes and
    shifts weigh nothing.

    Args:
        db: Open database session.
        user_id: Whose calendar and tasks.
        window_start: First day, inclusive.
        window_end: Last day, inclusive.
        today: The day that marks the current week; defaults to the user's today.

    Returns:
        The weeks, earliest first, with the heaviest week's weight; None when the
        user does not exist.

    Raises:
        ValueError: If the window is inverted or longer than the calendar allows.
    """
    occurrences = list_occurrences(db, user_id, window_start, window_end)
    if occurrences is None:
        return None

    today = today or user_today(db, user_id)
    weeks: dict[date, CrunchWeek] = {}

    cursor = week_of(window_start)
    last = week_of(window_end)
    while cursor <= last:
        weeks[cursor] = CrunchWeek(starts_on=cursor, is_current=cursor == week_of(today))
        cursor += timedelta(weeks=1)

    for item in occurrences:
        week = weeks.get(week_of(item.on_date))
        if week is None:
            continue
        weight = CRUNCH_WEIGHTS.get(item.kind, 0)
        if weight == 0:
            continue
        week.weight += weight
        if item.kind in (EventKind.FINAL.value, EventKind.MIDTERM.value):
            week.exams += 1
        else:
            week.deadlines += 1

    for task in list_tasks(db, user_id, start=window_start, end=window_end) or []:
        week = weeks.get(week_of(task.due_date))
        if week is None:
            continue
        week.weight += TASK_WEIGHT
        week.tasks += 1

    ordered = [weeks[key] for key in sorted(weeks)]
    return CrunchStrip(
        weeks=ordered,
        peak=max((week.weight for week in ordered), default=0),
    )
