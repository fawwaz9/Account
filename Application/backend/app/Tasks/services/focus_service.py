"""Focus sessions: a timer tagged per course (Phase 4 item 4).

One session runs at a time; starting another stops the first. A session left
running longer than `TRUST_HOURS` was forgotten, not studied through, so stopping
it records nothing, the task timer's own rule. Focus per course per week, and
hours on each course this term beside its grade, are read from the sessions.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app._database.models import CourseModel, FocusSessionModel, UserModel, utc_now
from app.Grades.services.course_service import get_all_courses
from app.Grades.services.grade_service import course_grade
from app.Grades.utils.terms import CURRENT
from app.Tasks.schemas.focus import CourseFocus, FocusSession, FocusStart, FocusSummary
from app.Tasks.services.timing_service import local_completion_date
from app.shared.dates import user_today, user_zone

#: A session running longer than this was forgotten: stopping it records nothing.
TRUST_HOURS = 12
#: How far back "this term" reaches when no course in it has dates.
TERM_DAYS = 120


def running(db: Session, user_id: uuid.UUID) -> FocusSessionModel | None:
    """Return the user's session under way, if any."""
    return (db.query(FocusSessionModel)
            .filter(FocusSessionModel.user_id == user_id, FocusSessionModel.ended_at.is_(None))
            .first())


def _close(row: FocusSessionModel, now: datetime) -> None:
    elapsed = now - row.started_at
    row.ended_at = now
    row.minutes = 0 if elapsed > timedelta(hours=TRUST_HOURS) or elapsed.total_seconds() < 0 else int(elapsed.total_seconds() // 60)


def _out(row: FocusSessionModel, codes: dict) -> FocusSession:
    return FocusSession(id=row.id, course_id=row.course_id, course_code=codes.get(row.course_id),
                        started_at=row.started_at, ended_at=row.ended_at, minutes=row.minutes)


def start(db: Session, user_id: uuid.UUID, body: FocusStart, now: datetime | None = None) -> FocusSession | None:
    """Start a session, stopping any one already running.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        body: The course it's for, if any.
        now: The moment, naive UTC; defaults to now.

    Returns:
        The new session; None when the user does not exist.

    Raises:
        LookupError: If the course isn't one of the caller's.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None
    codes = {}
    if body.course_id is not None:
        course = db.query(CourseModel).filter(CourseModel.id == body.course_id, CourseModel.user_id == user_id).first()
        if course is None:
            raise LookupError("Course not found")
        codes[course.id] = course.code
    now = now or utc_now()
    previous = running(db, user_id)
    if previous is not None:
        _close(previous, now)
    row = FocusSessionModel(id=uuid.uuid4(), user_id=user_id, course_id=body.course_id, started_at=now)
    db.add(row)
    db.commit()
    return _out(row, codes)


def stop(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> FocusSession | None:
    """Stop the running session, if there is one.

    Returns:
        The stopped session; None when nothing was running.
    """
    row = running(db, user_id)
    if row is None:
        return None
    _close(row, now or utc_now())
    db.commit()
    codes = {c.id: c.code for c in db.query(CourseModel.id, CourseModel.code).filter(CourseModel.user_id == user_id)}
    return _out(row, codes)


def summary(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> FocusSummary | None:
    """Return the running session, and focus per course this week and this term.

    Args:
        db: Open database session.
        user_id: Whose sessions.
        now: The moment, naive UTC; defaults to now.

    Returns:
        This term's courses (plus focus on no course, if any), most focused first,
        each with its grade now; None when the user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None
    zone = user_zone(db, user_id)
    today = local_completion_date(now, zone) if now else user_today(db, user_id)
    monday = today - timedelta(days=today.weekday())
    term_start = today - timedelta(days=TERM_DAYS)

    courses = [c for c in get_all_courses(db, user_id) if c.term_bucket == CURRENT and not c.transfer_credit]
    by_course: dict = {c.id: CourseFocus(course_id=c.id, course_code=c.code,
                                         grade=course_grade(c) if c.reported_average is not None else None)
                       for c in courses}
    codes = {c.id: c.code for c in db.query(CourseModel.id, CourseModel.code).filter(CourseModel.user_id == user_id)}
    for row in db.query(FocusSessionModel).filter(FocusSessionModel.user_id == user_id,
                                                  FocusSessionModel.minutes.isnot(None)):
        day = local_completion_date(row.started_at, zone)
        if day < term_start:
            continue
        entry = by_course.get(row.course_id)
        if entry is None:
            if row.course_id is not None and row.course_id not in codes:
                continue
            entry = by_course.setdefault(row.course_id, CourseFocus(
                course_id=row.course_id, course_code=codes.get(row.course_id, "No course")))
        entry.minutes_term += row.minutes
        if day >= monday:
            entry.minutes_this_week += row.minutes

    current = running(db, user_id)
    ordered = sorted(by_course.values(), key=lambda c: (-c.minutes_term, c.course_code))
    return FocusSummary(running=_out(current, codes) if current else None, courses=ordered,
                        total_this_week=sum(c.minutes_this_week for c in ordered))
