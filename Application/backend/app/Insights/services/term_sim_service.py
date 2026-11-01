"""The term simulator: the three rooms over one 168-hour week (Phase 4 item 9, §13.19).

Not a new model: a composition over the engines that already exist. The week's
hours come from the sliders; the money side is the what-if (D16) with the
scenario's work hours and spending; the body side prices workouts at the
student's own usual effort; the academic side compares study hours with what the
student's tasks are estimated at.

**The boundary holding under pressure** (§13.5, §13.19): work hours move time and
money and nothing else. The academic part renders only when study hours are set
directly, and nothing in it reads the work hours. It never projects a grade: it
says what the study hours cover, beside each course's band as it stands.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import ActivityModel, UserModel
from app.Calendar.services.load_service import week_load
from app.Finances.schemas.whatif import WhatIfIn
from app.Finances.services.whatif_service import what_if
from app.Fitness.services.exertion_service import MET_BY_VERSION, FORMULA_VERSION
from app.Grades.services.course_service import get_all_courses
from app.Grades.services.grade_service import course_grade, project_course
from app.Grades.utils.terms import CURRENT
from app.Insights.schemas.term_sim import (
    WEEK_HOURS,
    AcademicFit,
    BodyFit,
    CourseBand,
    MoneyFit,
    RoomHours,
    TermDefaults,
    TermIn,
    TimeFit,
)
from app.Insights.schemas.term_sim import TermResult
from app.Users.services.user_service import get_preferences
from app.shared.dates import user_today

#: Weeks ahead the defaults average over.
AHEAD_WEEKS = 4
#: Weeks back the workout defaults average over.
BACK_WEEKS = 4
#: Points per minute with no activity logged: a moderate effort (MET 5, a gym session).
DEFAULT_POINTS_PER_MINUTE = MET_BY_VERSION[FORMULA_VERSION]["gym"] / 6


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weekly_ahead(db: Session, user_id: uuid.UUID, today: date) -> tuple[float, float, float]:
    """Return class, estimated study and work hours a week over the next four weeks.

    Args:
        db: Open database session.
        user_id: Whose calendar and tasks.
        today: The user's today.

    Returns:
        (class hours, estimated study hours, work hours), each a weekly average.
    """
    start = _monday(today) + timedelta(weeks=1)
    end = start + timedelta(weeks=AHEAD_WEEKS) - timedelta(days=1)
    load = week_load(db, user_id, start, end)
    if load is None:
        return 0.0, 0.0, 0.0
    per_week = 60 * AHEAD_WEEKS
    return (round(load.class_minutes / per_week, 1), round(load.estimated_minutes / per_week, 1),
            round(load.work_minutes / per_week, 1))


def workout_habits(db: Session, user_id: uuid.UUID, today: date) -> tuple[float, float, float]:
    """Return workouts a week, their average minutes, and points per minute, recently.

    Args:
        db: Open database session.
        user_id: Whose activities.
        today: The user's today.

    Returns:
        (a week, minutes each, points a minute); 0 workouts, 45 minutes and a moderate
        effort with none logged.
    """
    since = _monday(today) - timedelta(weeks=BACK_WEEKS)
    rows = db.query(ActivityModel).filter(ActivityModel.user_id == user_id, ActivityModel.on_date >= since,
                                          ActivityModel.on_date < _monday(today)).all()
    if not rows:
        return 0.0, 45.0, DEFAULT_POINTS_PER_MINUTE
    minutes = sum(r.minutes for r in rows)
    return (round(len(rows) / BACK_WEEKS, 1), round(minutes / len(rows)),
            (sum(r.points for r in rows) / minutes) if minutes else DEFAULT_POINTS_PER_MINUTE)


def defaults(db: Session, user_id: uuid.UUID, today: date | None = None) -> TermDefaults | None:
    """Return where each slider starts, from the student's own figures.

    Args:
        db: Open database session.
        user_id: Whose figures.
        today: The user's today; defaults to their own clock.

    Returns:
        The starting values; None when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None
    today = today or user_today(db, user_id)
    classes, study, work = weekly_ahead(db, user_id, today)
    workouts, minutes, _ = workout_habits(db, user_id, today)
    return TermDefaults(class_hours=classes, study_hours=study, work_hours=work, workouts_per_week=workouts,
                        workout_minutes=minutes, exertion_goal=get_preferences(user).exertion_goal)


