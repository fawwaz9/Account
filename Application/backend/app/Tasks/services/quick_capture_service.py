"""Service functions for quick capture: one typed line turned into a task.

`app.shared.tokenizer` reads the text knowing nothing about the account; this
module matches what it found against the user's real courses. The preview and
the capture read the line the same way, so what is created is what was shown.
"""

import uuid

from sqlalchemy.orm import Session

from app.Grades.services.course_lookup import resolve_course
from app.Tasks.schemas.quick_capture import QuickCapturePreview
from app.Tasks.schemas.task import MAX_ESTIMATED_MINUTES, TaskCreate
from app.Tasks.services.task_service import create_task, user_exists
from app.shared.tokenizer import parse
from app.shared.dates import user_today

def build_preview(db: Session, user_id: uuid.UUID, text: str) -> QuickCapturePreview | None:
    """Read one typed line and say what task it would create, writing nothing.

    A course code that matches none (or several) of the user's courses is put back
    into the title rather than dropped; a duration outside 1-2400 minutes is ignored.

    Args:
        db: Open database session.
        user_id: Whose courses to match, and whose today dates are read against.
        text: The typed line.

    Returns:
        The preview; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    parsed = parse(text, user_today(db, user_id))
    title = parsed.title
    course = None
    unmatched = None

    if parsed.course_code:
        course = resolve_course(db, user_id, parsed.course_code)
        if course is None:
            # Never swallow text that was not used. A code matching no course
            # goes back into the title, where the student can see it was not
            # understood and fix it.
            unmatched = parsed.course_code
            title = f"{parsed.course_code} {title}".strip()

    minutes = parsed.minutes
    if minutes is not None and not (1 <= minutes <= MAX_ESTIMATED_MINUTES):
        # Out of range reads as a slipped digit rather than a plan, and the task
        # schema would refuse it anyway -- so drop it rather than fail the line.
        minutes = None

    return QuickCapturePreview(
        text=text,
        title=title,
        due_date=parsed.on_date,
        estimated_minutes=minutes,
        course_id=course.id if course else None,
        course_code=course.code if course else None,
        unmatched_course=unmatched,
        matched=parsed.matched,
        can_create=bool(title.strip()),
    )


def capture(db: Session, user_id: uuid.UUID, text: str):
    """Create the task one typed line describes, from the same preview the client saw.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        text: The typed line.

    Returns:
        The new task row and the preview it came from; (None, None) when the user
        does not exist.

    Raises:
        ValueError: If nothing is left of the line to make a title from.
    """
    preview = build_preview(db, user_id, text)
    if preview is None:
        return None, None

    if not preview.can_create:
        raise ValueError("There is nothing here to make a task from")

    task = create_task(db, user_id, TaskCreate(
        title=preview.title,
        notes=None,
        due_date=preview.due_date,
        due_time=None,
        estimated_minutes=preview.estimated_minutes,
        course_id=preview.course_id,
        tags=[],
    ))
    return task, preview
