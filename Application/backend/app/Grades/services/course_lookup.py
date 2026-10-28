"""Finding the course a student means from the code they typed.

In Grades because a course is what it looks up; quick capture, the omnibox and
tagging an expense to a course all call it.
"""

import re
import uuid

from sqlalchemy.orm import Session

from app._database.models import CourseModel


CODE_PARTS = re.compile(r"^([A-Za-z_]+)\s*(\d+[A-Za-z]?)$")
"""Letters (underscores allowed) then digits with an optional letter: a loose code."""


def code_parts(code: str) -> tuple[str, str] | None:
    """Return a code as (letters, number), ignoring case, spacing and underscores.

    Args:
        code: A typed or stored code, such as "statv201" or "STAT_V 201".

    Returns:
        The upper-cased letters with underscores removed and the upper-cased number,
        or None when the text is not letters followed by digits.
    """
    match = CODE_PARTS.match(code.strip())
    if match is None:
        return None
    return match.group(1).upper().replace("_", ""), match.group(2).upper()


def resolve_course(db: Session, user_id: uuid.UUID, typed: str) -> CourseModel | None:
    """Return the student's course a typed code means, or None when it is unclear.

    An exact match on letters and number wins; otherwise a single course whose letters
    start with the typed ones ("cpsc 210" finds "CPSC_V 210"). Two candidates resolve
    to nothing rather than a guess.

    Args:
        db: Open database session.
        user_id: Whose courses to search.
        typed: The code as typed.

    Returns:
        The one matching course, or None.
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
