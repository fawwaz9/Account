"""The weekly planner: constraint scheduling over free blocks (Phase 4 item 2, §4).

Tasks due in the next week (and any overdue) are sorted by due date, then
priority, and placed greedily into the free blocks the calendar already finds
(inside the study window, never over an event). Each placement says why. A task
that doesn't fit before it is due is listed with the shortfall rather than
squeezed in. An LLM would be slower, pricier and occasionally schedule study at
3am (§4); this can't.

A proposal stores nothing. Accepting writes ordinary personal events marked
`source = "planner"` (D7), each re-checked against the calendar as it stands, so
a block can never land on something booked since the proposal was made.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import EventModel, TaskModel, UserModel
from app.Calendar.schemas.planner import AcceptedPlan, AcceptPlan, PlannedBlock, Unplaced, WeekPlan
from app.Calendar.services.event_service import course_codes
from app.Calendar.services.load_service import free_blocks
from app.Tasks.services.estimates_service import estimate_ratio
from app.Users.services.user_service import get_preferences
from app.shared.dates import user_now

#: Days planned, today included.
HORIZON_DAYS = 7
#: Minutes given to a task with no estimate.
DEFAULT_MINUTES = 60
#: The longest single block: past two hours a block becomes a marathon.
MAX_CHUNK = 120
#: The least time left on a task worth planning; less is "nearly done".
MIN_REMAINING = 15
#: A break before more of the same task in the same free stretch, so two blocks
#: never make one marathon.
BREAK_MINUTES = 15
#: Marks the planner's events (D7).
SOURCE = "planner"


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _day(on: date, today: date) -> str:
    if on == today:
        return "today"
    if on == today + timedelta(days=1):
        return "tomorrow"
    return on.strftime("%A")


def _hours(minutes: int) -> str:
    """A limit in words: "4 hours", "1.5 hours", "1 hour"."""
    hours = minutes / 60
    shown = f"{hours:g}" if hours * 2 == int(hours * 2) else f"{hours:.1f}"
    return f"{shown} hour{'' if hours == 1 else 's'}"


def needed_minutes(task, ratio: float | None) -> int:
    """Return the minutes still to plan for a task: its estimate (scaled) less what's done.

    Args:
        task: The task row.
        ratio: The actual-to-estimate ratio when applied, else None.

    Returns:
        Minutes; `DEFAULT_MINUTES` with no estimate; 0 when nearly done.
    """
    if not task.estimated_minutes:
        return DEFAULT_MINUTES
    estimate = round(task.estimated_minutes * ratio) if ratio else task.estimated_minutes
    left = estimate - (task.actual_minutes or 0)
    return left if left >= MIN_REMAINING else 0


def plan_week(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> WeekPlan | None:
    """Return a proposed week: each open task's work placed in free time before it's due.

    Args:
        db: Open database session.
        user_id: Whose calendar and tasks.
        now: The user's local now, naive; defaults to their own clock.

    Returns:
        The proposal, with what didn't fit and every assumption; None when the user
        does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None
    now = now or user_now(db, user_id)
    today = now.date()
    end = today + timedelta(days=HORIZON_DAYS - 1)
    preferences = get_preferences(user)
    floor = preferences.min_free_block_minutes
    daily_cap = preferences.planner_daily_minutes

    # Every free stretch in the week, earliest first, as mutable [day, start, end].
    slots = sorted(
        ([b.on_date, _minutes(b.starts_at), _minutes(b.ends_at)] for b in free_blocks(db, user_id, today, end, now=now) or []),
        key=lambda s: (s[0], s[1]),
    )
    first_free = {s[0] for s in slots}

    tasks = (
        db.query(TaskModel)
        .filter(TaskModel.user_id == user_id, TaskModel.done.is_(False), TaskModel.archived.is_(False),
                TaskModel.due_date.isnot(None), TaskModel.due_date <= end)
        .all()
    )
    tasks = [t for t in tasks if t.snoozed_until is None or t.snoozed_until <= today]
    tasks.sort(key=lambda t: (t.due_date, -t.priority, t.title.lower()))

    # Time already planned for a task, so a second plan doesn't plan it twice;
    # and per day, so a second plan can't take a day past the daily limit (D28).
    planned: dict[uuid.UUID, int] = {}
    used: dict[date, int] = {}
    for event in db.query(EventModel).filter(EventModel.user_id == user_id, EventModel.source == SOURCE,
                                             EventModel.starts_on >= today):
        if event.start_time and event.end_time:
            length = _minutes(event.end_time) - _minutes(event.start_time)
            used[event.starts_on] = used.get(event.starts_on, 0) + length
            if event.planned_task_id is not None:
                planned[event.planned_task_id] = planned.get(event.planned_task_id, 0) + length

    ratio_reading = estimate_ratio(db, user_id)
    ratio = ratio_reading.ratio if ratio_reading.applied else None
    codes = course_codes(db, user_id)
    blocks: list[PlannedBlock] = []
    unplaced: list[Unplaced] = []

    for task in tasks:
        need = max(0, needed_minutes(task, ratio) - planned.get(task.id, 0))
        if need == 0:
            continue
        overdue = task.due_date < today
        last_day = end if overdue else task.due_date
        cutoff = _minutes(task.due_time) if task.due_time and not overdue else None
        placed = 0
        capped = False
        first_block = True
        earliest_possible = min((d for d in first_free if d <= last_day), default=None)
        for slot in slots:
            if need - placed <= 0:
                break
            if slot[0] > last_day:
                break
            # Fill this stretch while it has room, two hours at a time, before
            # moving on: the next stretch may be past the due date.
            while need - placed > 0:
                day, start, stop = slot
                if cutoff is not None and day == last_day:
                    stop = min(stop, cutoff)
                free = stop - start
                room = min(free, daily_cap - used.get(day, 0))
                left = need - placed
                if room < floor:
                    capped = capped or free >= floor
                    break
                # Never a block shorter than your shortest free block: a ten-minute
                # remainder rounds up rather than becoming a ten-minute block.
                take = min(max(left, floor), MAX_CHUNK, room)
                if first_block:
                    if overdue:
                        reason = "It's overdue, so the first free time."
                    elif day == earliest_possible:
                        reason = f"The first free time before it's due {_day(task.due_date, today)}."
                    else:
                        reason = (f"{_day(day, today).capitalize()}, because the free time before it went to "
                                  "work due sooner.")
                elif blocks and blocks[-1].task_id == task.id and blocks[-1].on_date == day:
                    reason = f"More of it after a {BREAK_MINUTES}-minute break, before it's due {_day(task.due_date, today)}."
                else:
                    reason = f"More of it, in the next free time before it's due {_day(task.due_date, today)}."
                blocks.append(PlannedBlock(
                    task_id=task.id, title=task.title, course_code=codes.get(task.course_id), due_date=task.due_date,
                    on_date=day, starts_at=_time(start), ends_at=_time(start + take), minutes=take, reason=reason,
                ))
                slot[1] = start + take
                used[day] = used.get(day, 0) + take
                placed += min(take, left)
                first_block = False
                if need - placed > 0:
                    slot[1] += BREAK_MINUTES
        if placed < need:
            short = need - placed
            due = _day(task.due_date, today)
            if capped:
                reason = (f"Only {placed} of {need} minutes fit before it's due {due} inside your daily limit of "
                          f"{_hours(daily_cap)}." if placed else
                          f"No time left before it's due {due} inside your daily limit of {_hours(daily_cap)}.")
            else:
                reason = (f"Only {placed} of {need} minutes are free before it's due {due}."
                          if placed else f"No free time left before it's due {due}.")
            unplaced.append(Unplaced(
                task_id=task.id, title=task.title, due_date=task.due_date, minutes_needed=need, minutes_short=short,
                reason=reason,
            ))

    assumptions = [
        f"Free time is your study window, between events, in stretches of at least {floor} minutes.",
        f"Each task gets its estimate{', scaled by how long tasks really take,' if ratio else ''} less the time "
        f"already logged; a task with no estimate gets {DEFAULT_MINUTES} minutes. No block is shorter than "
        f"{floor} minutes, so a small remainder rounds up.",
        f"No block runs longer than {MAX_CHUNK // 60} hours, with a {BREAK_MINUTES}-minute break before more of the "
        "same task. Soonest due goes first, then the most important.",
        f"At most {_hours(daily_cap)} of planned study a day, counting blocks you've already accepted. "
        "Change it in Settings, under Calendar.",
    ]
    if planned:
        assumptions.append("Time you've already accepted from the planner counts toward each task.")
    blocks.sort(key=lambda b: (b.on_date, b.starts_at))
    return WeekPlan(starts_on=today, ends_on=end, blocks=blocks, unplaced=unplaced, assumptions=assumptions)


