"""Exertion points and weekly goals (Phase 3 items 6 and 7).

An activity earns points when it is logged: hours x MET x corroboration weight x 10,
rounded, by the formula version stored with it, and never rewritten. A manual entry
weighs 1.0 until a device source exists to weigh it against. The weekly goal is the
student's own; the suggestion beside it is advice: the last 4 weeks plus 10%, eased
in a week holding exams. Weeks run Monday to Sunday in the student's own calendar.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import ActivityModel
from app.Calendar.schemas.event import EXAM_KINDS
from app.Calendar.services.event_service import list_occurrences
from app.Fitness.schemas.fitness import Activity, ActivityIn, Exertion, GoalSuggestion, WeekPoints
from app.shared.dates import user_for, user_today
from app.Users.services.user_service import get_preferences

#: The formula new activities are logged under. A new version adds an entry
#: below; rows keep the version, MET and weight they were logged with.
FORMULA_VERSION = 1
#: MET per activity kind, by formula version (the Compendium of Physical
#: Activities' moderate values).
MET_BY_VERSION = {
    1: {"walk": 3.5, "run": 9.8, "cycle": 7.5, "swim": 8.0, "gym": 5.0, "sport": 7.0, "yoga": 2.5,
        "hike": 6.0, "other": 4.0},
}
#: How much a source is trusted. Only manual entries exist until a device is
#: connected; their weight is what a corroborated source is measured against.
CORROBORATION = {"manual": 1.0}
#: How many complete weeks the suggestion averages, and how far it reaches past them.
SUGGEST_FROM_WEEKS = 4
OVERLOAD = 1.10
#: In a week holding an exam, the suggestion eases to this share.
EXAM_WEEK_SHARE = 0.7
#: Weeks with any activity needed before anything is suggested.
MIN_HISTORY_WEEKS = 2


def points(minutes: int, met: float, weight: float) -> int:
    """Return the points an activity earns under formula version 1.

    Args:
        minutes: How long it lasted.
        met: Its MET.
        weight: Its corroboration weight.

    Returns:
        Hours x MET x weight x 10, rounded to a whole point.
    """
    return round(minutes / 60 * met * weight * 10)


def monday_of(day: date) -> date:
    """Return the Monday of the week a day falls in."""
    return day - timedelta(days=day.weekday())


def log(db: Session, user_id: uuid.UUID, data: ActivityIn) -> Activity:
    """Log an activity, working out its points under the current formula.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: What, when and how long.

    Returns:
        The activity with its points.

    Note:
        Commits.
    """
    met = MET_BY_VERSION[FORMULA_VERSION][data.kind]
    weight = CORROBORATION["manual"]
    row = ActivityModel(user_id=user_id, on_date=data.on_date, kind=data.kind, minutes=data.minutes, met=met,
                        weight=weight, points=points(data.minutes, met, weight), formula_version=FORMULA_VERSION,
                        source="manual", note=(data.note or "").strip() or None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return Activity.model_validate(row)


def delete(db: Session, user_id: uuid.UUID, activity_id: uuid.UUID) -> bool:
    """Delete one of the caller's activities.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        activity_id: The activity.

    Returns:
        True if it was deleted; False when it is missing or another user's.

    Note:
        Commits.
    """
    row = db.query(ActivityModel).filter(ActivityModel.id == activity_id, ActivityModel.user_id == user_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def _totals(db: Session, user_id: uuid.UUID, start: date, end: date) -> dict[date, int]:
    """Return points per week (keyed by Monday) for activities between two days."""
    totals: dict[date, int] = {}
    for row in db.query(ActivityModel).filter(ActivityModel.user_id == user_id, ActivityModel.on_date >= start,
                                              ActivityModel.on_date <= end):
        week = monday_of(row.on_date)
        totals[week] = totals.get(week, 0) + row.points
    return totals


def exams_in_week(db: Session, user_id: uuid.UUID, week_start: date) -> int:
    """Return how many midterms and finals fall in a week on the student's calendar."""
    occurrences = list_occurrences(db, user_id, week_start, week_start + timedelta(days=6)) or []
    return sum(1 for o in occurrences if o.kind in {kind.value for kind in EXAM_KINDS} and o.job_id is None)


def suggest(history: list[int], exams: int) -> GoalSuggestion:
    """Return a suggested weekly goal from complete weeks' points.

    Args:
        history: The last `SUGGEST_FROM_WEEKS` complete weeks' points, oldest first.
        exams: Midterms and finals in the week being suggested for.

    Returns:
        Their average plus 10%, to the nearest 5, eased to 70% in an exam week; no
        number until `MIN_HISTORY_WEEKS` weeks hold any activity.
    """
    if sum(1 for week in history if week > 0) < MIN_HISTORY_WEEKS:
        return GoalSuggestion(points=None, reason="Log a couple of weeks of activity for a suggestion.")
    target = sum(history) / len(history) * OVERLOAD
    if exams:
        eased = max(5, round(target * EXAM_WEEK_SHARE / 5) * 5)
        word = "exam" if exams == 1 else "exams"
        return GoalSuggestion(points=eased, reason=f"{exams} {word} this week, so a lighter week than usual.")
    return GoalSuggestion(points=max(5, round(target / 5) * 5), reason="Your last 4 weeks, plus 10%.")


def summary(db: Session, user_id: uuid.UUID) -> Exertion | None:
    """Return this week's points against the goal, the weeks before, and a suggestion.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The summary; None when the user does not exist.
    """
    user = user_for(db, user_id)
    if user is None:
        return None
    today = user_today(db, user_id)
    week = monday_of(today)
    first = week - timedelta(weeks=8)
    totals = _totals(db, user_id, first, today)
    weeks = [WeekPoints(week_start=first + timedelta(weeks=i), points=totals.get(first + timedelta(weeks=i), 0))
             for i in range(8)]
    history = [w.points for w in weeks[-SUGGEST_FROM_WEEKS:]]
    recent = (
        db.query(ActivityModel)
        .filter(ActivityModel.user_id == user_id, ActivityModel.on_date > today - timedelta(days=28))
        .order_by(ActivityModel.on_date.desc(), ActivityModel.created_at.desc())
        .all()
    )
    return Exertion(
        week_start=week, this_week=totals.get(week, 0), goal=get_preferences(user).exertion_goal,
        suggestion=suggest(history, exams_in_week(db, user_id, week)), weeks=weeks,
        recent=[Activity.model_validate(row) for row in recent],
    )


def set_goal(db: Session, user_id: uuid.UUID, goal: int | None) -> Exertion | None:
    """Set or clear the caller's weekly goal.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        goal: Weekly points; None clears it.

    Returns:
        The summary with the new goal; None when the user does not exist.

    Note:
        Commits.
    """
    user = user_for(db, user_id)
    if user is None:
        return None
    # Reassigned whole: SQLAlchemy does not see a mutation inside a JSON column.
    user.preferences = {**(user.preferences or {}), "exertion_goal": goal}
    db.commit()
    return summary(db, user_id)
