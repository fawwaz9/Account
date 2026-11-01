"""The deadline spending guard, detection half: crunch weeks and your own spikes (item 13).

§13.5: crunch detection, then personal spike prediction, then a pre-allocation
nudge 5-7 days before (never during), then a report card. This half is the first
two and the timing; the pre-allocation and the report card need a per-week
override stored, so they wait for the schema step.

- A week's **load** weighs each final 5, midterm 3, deadline event 1 and task due 1
  (the workload model's own weights), counting tasks due whether done or not, so
  a past week reads as heavy as it was.
- A **crunch week** carries at least `CRUNCH_FLOOR` and at least twice your
  median week's load: your threshold, not a generic one.
- A category **lifts** when its average in crunch weeks is more than `MIN_LIFT`
  times its average in other weeks, over at least `MIN_CATEGORY_WEEKS` crunch
  weeks, and by at least `MIN_GAP` dollars. Only your own spending; no priors.
- **Silent** until `NEEDED_CRUNCH_WEEKS` crunch weeks are in the history: a wrong
  prediction early is worse than none.

Calendar into money only: nothing here is read by an academic feature.
"""

import statistics
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import SpendCategoryModel, TaskModel, TransactionModel, UserModel
from app.Calendar.schemas.event import EventKind
from app.Calendar.services.event_service import list_occurrences
from app.Calendar.services.load_service import CRUNCH_WEIGHTS, TASK_WEIGHT
from app.Finances.schemas.guard import CategoryLift, SpendingGuard, UpcomingCrunch
from app.Finances.services.counted import on_counted_accounts
from app.shared.dates import user_today
from app.shared.money import money

HISTORY_WEEKS = 26
CRUNCH_FLOOR = 5
NEEDED_CRUNCH_WEEKS = 2
MIN_LIFT = 1.5
MIN_CATEGORY_WEEKS = 3
MIN_GAP = 5.0
#: The guard speaks for a crunch week starting within this many days.
LEAD_DAYS = 7

NOTE = ("A heads-up, not a licence: if you set money aside for it, the week stays inside your plan "
        "rather than on top of it.")


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weekly_load(db: Session, user_id: uuid.UUID, first: date, last: date) -> dict[date, dict]:
    """Return each week's load between two Mondays: weight, exams, deadlines, tasks.

    Args:
        db: Open database session.
        user_id: Whose calendar and tasks.
        first: The first Monday.
        last: The last Monday.

    Returns:
        Monday to {"weight", "exams", "deadlines", "tasks"}, every week present.
    """
    weeks = {first + timedelta(weeks=i): {"weight": 0, "exams": 0, "deadlines": 0, "tasks": 0}
             for i in range((last - first).days // 7 + 1)}
    for item in list_occurrences(db, user_id, first, last + timedelta(days=6)) or []:
        week = weeks.get(_monday(item.on_date))
        weight = CRUNCH_WEIGHTS.get(item.kind, 0)
        if week is None or not weight:
            continue
        week["weight"] += weight
        week["exams" if item.kind in (EventKind.MIDTERM.value, EventKind.FINAL.value) else "deadlines"] += 1
    for due in db.query(TaskModel.due_date).filter(TaskModel.user_id == user_id, TaskModel.archived.is_(False),
                                                   TaskModel.due_date >= first,
                                                   TaskModel.due_date <= last + timedelta(days=6)):
        week = weeks.get(_monday(due.due_date))
        if week is not None:
            week["weight"] += TASK_WEIGHT
            week["tasks"] += 1
    return weeks


def threshold(weights: list[int]) -> float:
    """Return the load a week needs to be a crunch: the floor, or twice your median week.

    The median is over every week in the history, quiet ones included, so a term
    whose only busy weeks are exam weeks still finds them; infinite with no load at all.
    """
    if not any(weights):
        return float("inf")
    return max(CRUNCH_FLOOR, 2 * statistics.median(weights))


def spending_guard(db: Session, user_id: uuid.UUID, today: date | None = None) -> SpendingGuard | None:
    """Return the crunch weeks found, your spikes in them, and the crunch week ahead.

    Args:
        db: Open database session.
        user_id: Whose calendar and money.
        today: The user's today; defaults to their own clock.

    Returns:
        The guard's reading; nothing to say until two crunch weeks are in the history.
        None when the user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None
    today = today or user_today(db, user_id)
    this_week = _monday(today)
    first = this_week - timedelta(weeks=HISTORY_WEEKS)
    history = weekly_load(db, user_id, first, this_week - timedelta(weeks=1))
    bar = threshold([w["weight"] for w in history.values()])
    crunch = {monday for monday, w in history.items() if w["weight"] >= bar}

    reading = SpendingGuard(ready=len(crunch) >= NEEDED_CRUNCH_WEEKS, crunch_weeks=len(crunch),
                            needed_crunch_weeks=NEEDED_CRUNCH_WEEKS, note=NOTE)
    if not reading.ready:
        return reading

    # The week ahead: a Monday within the lead, never the week already under way.
    ahead = weekly_load(db, user_id, this_week + timedelta(weeks=1), this_week + timedelta(weeks=1))
    upcoming_monday = this_week + timedelta(weeks=1)
    days_away = (upcoming_monday - today).days
    upcoming = ahead[upcoming_monday]
    if days_away <= LEAD_DAYS and upcoming["weight"] >= bar:
        reading.upcoming = UpcomingCrunch(starts_on=upcoming_monday, days_away=days_away, exams=upcoming["exams"],
                                          deadlines=upcoming["deadlines"], tasks=upcoming["tasks"])

    rows = (
        db.query(TransactionModel.category_id, TransactionModel.amount, TransactionModel.occurred_on)
        .filter(TransactionModel.user_id == user_id, TransactionModel.kind == "expense",
                TransactionModel.occurred_on >= first, TransactionModel.occurred_on < this_week,
                TransactionModel.category_id.isnot(None), on_counted_accounts(user_id))
        .all()
    )
    if not rows:
        return reading
    started = _monday(min(r.occurred_on for r in rows))
    weeks = [m for m in history if m >= started]
    spent: dict[uuid.UUID, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        spent[row.category_id][_monday(row.occurred_on)] += abs(row.amount)

    names = {c.id: c.name for c in db.query(SpendCategoryModel).filter(SpendCategoryModel.user_id == user_id)}
    crunch_in = [m for m in weeks if m in crunch]
    other = [m for m in weeks if m not in crunch]
    lifts: list[CategoryLift] = []
    if len(crunch_in) >= MIN_CATEGORY_WEEKS and other:
        for category_id, by_week in spent.items():
            crunch_avg = sum(by_week.get(m, 0.0) for m in crunch_in) / len(crunch_in)
            usual_avg = sum(by_week.get(m, 0.0) for m in other) / len(other)
            if usual_avg <= 0 or crunch_avg - usual_avg < MIN_GAP:
                continue
            lift = crunch_avg / usual_avg
            if lift > MIN_LIFT and category_id in names:
                lifts.append(CategoryLift(category=names[category_id], crunch_weekly=money(crunch_avg),
                                          usual_weekly=money(usual_avg), lift=round(lift, 1),
                                          crunch_weeks=len(crunch_in)))
    reading.lifts = sorted(lifts, key=lambda c: -c.lift)
    return reading
