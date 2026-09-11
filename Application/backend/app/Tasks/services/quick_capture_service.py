"""Turning one typed line into a real task.

Two steps, deliberately separate. `app.shared.tokenizer` reads the text and
knows nothing about this account; this module takes what it found and matches it
against courses that actually exist. Keeping them apart is what lets the parser
be tested without fixtures and reused by the omnibox later.
"""

import re
import uuid

from sqlalchemy.orm import Session

from app._database.models import CourseModel
from app.Tasks.schemas.quick_capture import QuickCapturePreview
from app.Tasks.schemas.task import MAX_ESTIMATED_MINUTES, TaskCreate
from app.Tasks.services.task_service import create_task, user_exists
from app.shared.tokenizer import parse

#: Splits a code into its letters and its number, ignoring spacing and case, so
#: "cpsc210", "CPSC 210" and "cpsc_v 210" can be compared on equal terms.
CODE_PARTS = re.compile(r"^([A-Za-z_]+)\s*(\d+[A-Za-z]?)$")


def code_parts(code: str) -> tuple[str, str] | None:
    """A code as (letters, number), with case, spacing and underscores ignored.

    Underscores go from both sides rather than just the stored one, so someone
    typing "statv201" finds "STAT_V 201" as readily as "stat201" does.
    """
    match = CODE_PARTS.match(code.strip())
    if match is None:
        return None
    return match.group(1).upper().replace("_", ""), match.group(2).upper()


def resolve_course(db: Session, user_id: uuid.UUID, typed: str) -> CourseModel | None:
    """Match a typed code against the courses this account actually has.

    Exact first, then letters-as-a-prefix -- which is what makes "cpsc 210" find
    "CPSC_V 210" without a hardcoded list of campus suffixes. An ambiguous
    prefix resolves to nothing rather than guessing: filing a lab against the
    wrong course is worse than filing it against none.
    """
    wanted = code_parts(typed)
    if wanted is None:
        return None

    wanted_letters, wanted_number = wanted
    courses = db.query(CourseModel).filter(CourseModel.user_id == user_id).all()

    exact: list[CourseModel] = []
    prefixed: list[CourseModel] = []

    for course in courses:
        parts = code_parts(course.code)
        if parts is None:
            continue
        letters, number = parts
        if number != wanted_number:
            continue
        if letters == wanted_letters:
            exact.append(course)
        elif letters.startswith(wanted_letters):
            prefixed.append(course)

    if len(exact) == 1:
        return exact[0]
    # Only an unambiguous prefix counts. Two courses matching means the student
    # has to say which, and the code stays visible in the title so they can.
    if not exact and len(prefixed) == 1:
        return prefixed[0]
    return None


def build_preview(db: Session, user_id: uuid.UUID, text: str) -> QuickCapturePreview | None:
    """Read one line and say what it would create."""
    if not user_exists(db, user_id):
        return None

    parsed = parse(text)
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
    """Create the task one line describes.

    Goes through the same preview the client showed, so what is created is
    exactly what was on screen -- two readings of the same text could otherwise
    drift apart between the keystroke and the submit.
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
