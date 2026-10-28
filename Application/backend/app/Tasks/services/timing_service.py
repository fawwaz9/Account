"""Service functions for completion timing: how early or late tasks get finished.

Derived from what is stored: a completed task's due date and `completed_at`. The
one thing it needs care with is time zones: `completed_at` is naive UTC and must
be read on the student's clock before it is compared with a local due date.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app._database.models import TaskModel, UserModel
from app.Tasks.schemas.timing import CompletionTiming, TimingWindow
# `zone_of` lived here and now lives in `shared.dates`, because the free-time,
# finance and jobs services all needed the same rule. Re-exported from this
# module's name so existing importers keep working.
from app.shared.dates import local_today, zone_of

#: Length of the rolling window, in days, counting today.
PAST_WEEK_DAYS = 7


def local_completion_date(completed_at: datetime, zone: ZoneInfo) -> date:
    """Return the local calendar day a task was ticked off on.

    Args:
        completed_at: When it was completed, naive UTC.
        zone: The user's time zone.

    Returns:
        The date in that zone.

    Note:
        Comparing the UTC date directly would shift evening completions west of
        Greenwich onto the next day and bias every figure toward late.
    """
    return completed_at.replace(tzinfo=timezone.utc).astimezone(zone).date()


def summarise(label: str, starts_on: date, ends_on: date, deltas: list[int]) -> TimingWindow:
    """Turn one window's day differences into the timing figures.

    Args:
        label: The window's name.
        starts_on: First day of the window.
        ends_on: Last day of the window.
        deltas: Completion date minus due date for each counted task, in days
            (positive is late).

    Returns:
        The window's figures; only the label and dates when `deltas` is empty.
    """
    window = TimingWindow(label=label, starts_on=starts_on, ends_on=ends_on)
    if not deltas:
        return window

    early = [-delta for delta in deltas if delta < 0]
    late = [delta for delta in deltas if delta > 0]
    on_time = len(deltas) - len(late)

    window.counted = len(deltas)
    window.mean_days = round(sum(deltas) / len(deltas), 1)
    window.on_time_percent = round(on_time / len(deltas) * 100, 1)
    window.early_count = len(early)
    window.late_count = len(late)
    if early:
        window.early_mean_days = round(sum(early) / len(early), 1)
    if late:
        window.late_mean_days = round(sum(late) / len(late), 1)

    return window


def completion_timing(db: Session, user_id: uuid.UUID, on_day: date | None = None):
    """Return how early or late the user finished dated work, over two windows.

    Reads every completed task (done tasks are archived, so `list_tasks` would miss
    them) and buckets each by the local day it was finished.

    Args:
        db: Open database session.
        user_id: Whose tasks.
        on_day: The day to report on; defaults to the user's today.

    Returns:
        The past seven days and the calendar month to date, plus how many undated
        tasks were finished in either; None when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    zone = zone_of(user)
    anchor = on_day or local_today(user)
    week_start = anchor - timedelta(days=PAST_WEEK_DAYS - 1)
    month_start = anchor.replace(day=1)
    earliest = min(week_start, month_start)

    completed = (
        db.query(TaskModel)
        .filter(
            TaskModel.user_id == user_id,
            TaskModel.done.is_(True),
            TaskModel.completed_at.isnot(None),
        )
        .all()
    )

    week: list[int] = []
    month: list[int] = []
    undated = 0

    for task in completed:
        finished_on = local_completion_date(task.completed_at, zone)
        if finished_on < earliest or finished_on > anchor:
            continue

        # Counted only after the window check, so the figure describes recent
        # work rather than every undated task ever ticked off.
        if task.due_date is None:
            undated += 1
            continue

        delta = (finished_on - task.due_date).days
        if finished_on >= week_start:
            week.append(delta)
        if finished_on >= month_start:
            month.append(delta)

    return CompletionTiming(
        past_week=summarise("Past week", week_start, anchor, week),
        this_month=summarise("This month", month_start, anchor, month),
        undated_completed=undated,
    )
