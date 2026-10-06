"""Linking your courses to the shared catalogue (Phase 2 item 3, D11).

The catalogue is read here and written nowhere: under row-level security the
API's role cannot, and the owner-run review script is the only writer (D9).

**The link is computed, not stored.** A course with no choice of yours is
matched by campus and code each time it is read, so it links itself as soon
as the catalogue gains it -- which matters, because the catalogue starts empty
and grows only as reviews are approved. What is stored is only what you
decided: a course picked by hand, or "none". Either one beats the match.

Nothing here reads or changes a grade, an average or a credit. The link is a
pointer for prerequisites to hang on, and tests/test_catalogue_link.py holds
every grade figure still across linking and unlinking.
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
SEARCH_LIMIT = 20


class CatalogueError(ValueError):
    """A choice that names no catalogue course."""


@dataclass(frozen=True)
class CatalogueKey:
    campus: str | None
    subject: str
    number: str


def key_of(code: str) -> CatalogueKey | None:
    """A course code as the catalogue keys it. None when it is not a code.

    An unknown suffix ("CPSC_X 110") is not a campus, so it reads as none and
    the match then has to be unambiguous without it.
    """
    match = CODE.match(code.strip())
    if match is None:
        return None
    subject, suffix, number = match.groups()
    campus = CAMPUS_SUFFIX.get(suffix.upper()) if suffix else None
    return CatalogueKey(campus=campus, subject=subject.upper(), number=number.upper())


def match(db: Session, code: str) -> CatalogueCourseModel | None:
    """The one catalogue course this code names, or None.

    None also when two campuses offer the same code and the code does not say
    which: linking the wrong one would show the wrong prerequisites, and no
    link at least says nothing (course_lookup's rule).
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
    return db.query(CourseModel).filter(
        CourseModel.id == course_id, CourseModel.user_id == user_id
    ).first()


def get_link(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CatalogueLink | None:
    course = _owned(db, user_id, course_id)
    return None if course is None else link_of(db, course)


def set_link(db: Session, user_id: uuid.UUID, course_id: uuid.UUID,
             choice: CatalogueChoice) -> CatalogueLink | None:
    """Record your decision. None if the course is not yours."""
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


def search(db: Session, text: str) -> list[CatalogueCourseModel]:
    """Catalogue courses whose code starts like ``text``: "cpsc", "cpsc 2", "CPSC_V 221".

    Prefix only, on the subject and then the number, which is how people type
    a code. Anything else matches nothing rather than everything.
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
