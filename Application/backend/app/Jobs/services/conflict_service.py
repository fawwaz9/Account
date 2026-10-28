"""Service functions for shifts that overlap, or crowd, an exam.

Read from the calendar's own occurrences, so skipped dates, blackouts and
repeating shifts agree with what the calendar shows; nothing here writes. A
shift overlaps an exam when they share any time, and crowds it when it ends
before the exam starts but within the user's buffer. Missing times only ever
widen an item, so an untimed exam or shift flags more, never less.
"""
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import JobModel
from app.Calendar.services.event_service import list_occurrences
from app.Calendar.schemas.event import EventKind
from app.Jobs.schemas.conflict import ShiftConflict, ShiftConflicts
from app.shared.dates import user_for, user_today
from app.Users.services.user_service import get_preferences

EXAM_KINDS = {EventKind.MIDTERM.value, EventKind.FINAL.value}
#: When an exam with no time is assumed to start: the earliest a UBC exam sits.
UNTIMED_EXAM_START = time(8, 0)
#: How far ahead the Jobs page looks by default.
DEFAULT_DAYS = 60


def _span(on: date, start: time | None, end: time | None, *, untimed_start: time) -> tuple[datetime, datetime]:
    """Return an occurrence as a [start, end) interval of naive datetimes.

    A missing start uses `untimed_start`; a missing end runs to midnight; an end at
    or before the start is taken as the next day, for an overnight shift.
    """
    begins = datetime.combine(on, start or untimed_start)
    if end is None:
        ends = datetime.combine(on + timedelta(days=1), time(0, 0))
    elif start is not None and end <= start:
        # An overnight shift: 22:00 to 02:00 ends the next morning.
        ends = datetime.combine(on + timedelta(days=1), end)
    else:
        ends = datetime.combine(on, end)
    return begins, ends


def find_conflicts(occurrences, buffer_hours: int, job_names: dict) -> list[ShiftConflict]:
    """Pair every shift with every midterm or final it overlaps or crowds.

    An exam with no start time is taken to start at 08:00; a shift with no times
    runs the whole day.

    Args:
        occurrences: Expanded calendar occurrences; shifts are those with a
            `job_id`, exams the midterms and finals without one.
        buffer_hours: How many hours before an exam a shift must end by; 0 flags
            overlaps only.
        job_names: Job ids mapped to names, for labelling.

    Returns:
        The conflicts, by exam date and start, then shift date and kind; empty
        when there are none.
    """
    shifts = [o for o in occurrences if o.job_id is not None]
    exams = [o for o in occurrences if o.kind in EXAM_KINDS and o.job_id is None]
    buffer = timedelta(hours=buffer_hours)
    found = []
    for exam in exams:
        exam_start, exam_end = _span(exam.on_date, exam.start_time, exam.end_time, untimed_start=UNTIMED_EXAM_START)
        for shift in shifts:
            shift_start, shift_end = _span(shift.on_date, shift.start_time, shift.end_time, untimed_start=time(0, 0))
            if shift_start < exam_end and exam_start < shift_end:
                kind, gap = "overlap", 0.0
            elif shift_end <= exam_start and exam_start - shift_end < buffer:
                kind, gap = "crowds", round((exam_start - shift_end).total_seconds() / 3600, 1)
            else:
                continue
            found.append(ShiftConflict(
                kind=kind, shift_event_id=shift.event_id, shift_on=shift.on_date, shift_start=shift.start_time,
                shift_end=shift.end_time, job_id=shift.job_id, job_name=job_names.get(shift.job_id),
                exam_event_id=exam.event_id, exam_title=exam.title, exam_kind=exam.kind, exam_on=exam.on_date,
                exam_start=exam.start_time, course_code=exam.course_code, hours_between=gap,
            ))
    found.sort(key=lambda c: (c.exam_on, c.exam_start or UNTIMED_EXAM_START, c.shift_on, c.kind))
    return found


def shift_conflicts(db: Session, user_id: uuid.UUID, start: date | None = None,
                    end: date | None = None) -> ShiftConflicts | None:
    """Return the user's shift-and-exam conflicts for exams in a window.

    Shifts from the day before the window are included, so a closing shift the
    night before the first exam still counts.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        start: First exam date to report; defaults to the user's today.
        end: Last exam date to report; defaults to 60 days after `start`.

    Returns:
        The user's exam buffer and the conflicts; None when the user does not
        exist.

    Raises:
        ValueError: If the window is inverted or longer than the calendar allows.
    """
    user = user_for(db, user_id)
    if user is None:
        return None
    start = start or user_today(db, user_id)
    end = end or start + timedelta(days=DEFAULT_DAYS)
    # A shift the night before the window's first exam still counts.
    occurrences = list_occurrences(db, user_id, start - timedelta(days=1), end) or []
    buffer_hours = get_preferences(user).exam_buffer_hours
    names = {job.id: job.name for job in db.query(JobModel).filter(JobModel.user_id == user_id)}
    conflicts = [c for c in find_conflicts(occurrences, buffer_hours, names) if c.exam_on >= start]
    return ShiftConflicts(buffer_hours=buffer_hours, conflicts=conflicts)
