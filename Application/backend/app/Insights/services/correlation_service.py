"""Cross-room correlations, non-financial: exertion against finished work (item 8).

Week by week over the last half-year: exertion points (the body room) against
tasks finished and minutes of work finished (the academic room). Pearson's r,
read into words, with the number of weeks behind it. Nothing is said until both
rooms hold `NEEDED_WEEKS` weeks of data, because a spurious link early erodes
trust (§15: "ice cream causes grades"). No money table is read (§13.3).
"""

import math
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import ActivityModel, TaskModel, UserModel
from app.Insights.schemas.correlations import Correlation, Correlations, WeekPair
from app.Tasks.services.risk_service import task_minutes
from app.Tasks.services.timing_service import local_completion_date
from app.shared.dates import user_today, user_zone

#: Weeks of both rooms before anything is said.
NEEDED_WEEKS = 8
#: How far back the weeks run.
WINDOW_WEEKS = 26

CAUTION = (
    "Weeks that move together aren't proof that one causes the other: a light week of classes can mean "
    "more time for both."
)


def monday_of(day: date) -> date:
    """Return the Monday on or before a day."""
    return day - timedelta(days=day.weekday())


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Return Pearson's r for two equal-length series, or None when either never changes.

    Args:
        xs: One series.
        ys: The other.

    Returns:
        r in [-1, 1], or None with no variation on one side.
    """
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
    return max(-1.0, min(1.0, r))


def strength(r: float | None) -> str:
    """Return a coefficient in words: under 0.2 is no clear link, then weak, moderate, strong."""
    if r is None or abs(r) < 0.2:
        return "no clear link"
    if abs(r) < 0.4:
        return "weak"
    if abs(r) < 0.6:
        return "moderate"
    return "strong"


def reading(r: float | None, weeks: int, academic: str) -> str:
    """Return one sentence on what moved together, never a cause."""
    word = strength(r)
    if word == "no clear link":
        return f"No clear link across {weeks} weeks between how much you moved and the {academic} you finished."
    direction = "more" if r > 0 else ("fewer" if academic == "tasks" else "less")
    return (f"A {word} link across {weeks} weeks: in weeks you moved more, you tended to finish "
            f"{direction} {academic}.")


def correlations(db: Session, user_id: uuid.UUID, today: date | None = None) -> Correlations | None:
    """Return exertion against finished work, week by week, once there are enough weeks.

    Args:
        db: Open database session.
        user_id: Whose rooms.
        today: The user's today; defaults to their own clock.

    Returns:
        The reading; no pairs until `NEEDED_WEEKS` weeks hold both rooms. None when the
        user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None
    today = today or user_today(db, user_id)
    last = monday_of(today) - timedelta(weeks=1)  # the last complete week
    first = last - timedelta(weeks=WINDOW_WEEKS - 1)

    body: dict[date, int] = {}
    for row in db.query(ActivityModel).filter(ActivityModel.user_id == user_id, ActivityModel.on_date >= first,
                                              ActivityModel.on_date <= last + timedelta(days=6)):
        week = monday_of(row.on_date)
        body[week] = body.get(week, 0) + row.points

    zone = user_zone(db, user_id)
    tasks: dict[date, int] = {}
    minutes: dict[date, int] = {}
    for row in db.query(TaskModel).filter(TaskModel.user_id == user_id, TaskModel.done.is_(True),
                                          TaskModel.completed_at.isnot(None)):
        week = monday_of(local_completion_date(row.completed_at, zone))
        if not first <= week <= last:
            continue
        tasks[week] = tasks.get(week, 0) + 1
        minutes[week] = minutes.get(week, 0) + (task_minutes(row) or 0)

    if not body or not tasks:
        return Correlations(ready=False, weeks_of_both=0, needed_weeks=NEEDED_WEEKS, caution=CAUTION)

    start = max(min(body), min(tasks))
    weeks = [start + timedelta(weeks=i) for i in range((last - start).days // 7 + 1)]
    if len(weeks) < NEEDED_WEEKS:
        return Correlations(ready=False, weeks_of_both=len(weeks), needed_weeks=NEEDED_WEEKS, caution=CAUTION)

    found: list[Correlation] = []
    for key, series, label in (("tasks", tasks, "tasks"), ("minutes", minutes, "work")):
        xs = [body.get(w, 0) for w in weeks]
        ys = [series.get(w, 0) for w in weeks]
        r = pearson(xs, ys)
        found.append(Correlation(
            key=key, body_label="Exertion points",
            academic_label="Tasks finished" if key == "tasks" else "Minutes of work finished",
            weeks=len(weeks), coefficient=None if r is None else round(r, 2), strength=strength(r),
            reading=reading(r, len(weeks), label),
            pairs=[WeekPair(week_start=w, body=x, academic=y) for w, x, y in zip(weeks, xs, ys)],
        ))
    return Correlations(ready=True, weeks_of_both=len(weeks), needed_weeks=NEEDED_WEEKS,
                        correlations=found, caution=CAUTION)
