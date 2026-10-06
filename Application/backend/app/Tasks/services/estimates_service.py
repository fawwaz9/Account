"""How long tasks really take, against what was estimated (Phase 1 D35, D36).

The review loop "you estimated 2h, it took 3.5h" (account-vision.md §13.13).
Two ways in, both landing in `tasks.actual_minutes`: the question asked when a
task with an estimate is ticked off, and a timer kept on the server.

The ratio is total actual over total estimated, not a mean of per-task ratios:
a five-minute task that took fifteen is a 3x miss that cost ten minutes, and
must not outweigh a five-hour one that ran an hour over.
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
    """Whole minutes, rounded up; None when the timer cannot be trusted."""
    seconds = (now - started).total_seconds()
    if seconds < 0 or seconds > TIMER_TRUST_HOURS * 3600:
        return None
    return max(1, math.ceil(seconds / 60))


def stop_clock(task: TaskModel, now: datetime | None = None) -> tuple[int, bool]:
    """Stop a running timer, adding what it measured. Returns (added, discarded).

    Called from `set_done` too, so ticking a task off with its timer running
    keeps the time rather than leaving a clock running on a finished task.
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
    if task.done:
        raise ValueError("This task is finished; untick it to time it again")
    if task.timer_started_at is None:  # starting a running timer changes nothing
        task.timer_started_at = utc_now()


def estimate_ratio(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> EstimateRatio:
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
