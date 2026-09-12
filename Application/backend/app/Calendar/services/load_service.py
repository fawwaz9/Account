"""When you actually have time, and when the term lands on you.

Three readings of one window, all derived from data already stored: no new
tables, no writes. They share a single list_occurrences call because they are
really one question -- what does this week cost and where is the room -- asked
three ways.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import UserModel

from app.Calendar.schemas.event import EventKind
from app.Calendar.schemas.load import CrunchStrip, CrunchWeek, FreeBlock, WeekLoad
from app.Calendar.services.event_service import list_occurrences
from app.Tasks.services.task_service import list_tasks
from app.Users.services.user_service import get_preferences

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
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def study_window(db: Session, user_id: uuid.UUID) -> tuple[time, time, int]:
    """The hours worth offering as free, and the shortest gap worth offering."""
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
    """The day's timed commitments, merged, earliest first.

    Merged because two classes can overlap -- the week view exists partly to show
    that they do -- and treating them as separate spans would invent a gap
    between the end of the first and the start of the second that never existed.

    All-day items are skipped: they occupy no position on a clock, so they block
    no hour of it.
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
    """The gaps between a day's commitments, longest first.

    Clipped to the study window at both ends, so a 07:00 lab does not open a
    block at midnight and an evening with nothing in it stops at the hour you
    said you stop.

    Time already gone is not free time. Days before today are skipped entirely,
    and today's blocks start no earlier than the current hour -- offering
    "08:00-16:00" at two in the afternoon is offering six hours that no longer
    exist.
    """
    occurrences = list_occurrences(db, user_id, window_start, window_end)
    if occurrences is None:
        return None

    now = now or datetime.now()
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
    """What the window costs in hours, booked and estimated kept apart."""
    occurrences = list_occurrences(db, user_id, window_start, window_end)
    if occurrences is None:
        return None

    booked = 0
    events = 0
    for item in occurrences:
        events += 1
        if item.start_time is None:
            continue
        end = item.end_time or item.start_time
        booked += max(0, minutes_between(item.start_time, end))

    tasks = list_tasks(db, user_id, start=window_start, end=window_end) or []
    estimated = sum(task.estimated_minutes or 0 for task in tasks)
    unestimated = sum(1 for task in tasks if not task.estimated_minutes)

    return WeekLoad(
        starts_on=window_start,
        ends_on=window_end,
        booked_minutes=booked,
        estimated_minutes=estimated,
        task_count=len(tasks),
        unestimated_tasks=unestimated,
        event_count=events,
    )


def week_of(day: date) -> date:
    """The Monday of a day's week, so weeks group consistently."""
    return day - timedelta(days=day.weekday())


def crunch(
    db: Session, user_id: uuid.UUID, window_start: date, window_end: date,
    today: date | None = None,
) -> CrunchStrip | None:
    """How the term's weight is spread across its weeks.

    Every week in the range appears, including the empty ones -- a strip with
    gaps in it would read as missing data rather than as a quiet fortnight.
    """
    occurrences = list_occurrences(db, user_id, window_start, window_end)
    if occurrences is None:
        return None

    today = today or date.today()
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
