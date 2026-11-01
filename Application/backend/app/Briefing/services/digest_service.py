"""The digest: today's calendar, work due, exams, risk and the week, in one body.

Composed from the services that already answer each part (occurrences, tasks,
exam countdown, deadline risk, week load, free blocks), so the digest says what
the pages say. Deterministic: the same data gives the same words. No money (D8).
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import CourseModel, TaskModel, UserModel
from app.Briefing.schemas.digest import (
    Digest,
    DigestEvent,
    DigestExam,
    DigestRisk,
    DigestTask,
    DigestWeek,
)
from app.Calendar.services.event_service import list_occurrences
from app.Calendar.services.load_service import free_blocks, week_load, week_of
from app.Tasks.services.countdown_service import exam_countdown
from app.Tasks.services.risk_service import deadline_risk
from app.shared.dates import user_now

#: Overdue tasks named by title; the count covers the rest.
MAX_LISTED = 3

KIND_WORDS = {"midterm": "midterm", "final": "final"}


def _duration(minutes: int) -> str:
    """Return minutes as "45m", "2h" or "1h 30m"."""
    hours, rest = divmod(max(0, int(minutes)), 60)
    if hours == 0:
        return f"{rest}m"
    return f"{hours}h" if rest == 0 else f"{hours}h {rest}m"


def _clock(value: time | None) -> str:
    """Return a time as "9am" or "6:30pm"; "" for None."""
    if value is None:
        return ""
    suffix = "am" if value.hour < 12 else "pm"
    hour = value.hour % 12 or 12
    return f"{hour}{suffix}" if value.minute == 0 else f"{hour}:{value.minute:02d}{suffix}"


def _days(days_left: int) -> str:
    """Return "today", "tomorrow" or "in 3 days"."""
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "tomorrow"
    return f"in {days_left} days"


def _plural(count: int, word: str) -> str:
    """Return "1 task" or "3 tasks"."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def build_digest(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> Digest | None:
    """Return the user's digest for today.

    Args:
        db: Open database session, acting as the user.
        user_id: Whose day.
        now: The user's local now, naive; defaults to their own clock.

    Returns:
        The digest with its plain-text rendering; None when the user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None

    now = now or user_now(db, user_id)
    today = now.date()
    codes = {
        row.id: row.code
        for row in db.query(CourseModel.id, CourseModel.code).filter(CourseModel.user_id == user_id).all()
    }

    occurrences = list_occurrences(db, user_id, today, today) or []
    events = [
        DigestEvent(
            title=item.title,
            kind=item.kind.value if hasattr(item.kind, "value") else item.kind,
            start_time=item.start_time,
            end_time=item.end_time,
            location=item.location,
            course_code=item.course_code,
        )
        for item in sorted(occurrences, key=lambda o: (o.start_time is not None, o.start_time or time.min))
    ]

    open_tasks = (
        db.query(TaskModel)
        .filter(
            TaskModel.user_id == user_id,
            TaskModel.done.is_(False),
            TaskModel.archived.is_(False),
            TaskModel.due_date.isnot(None),
            TaskModel.due_date <= today,
        )
        .all()
    )

    def as_digest(task) -> DigestTask:
        return DigestTask(
            title=task.title, course_code=codes.get(task.course_id), due_date=task.due_date,
            due_time=task.due_time, estimated_minutes=task.estimated_minutes,
        )

    due_today = sorted(
        (t for t in open_tasks if t.due_date == today),
        key=lambda t: (t.due_time is None, t.due_time or time.max, -t.priority, t.title.lower()),
    )
    overdue = sorted((t for t in open_tasks if t.due_date < today), key=lambda t: (t.due_date, t.title.lower()))

    countdown = exam_countdown(db, user_id, now)
    exams = [
        DigestExam(
            name=f"{exam.course_code} {KIND_WORDS.get(exam.kind, exam.kind)}" if exam.course_code else exam.title,
            on_date=exam.on_date, days_left=exam.days_left,
            open_tasks=exam.open_tasks, estimated_minutes=exam.estimated_minutes,
        )
        for exam in (countdown.exams if countdown else [])
    ]

    risk = deadline_risk(db, user_id, today)
    at_risk = [
        DigestRisk(due_date=d.due_date, titles=d.titles, shortfall_minutes=d.shortfall_minutes,
                   includes_earlier=d.minutes_by_then > d.own_minutes)
        for d in (risk.deadlines if risk and risk.ready else []) if d.at_risk
    ]

    monday = week_of(today)
    load = week_load(db, user_id, monday, monday + timedelta(days=6))
    week = DigestWeek(
        booked_minutes=load.booked_minutes if load else 0,
        estimated_minutes=load.estimated_minutes if load else 0,
        tasks_due=load.task_count if load else 0,
    )

    blocks = free_blocks(db, user_id, today, today, now=now) or []
    longest = max(blocks, key=lambda b: b.minutes, default=None)

    digest = Digest(
        on_date=today,
        events=events,
        due_today=[as_digest(t) for t in due_today],
        overdue=[as_digest(t) for t in overdue[:MAX_LISTED]],
        overdue_count=len(overdue),
        exams=exams,
        at_risk=at_risk,
        week=week,
        free_minutes_today=sum(b.minutes for b in blocks),
        longest_free_start=longest.starts_at if longest else None,
        longest_free_minutes=longest.minutes if longest else 0,
    )
    digest.text = render(digest)
    return digest


def render(digest: Digest) -> str:
    """Return the digest as plain sentences, one line per part, parts with nothing left out.

    Args:
        digest: The digest.

    Returns:
        The text; never mentions money.
    """
    lines = [digest.on_date.strftime("%A, %B ") + str(digest.on_date.day) + "."]

    if digest.events:
        parts = []
        for event in digest.events:
            name = f"{event.course_code} {event.kind}" if event.course_code and event.kind != "personal" else event.title
            when = (
                f"{_clock(event.start_time)}–{_clock(event.end_time)}" if event.start_time and event.end_time
                else _clock(event.start_time) or "all day"
            )
            where = f" ({event.location})" if event.location else ""
            parts.append(f"{name} {when}{where}")
        lines.append("Today: " + "; ".join(parts) + ".")
    else:
        lines.append("Nothing on the calendar today.")

    if digest.due_today:
        names = [f"{t.title}" + (f" ({t.course_code})" if t.course_code else "") for t in digest.due_today]
        lines.append("Due today: " + ", ".join(names) + ".")

    if digest.overdue_count:
        names = ", ".join(t.title for t in digest.overdue)
        more = digest.overdue_count - len(digest.overdue)
        lines.append(
            f"Overdue: {_plural(digest.overdue_count, 'task')} — {names}" + (f" and {more} more" if more else "") + "."
        )

    for exam in digest.exams:
        work = (
            f" — {_plural(exam.open_tasks, 'open task')}"
            + (f", about {_duration(exam.estimated_minutes)}" if exam.estimated_minutes else "")
            if exam.open_tasks else ""
        )
        lines.append(f"Exam: {exam.name} {_days(exam.days_left)}{work}.")

    for item in digest.at_risk:
        days = (item.due_date - digest.on_date).days
        lines.append(
            f"At risk: {', '.join(item.titles)} ({_days(days)})"
            f"{', with what is due before it' if item.includes_earlier else ''} — about "
            f"{_duration(item.shortfall_minutes)} short at your usual pace."
        )

    week = digest.week
    if week.booked_minutes or week.tasks_due:
        booked = f"{_duration(week.booked_minutes)} booked" if week.booked_minutes else "nothing booked"
        work = f", {_duration(week.estimated_minutes)} of estimated work" if week.estimated_minutes else ""
        lines.append(f"This week: {booked}{work}, {_plural(week.tasks_due, 'task')} due.")

    if digest.free_minutes_today:
        start = _clock(digest.longest_free_start)
        if digest.longest_free_minutes == digest.free_minutes_today:
            lines.append(f"Free today: {_duration(digest.free_minutes_today)} from {start}.")
        else:
            lines.append(
                f"Free today: {_duration(digest.free_minutes_today)}, the longest "
                f"{_duration(digest.longest_free_minutes)} from {start}."
            )

    return "\n".join(lines)
