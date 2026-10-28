"""Service functions for how long tasks really take against their estimates.

Actual time reaches `tasks.actual_minutes` two ways: the question asked when an
estimated task is ticked off, and a timer kept on the server. The ratio is total
actual over total estimated, never a mean of per-task ratios, so a small task
missed badly cannot outweigh a long one.
"""

import math
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app._database.models import TaskModel, utc_now
from app.Tasks.schemas.task import EstimateRatio
from app.Users.services.user_service import get_preferences
from app.shared.dates import user_for

#: A timer running longer than this was forgotten, not worked to: stopping it
#: records nothing rather than a night's sleep as time on an essay.
TIMER_TRUST_HOURS = 12
#: Tasks with both numbers needed before the ratio says anything.
RATIO_MIN_TASKS = 5
#: How far back the ratio looks. Habits change over a term; a year-old
#: estimate says little about this week's.
RATIO_WINDOW_DAYS = 90


def elapsed_minutes(started: datetime, now: datetime) -> int | None:
    """Return a timer's elapsed time in whole minutes, rounded up.

    Args:
        started: When the timer started, naive UTC.
        now: The moment it stops, naive UTC.

    Returns:
        At least 1 minute; None when the span is negative or longer than
        `TIMER_TRUST_HOURS`, which means the timer was forgotten.
    """
    seconds = (now - started).total_seconds()
    if seconds < 0 or seconds > TIMER_TRUST_HOURS * 3600:
        return None
    return max(1, math.ceil(seconds / 60))


def stop_clock(task: TaskModel, now: datetime | None = None) -> tuple[int, bool]:
    """Stop a task's running timer and add what it measured to `actual_minutes`.

    Only changes the row; the caller commits. `set_done` calls it too, so ticking a
    task off with its timer running keeps the time.

    Args:
        task: The task, whose timer may or may not be running.
        now: The stopping moment, naive UTC; defaults to now.

    Returns:
        The minutes added and whether the timer was discarded as untrustworthy:
        (0, False) when no timer was running, (0, True) when it was discarded.
    """
    if task.timer_started_at is None:
        return 0, False
    minutes = elapsed_minutes(task.timer_started_at, now or utc_now())
    task.timer_started_at = None
    if minutes is None:
        return 0, True
    task.actual_minutes = (task.actual_minutes or 0) + minutes
    return minutes, False


def start_timer(task: TaskModel) -> None:
    """Start a task's timer, leaving one that is already running alone.

    Only changes the row; the caller commits.

    Args:
        task: The task to time.

    Raises:
        ValueError: If the task is already done.
    """
    if task.done:
        raise ValueError("This task is finished; untick it to time it again")
    if task.timer_started_at is None:  # starting a running timer changes nothing
        task.timer_started_at = utc_now()


def estimate_ratio(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> EstimateRatio:
    """Return how the user's actual task times compare with their estimates.

    Reads tasks completed in the last `RATIO_WINDOW_DAYS` days that carry both an
    estimate and an actual time.

    Args:
        db: Open database session.
        user_id: Whose tasks to read.
        now: The moment to look back from, naive UTC; defaults to now.

    Returns:
        The ratio (None until `RATIO_MIN_TASKS` such tasks exist), the counts
        and sums behind it, and whether the user asked for the workload forecast
        to apply it.
    """
    since = (now or utc_now()) - timedelta(days=RATIO_WINDOW_DAYS)
    rows = (
        db.query(TaskModel.estimated_minutes, TaskModel.actual_minutes)
        .filter(
            TaskModel.user_id == user_id,
            TaskModel.done.is_(True),
            TaskModel.completed_at >= since,
            TaskModel.estimated_minutes.isnot(None),
            TaskModel.actual_minutes.isnot(None),
        )
        .all()
    )
    estimated = sum(row.estimated_minutes for row in rows)
    actual = sum(row.actual_minutes for row in rows)
    enough = len(rows) >= RATIO_MIN_TASKS and estimated > 0
    return EstimateRatio(
        ratio=round(actual / estimated, 2) if enough else None,
        tasks=len(rows),
        needed=RATIO_MIN_TASKS,
        estimated_minutes=estimated,
        actual_minutes=actual,
        applied=enough and get_preferences(user_for(db, user_id)).use_estimate_ratio,
    )