def accept(db: Session, user_id: uuid.UUID, body: AcceptPlan, now: datetime | None = None) -> AcceptedPlan | None:
    """Put accepted blocks on the calendar, each re-checked against free time now.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        body: The blocks.
        now: The user's local now, naive; defaults to their own clock.

    Returns:
        How many events were written; None when the user does not exist.

    Raises:
        LookupError: If a block names anything but one of the caller's open tasks.
        ValueError: If a block isn't inside free time as the calendar stands, falls
            outside the week, or overlaps another block.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None
    now = now or user_now(db, user_id)
    today = now.date()
    ids = {b.task_id for b in body.blocks}
    tasks = {t.id: t for t in db.query(TaskModel).filter(
        TaskModel.user_id == user_id, TaskModel.id.in_(ids), TaskModel.done.is_(False), TaskModel.archived.is_(False))}
    if set(tasks) != ids:
        # Another person's task, like a missing one, is simply not found.
        raise LookupError("Task not found")

    days = sorted({b.on_date for b in body.blocks})
    if days[0] < today or days[-1] > today + timedelta(days=HORIZON_DAYS - 1):
        raise ValueError("Every block has to fall in the week being planned")
    free = free_blocks(db, user_id, days[0], days[-1], now=now) or []
    ordered = sorted(body.blocks, key=lambda b: (b.on_date, b.starts_at))
    for earlier, later in zip(ordered, ordered[1:]):
        if earlier.on_date == later.on_date and later.starts_at < earlier.ends_at:
            raise ValueError("Two blocks overlap")
    for block in ordered:
        if not any(f.on_date == block.on_date and f.starts_at <= block.starts_at and block.ends_at <= f.ends_at
                   for f in free):
            raise ValueError("A block isn't in free time any more; plan again")

    for block in ordered:
        task = tasks[block.task_id]
        db.add(EventModel(
            id=uuid.uuid4(), user_id=user_id, course_id=task.course_id, title=task.title, kind="personal",
            notes="Planned by the weekly planner.", starts_on=block.on_date, start_time=block.starts_at,
            end_time=block.ends_at, source=SOURCE, planned_task_id=task.id,
        ))
    db.commit()
    return AcceptedPlan(created=len(ordered))
