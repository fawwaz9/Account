"""Linking a student's courses to the shared catalogue, which is only read here.

A course with no choice of the student's is matched by campus and code on every
read, so it links itself once the catalogue gains it; only a hand-picked course or
"none" is stored. Nothing here touches a grade, an average or a credit.
"""
import re
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app._database.models import CatalogueCourseModel, CourseModel
from app.Grades.schemas.catalogue import CatalogueChoice, CatalogueLink

#: The campus a code's suffix names: "CPSC_V 110" is Vancouver, "COSC_O 111"
#: Okanagan. A code with no suffix names no campus.
CAMPUS_SUFFIX = {"V": "UBCV", "O": "UBCO"}
CODE = re.compile(r"^([A-Za-z]{2,5})(?:_([A-Za-z]))?\s*(\d{3}[A-Za-z]?)$")
"""A full course code with an optional campus suffix captured separately."""
SEARCH_LIMIT = 20


class CatalogueError(ValueError):
    """Raised when a chosen catalogue course does not exist."""


@dataclass(frozen=True)
class CatalogueKey:
    """A course code as the catalogue keys it.

    Attributes:
        campus: "UBCV" or "UBCO" from a code's suffix; None when the code names no
            campus.
        subject: Upper-cased subject, such as "CPSC".
        number: Upper-cased number with any letter suffix, such as "110".
    """
    campus: str | None
    subject: str
    number: str


def key_of(code: str) -> CatalogueKey | None:
    """Return a course code as the catalogue keys it, or None when it is not a code.

    Args:
        code: A code such as "CPSC_V 110"; an unknown suffix reads as no campus.

    Returns:
        The campus, subject and number, or None.
    """
    match = CODE.match(code.strip())
    if match is None:
        return None
    subject, suffix, number = match.groups()
    campus = CAMPUS_SUFFIX.get(suffix.upper()) if suffix else None
    return CatalogueKey(campus=campus, subject=subject.upper(), number=number.upper())


def match(db: Session, code: str) -> CatalogueCourseModel | None:
    """Return the one catalogue course a code names, or None.

    Args:
        db: Open database session.
        code: The student's course code.

    Returns:
        The catalogue row when exactly one matches; None for no match, an unreadable
        code, or the same code on both campuses with no suffix to choose.
    """
    key = key_of(code)
    if key is None:
        return None
    query = db.query(CatalogueCourseModel).filter(
        CatalogueCourseModel.subject == key.subject, CatalogueCourseModel.number == key.number
    )
    if key.campus is not None:
        query = query.filter(CatalogueCourseModel.campus == key.campus)
    rows = query.limit(2).all()
    return rows[0] if len(rows) == 1 else None


def link_of(db: Session, course: CourseModel) -> CatalogueLink:
    """Return how a course links to the catalogue: chosen, none, matched or not found.

    A chosen course whose catalogue row has gone falls back to matching.

    Args:
        db: Open database session.
        course: The student's course row.

    Returns:
        The link and, for "chosen" and "matched", the catalogue course.
    """
    if course.catalogue_unlinked:
        return CatalogueLink(how="none_chosen")
    if course.catalogue_course_id is not None:
        chosen = db.get(CatalogueCourseModel, course.catalogue_course_id)
        if chosen is not None:
            return CatalogueLink(how="chosen", course=chosen)
        # The catalogue row has gone; the choice means nothing now, so the
        # course falls back to matching rather than linking to nothing.
    matched = match(db, course.code)
    return CatalogueLink(how="matched" if matched else "not_found", course=matched)


def _owned(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    """Return the caller's course with this id, or None."""
    return db.query(CourseModel).filter(
        CourseModel.id == course_id, CourseModel.user_id == user_id
    ).first()


def get_link(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CatalogueLink | None:
    """Return a course's catalogue link.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The link, or None when the course is missing or another user's.
    """
    course = _owned(db, user_id, course_id)
    return None if course is None else link_of(db, course)


def set_link(db: Session, user_id: uuid.UUID, course_id: uuid.UUID,
             choice: CatalogueChoice) -> CatalogueLink | None:
    """Record the student's catalogue choice: automatic, a chosen course, or none.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        choice: The mode, and the catalogue course for "chosen".

    Returns:
        The resulting link, or None when the course is missing or another user's.

    Raises:
        CatalogueError: If the chosen catalogue course does not exist.

    Note:
        Commits.
    """
    course = _owned(db, user_id, course_id)
    if course is None:
        return None
    if choice.mode == "chosen":
        if db.get(CatalogueCourseModel, choice.catalogue_course_id) is None:
            raise CatalogueError("That course is not in the catalogue")
        course.catalogue_course_id, course.catalogue_unlinked = choice.catalogue_course_id, False
    elif choice.mode == "none":
        course.catalogue_course_id, course.catalogue_unlinked = None, True
    else:
        course.catalogue_course_id, course.catalogue_unlinked = None, False
    db.commit()
    return link_of(db, course)


SEARCH = re.compile(r"^([A-Za-z]{0,5})(?:_([A-Za-z]))?\s*(\d{0,3}[A-Za-z]?)$")
"""A code prefix as typed in the search box: letters, an optional suffix, digits."""


def search(db: Session, text: str) -> list[CatalogueCourseModel]:
    """Return catalogue courses whose code starts like the text, such as "cpsc 2".

    Prefix match on the subject, then the number, filtered by campus when a known
    suffix is typed; anything else matches nothing.

    Args:
        db: Open database session.
        text: What the student typed.

    Returns:
        Up to `SEARCH_LIMIT` courses ordered by subject, number and campus; empty when
        the text is not a code prefix.
    """
    found = SEARCH.match(text.strip())
    if found is None:
        return []
    subject, suffix, number = found.groups()
    query = db.query(CatalogueCourseModel)
    if subject:
        query = query.filter(CatalogueCourseModel.subject.startswith(subject.upper(), autoescape=True))
    if number:
        query = query.filter(CatalogueCourseModel.number.startswith(number.upper(), autoescape=True))
    if suffix and suffix.upper() in CAMPUS_SUFFIX:
        query = query.filter(CatalogueCourseModel.campus == CAMPUS_SUFFIX[suffix.upper()])
    return (
        query.order_by(CatalogueCourseModel.subject, CatalogueCourseModel.number, CatalogueCourseModel.campus)
        .limit(SEARCH_LIMIT)
        .all()
    )
