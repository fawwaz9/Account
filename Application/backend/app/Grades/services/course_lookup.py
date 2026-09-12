"""Finding the course a student means from the code they typed.

Lives in Grades because that is what it looks up. It was written inside quick
capture, which was the right place when Tasks was the only caller; it now has
three (quick capture, the omnibox, and tagging an expense to a course), and a
course lookup reached for from Finances should not have to import Tasks to get
it. Same move as grade_tasks.py -> grade_schedule.py.
"""

import re
import uuid

from sqlalchemy.orm import Session

from app._database.models import CourseModel


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
