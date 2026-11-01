"""Deadline risk: your velocity against the velocity each deadline needs (Phase 4 item 3).

Velocity is the minutes of work you actually finished per day over the last four
weeks: a finished task's timed or reported minutes, else its estimate. Required
velocity for a due date is the estimated minutes still open on everything due by
then, overdue work included, divided by the days left. A deadline is at risk when
the second is above the first. Division, not machine learning (§4).

Cold start (§13.5: a wrong prediction early is worse than none): nothing is said
until there are `NEEDED_DAYS` days of history and `NEEDED_TASKS` finished tasks
with a time, and the answer says how close it is.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app._database.models import TaskModel, UserModel
from app.Tasks.schemas.risk import DeadlineRisk, RiskDeadline
from app.Tasks.services.estimates_service import estimate_ratio
from app.Tasks.services.timing_service import local_completion_date
from app.shared.dates import user_today, user_zone

#: How far back velocity looks. Long enough to smooth a week off, short enough to
#: follow a term's change of pace.
WINDOW_DAYS = 28
#: Days of history before velocity means anything.
NEEDED_DAYS = 14
#: Finished tasks with a time before velocity means anything.
NEEDED_TASKS = 5
#: How far ahead due dates are read.
HORIZON_DAYS = 21


def task_minutes(task) -> int | None:
    """Return the minutes a finished task stands for: actual, else estimated.

    Args:
        task: A task row.

    Returns:
        Minutes above 0, or None when the task carries neither figure.
    """
    for minutes in (task.actual_minutes, task.estimated_minutes):
        if minutes and minutes > 0:
            return minutes
    return None


def velocity(db: Session, user_id: uuid.UUID, today: date) -> tuple[float | None, int, int]:
    """Return minutes finished per day, the days of history behind it, and the tasks.

    Args:
        db: Open database session.
        user_id: Whose tasks.
        today: The user's today.

    Returns:
        (minutes per day or None when there is no history, history days, counted tasks).
        History runs from the first finished task with a time, capped at the window.
    """
    rows = (
        db.query(TaskModel)
        .filter(
            TaskModel.user_id == user_id,
            TaskModel.done.is_(True),
            TaskModel.completed_at.isnot(None),
        )
        .all()
    )
    # `completed_at` is naive UTC; an evening's work belongs to the user's own day,
    # not to tomorrow in Greenwich.
    zone = user_zone(db, user_id)
    counted = [(local_completion_date(row.completed_at, zone), task_minutes(row)) for row in rows]
    counted = [(day, minutes) for day, minutes in counted if minutes is not None and day <= today]
    if not counted:
        return None, 0, 0

    first = min(day for day, _ in counted)
    history_days = min(WINDOW_DAYS, (today - first).days + 1)
    since = today - timedelta(days=history_days - 1)
    in_window = [minutes for day, minutes in counted if day >= since]
    return round(sum(in_window) / history_days, 1), history_days, len(in_window)


def deadline_risk(db: Session, user_id: uuid.UUID, today: date | None = None) -> DeadlineRisk | None:
    """Return the user's velocity and each due date in the next three weeks against it.

    Args:
        db: Open database session.
        user_id: Whose tasks.
        today: The user's today; defaults to their own clock's.

    Returns:
        The reading, with no deadlines until the cold start is past; None when the
        user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None

    today = today or user_today(db, user_id)
    pace, history_days, counted_tasks = velocity(db, user_id, today)
    ratio = estimate_ratio(db, user_id)
    applied = ratio.ratio if ratio.applied else None
    ready = history_days >= NEEDED_DAYS and counted_tasks >= NEEDED_TASKS and pace is not None

    horizon_end = today + timedelta(days=HORIZON_DAYS)
    open_tasks = (
        db.query(TaskModel)
        .filter(
            TaskModel.user_id == user_id,
            TaskModel.done.is_(False),
            TaskModel.archived.is_(False),
            TaskModel.due_date.isnot(None),
            TaskModel.due_date <= horizon_end,
        )
        .all()
    )
    unestimated = sum(1 for task in open_tasks if not task.estimated_minutes)

    reading = DeadlineRisk(
        ready=ready,
        history_days=history_days,
        needed_days=NEEDED_DAYS,
        counted_tasks=counted_tasks,
        needed_tasks=NEEDED_TASKS,
        window_days=WINDOW_DAYS,
        velocity_minutes_per_day=pace if ready else None,
        estimate_ratio=applied,
        unestimated_open=unestimated,
        horizon_days=HORIZON_DAYS,
    )
    if not ready:
        return reading

    by_day: dict[date, list] = defaultdict(list)
    for task in open_tasks:
        by_day[task.due_date].append(task)

    def scaled(minutes: int) -> int:
        return round(minutes * applied) if applied else minutes

    # Overdue work still has to be done, so it counts toward every deadline after
    # it; it is not a deadline of its own, since its day has gone.
    running = scaled(sum(t.estimated_minutes or 0 for d, ts in by_day.items() if d < today for t in ts))
    deadlines: list[RiskDeadline] = []
    for day in sorted(d for d in by_day if d >= today):
        tasks = sorted(by_day[day], key=lambda t: (-t.priority, t.title.lower()))
        own = scaled(sum(t.estimated_minutes or 0 for t in tasks))
        running += own
        days_left = (day - today).days + 1
        required = running / days_left
        # A day that adds no estimated work is no new risk: whatever shortfall it
        # shows was already named at an earlier deadline.
        at_risk = required > pace and own > 0
        deadlines.append(RiskDeadline(
            due_date=day,
            tasks=len(tasks),
            titles=[t.title for t in tasks[:3]],
            own_minutes=own,
            minutes_by_then=running,
            days_left=days_left,
            required_minutes_per_day=round(required, 1),
            at_risk=at_risk,
            shortfall_minutes=round(running - pace * days_left) if at_risk else 0,
        ))
    reading.deadlines = deadlines
    return reading