def academic_fit(db: Session, user_id: uuid.UUID, study_hours: float, estimated: float) -> AcademicFit:
    """Return what directly set study hours cover, beside each current course's band.

    Reads nothing about work: only study hours, task estimates and grades.

    Args:
        db: Open database session.
        user_id: Whose courses.
        study_hours: The hours set directly.
        estimated: Estimated study hours a week from the student's tasks.

    Returns:
        The coverage in numbers and words, and the bands as they stand.
    """
    coverage = round(study_hours / estimated * 100) if estimated > 0 else None
    if coverage is None:
        reading = "Your tasks carry no estimates for these weeks, so there's nothing to measure the hours against."
    elif coverage >= 100:
        reading = f"{study_hours:g} hours covers the {estimated:g} your tasks are estimated at."
    else:
        reading = (f"{study_hours:g} hours covers {coverage}% of the {estimated:g} your tasks are estimated at: "
                   f"about {estimated - study_hours:.1f} hours short each week.")
    bands = [
        CourseBand(code=c.code, current=course_grade(c), best=project_course(c, 1.0), worst=project_course(c, 0.0))
        for c in get_all_courses(db, user_id) if c.term_bucket == CURRENT and not c.transfer_credit
    ]
    return AcademicFit(study_hours=study_hours, estimated_hours=estimated, coverage=coverage, reading=reading,
                       bands=bands)


def simulate(db: Session, user_id: uuid.UUID, body: TermIn, today: date | None = None) -> TermResult | None:
    """Return one simulated week of the term across the three rooms.

    Args:
        db: Open database session.
        user_id: Whose rooms.
        body: The sliders.
        today: The user's today; defaults to their own clock.

    Returns:
        The time fit, the money and body figures, and the academic part only when
        study hours were set; None when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None
    today = today or user_today(db, user_id)
    _, estimated, scheduled_work = weekly_ahead(db, user_id, today)
    _, _, per_minute = workout_habits(db, user_id, today)

    work = scheduled_work if body.work_hours is None else body.work_hours
    study = estimated if body.study_hours is None else body.study_hours
    workout_hours = body.workouts_per_week * body.workout_minutes / 60
    rooms = [
        RoomHours(room="academic", label="Classes and study", hours=round(body.class_hours + study, 1)),
        RoomHours(room="money", label="Work", hours=round(work, 1)),
        RoomHours(room="body", label="Workouts", hours=round(workout_hours, 1)),
        RoomHours(room="life", label="Sleep and everything else", hours=round((body.sleep_hours + body.overhead_hours) * 7, 1)),
    ]
    total = round(sum(r.hours for r in rooms), 1)
    time = TimeFit(rooms=rooms, total=total, fits=total <= WEEK_HOURS,
                   short_by=round(max(0.0, total - WEEK_HOURS), 1), spare=round(max(0.0, WEEK_HOURS - total), 1))

    money = None
    change = round(work - scheduled_work, 2)
    try:
        result = what_if(db, user_id, WhatIfIn(hours_per_week=max(-40, min(40, change)),
                                               monthly_spending_change=body.monthly_spending_change), on_day=today)
    except ValueError:
        result = None
    if result is not None:
        money = MoneyFit(
            baseline_ending=result.baseline.ending_balance, scenario_ending=result.scenario.ending_balance,
            difference=result.difference, lowest=result.scenario.lowest_balance,
            negative_on=result.scenario.negative_on.isoformat() if result.scenario.negative_on else None,
            notes=result.capped,
        )

    goal = get_preferences(user).exertion_goal
    weekly_points = round(body.workouts_per_week * body.workout_minutes * per_minute)
    body_fit = BodyFit(points_per_week=weekly_points, goal=goal,
                       meets_goal=None if goal is None else weekly_points >= goal)

    academic = academic_fit(db, user_id, body.study_hours, estimated) if body.study_hours is not None else None

    assumptions = [
        f"A week is {WEEK_HOURS} hours: sleep and everything else are counted every day.",
        f"Study, work and classes start from your next {AHEAD_WEEKS} weeks: tasks' estimates, scheduled shifts "
        "and timetabled classes.",
        "Work hours change your time and your money, and nothing about your grades.",
        "Workouts are priced at the effort of what you've logged lately"
        + ("." if per_minute != DEFAULT_POINTS_PER_MINUTE else ", or a moderate effort with nothing logged."),
    ]
    if body.study_hours is None:
        assumptions.append("Set study hours yourself to see what they cover; nothing academic shows until you do.")
    return TermResult(time=time, money=money, body=body_fit, academic=academic, assumptions=assumptions)
