"""Exam countdown: inside a week of an exam, its course's open work first (Phase 4 item 5).

Reads the calendar's midterms and finals and the open tasks on their courses due
by the exam's day, or undated. An
exam already over today (past its end, or its start when it has no end) has left
the countdown, as it leaves the exam strip.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app._database.models import TaskModel, UserModel
from app.Calendar.schemas.event import EventKind
from app.Calendar.services.event_service import list_occurrences
from app.Tasks.schemas.countdown import CountdownExam, CountdownTask, ExamCountdown
from app.shared.dates import user_now

#: The countdown starts this many days before an exam (§16: "inside 7 days").
WINDOW_DAYS = 7
#: Tasks listed per exam; the count and the minutes cover all of them.
MAX_TASKS = 5

EXAM_KIND_VALUES = {EventKind.MIDTERM.value, EventKind.FINAL.value}


def still_ahead(item, now: datetime) -> bool:
    """Return whether an exam occurrence is still to come at `now`.

    Args:
        item: An event occurrence.
        now: The user's local now, naive.

    Returns:
        False for an earlier day, or for today's exam once its end (else its start)
        has passed; an untimed exam stays the whole day.
    """
    if item.on_date != now.date():
        return item.on_date > now.date()
    over = item.end_time or item.start_time
    return over is None or over > now.time()


def exam_countdown(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> ExamCountdown | None:
    """Return every exam in the next week with its course's open work.

    Args:
        db: Open database session.
        user_id: Whose calendar and tasks.
        now: The user's local now, naive; defaults to their own clock.

    Returns:
        The exams, soonest first; None when the user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None

    now = now or user_now(db, user_id)
    today = now.date()
    occurrences = list_occurrences(db, user_id, today, today + timedelta(days=WINDOW_DAYS)) or []
    exams = sorted(
        (item for item in occurrences if item.kind in EXAM_KIND_VALUES and still_ahead(item, now)),
        key=lambda item: (item.on_date, item.start_time is None, item.start_time),
    )

    course_ids = {item.course_id for item in exams if item.course_id is not None}
    open_by_course: dict[uuid.UUID, list] = {course_id: [] for course_id in course_ids}
    if course_ids:
        rows = (
            db.query(TaskModel)
            .filter(
                TaskModel.user_id == user_id,
                TaskModel.course_id.in_(course_ids),
                TaskModel.done.is_(False),
                TaskModel.archived.is_(False),
            )
            .all()
        )
        for row in rows:
            open_by_course[row.course_id].append(row)
    for tasks in open_by_course.values():
        tasks.sort(key=lambda t: (t.due_date is None, t.due_date or date.max, -t.priority, t.title.lower()))

    countdown: list[CountdownExam] = []
    for item in exams:
        # The work that matters before this exam: due by its day, or undated.
        # Work due after it isn't exam-week work and stays in the list below.
        tasks = [
            t for t in (open_by_course.get(item.course_id, []) if item.course_id else [])
            if t.due_date is None or t.due_date <= item.on_date
        ]
        countdown.append(CountdownExam(
            event_id=item.event_id,
            title=item.title,
            kind=item.kind.value if hasattr(item.kind, "value") else item.kind,
            on_date=item.on_date,
            start_time=item.start_time,
            location=item.location,
            course_id=item.course_id,
            course_code=item.course_code,
            days_left=(item.on_date - today).days,
            tasks=[
                CountdownTask(id=t.id, title=t.title, due_date=t.due_date,
                              estimated_minutes=t.estimated_minutes, priority=t.priority)
                for t in tasks[:MAX_TASKS]
            ],
            open_tasks=len(tasks),
            estimated_minutes=sum(t.estimated_minutes or 0 for t in tasks),
        ))
    return ExamCountdown(window_days=WINDOW_DAYS, exams=countdown)
