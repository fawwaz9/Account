"""How early or late work actually gets finished.

Derived entirely from what is already stored: a task carries `due_date` and, once
it is ticked off, `completed_at`. The difference between them is the whole
measurement, so this needs no new column and no new table.

The one thing it does need is care about time zones, and getting that wrong is
not a rounding error -- it is a bias in one direction across most of the sample.
See `local_completion_date`.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app._database.models import TaskModel, UserModel
from app.Tasks.schemas.timing import CompletionTiming, TimingWindow
from app.Users.services.user_service import get_preferences

#: Length of the rolling window, in days, counting today.
PAST_WEEK_DAYS = 7


def today() -> date:
    return date.today()


def zone_of(user: UserModel) -> ZoneInfo:
    """The student's own time zone, falling back to UTC if it is unreadable.

    A stored zone is validated on the way in, so a bad one here means the row
    predates that validation. Falling back beats failing the whole page.
    """
    try:
        return ZoneInfo(get_preferences(user).timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_completion_date(completed_at: datetime, zone: ZoneInfo) -> date:
    """The calendar day a task was ticked off, where the student was standing.

    `completed_at` is naive UTC (see `utc_now`), while `due_date` is a plain
    local date with no zone at all. Subtracting one from the other directly is
    wrong in a way that hides: in America/Regina, UTC-6, anything finished after
    18:00 local is stored on the following UTC day, so an evening's work on its
    due date reads as a day late. Evening is when most of it gets done, so the
    error is not noise -- it is a systematic drift toward "late" that would make
    the whole figure a lie.
    """
    return completed_at.replace(tzinfo=timezone.utc).astimezone(zone).date()


def summarise(label: str, starts_on: date, ends_on: date, deltas: list[int]) -> TimingWindow:
    """Turn a window's day-deltas into the figures the page shows."""
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
    """Both windows, from one pass over the completed tasks.

    Completed tasks are archived by `set_done`, so this deliberately does not go
    through `list_tasks`, which filters out done and archived work by default and
    would return nothing at all.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    zone = zone_of(user)
    anchor = on_day or today()
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
