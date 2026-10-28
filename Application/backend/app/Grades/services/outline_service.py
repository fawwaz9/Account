"""Course outlines shared between students (Phase 3 item 2, D12).

A student offers their own course's outline: its weights and its assessments' names,
categories and due dates, never a score or a note. The owner approves offers with
`scripts/outline_review.py`, which copies them into the shared-read
`shared_outlines`; a classmate in the same course and term can then fill an empty
course from it, and change anything after. Nothing here reads another user's rows.
"""
import uuid

from sqlalchemy.orm import Session

from app._database.models import CourseModel, GradeModel, OutlineOfferModel, SharedOutlineModel, utc_now
from app.Grades.schemas.grade import GradeCreate
from app.Grades.schemas.outline import Outline, OutlineAssessment, OutlineOffer, OutlineStatus, SharedOutline
from app.Grades.services.grade_service import add_grades_bulk, update_category_weights
from app.Grades.services.term_review_service import course_key_of, term_code_of
from app.Grades.utils.enums import GradeCategory, GradeSchedule
from app.shared.dates import user_for

#: Exams are calendar blocks, the rest tasks; the syllabus intake's rule.
EXAM_CATEGORIES = {GradeCategory.MIDTERM, GradeCategory.FINAL}
#: An outline's assessments are added unmarked, out of this.
OUTLINE_MAX_SCORE = 100.0


class OutlineError(ValueError):
    """Raised when an outline can't be offered or applied; the message says why."""
    pass


def _own(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    """Return the caller's course, or None when it is missing or someone else's."""
    return db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()


def build_outline(course: CourseModel) -> Outline:
    """Return a course's outline: its weights above 0 and every assessment, unscored.

    Args:
        course: The course, with its weights and grades.

    Returns:
        The outline, assessments by due date (undated last) then name, at most 60.
    """
    grades = sorted(course.grades, key=lambda g: (g.due_date is None, g.due_date or 0, g.name))
    return Outline(
        weights={GradeCategory(c): w for c, w in course.category_weights.items() if w > 0},
        assessments=[OutlineAssessment(name=g.name, category=GradeCategory(g.category), due_date=g.due_date)
                     for g in grades[:60]],
    )


def _shared_for(db: Session, key: str | None, term: str | None) -> SharedOutlineModel | None:
    """Return the reviewed outline for a course and term, or None."""
    if key is None or term is None:
        return None
    return db.query(SharedOutlineModel).filter_by(course_key=key, term_code=term).first()


def _blocked(course: CourseModel, key: str | None, term: str | None) -> str | None:
    """Return why a course's outline can't be offered, or None when it can."""
    if course.transfer_credit:
        return "Transfer credit has no outline to share."
    if key is None:
        return "This course's code isn't a course code, so classmates couldn't find its outline."
    if term is None:
        return "Set the year your first year began in Settings, so the outline can be filed under its term."
    if not any(weight > 0 for weight in course.category_weights.values()):
        return "Give the course its category weights first."
    return None


def status(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> OutlineStatus | None:
    """Return what the caller can do with outlines on one of their courses.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The status; None when the course is missing or another user's.
    """
    course = _own(db, user_id, course_id)
    if course is None:
        return None
    user = user_for(db, user_id)
    key = None if course.transfer_credit else course_key_of(db, course)
    term = term_code_of(course, user.first_year_calendar_year if user else None)
    blocked = _blocked(course, key, term)
    offer = course.outline_offer
    shared = _shared_for(db, key, term)
    has_grades = db.query(GradeModel.id).filter(GradeModel.course_id == course.id).first() is not None
    return OutlineStatus(
        course_key=key, term_code=term, can_offer=blocked is None, offer_blocked=blocked,
        offer=OutlineOffer(status=offer.status, created_at=offer.created_at) if offer else None,
        shared=SharedOutline(outline=Outline.model_validate(shared.outline), approved_at=shared.approved_at)
        if shared else None,
        can_apply=shared is not None and not has_grades,
    )


def offer(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> OutlineStatus | None:
    """Offer this course's outline for review, replacing any earlier offer of it.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The status after offering; None when the course is missing or another user's.

    Raises:
        OutlineError: If the course is transfer credit, its code isn't a course code,
            its term is unknown, or it has no weights.

    Note:
        Commits. An offer reaches nobody until the owner approves it.
    """
    course = _own(db, user_id, course_id)
    if course is None:
        return None
    user = user_for(db, user_id)
    key = None if course.transfer_credit else course_key_of(db, course)
    term = term_code_of(course, user.first_year_calendar_year if user else None)
    blocked = _blocked(course, key, term)
    if blocked:
        raise OutlineError(blocked)
    outline = build_outline(course).model_dump(mode="json")
    row = course.outline_offer
    if row is None:
        row = OutlineOfferModel(user_id=user_id, course_id=course.id)
        db.add(row)
    row.course_key, row.term_code, row.outline = key, term, outline
    row.status, row.created_at, row.reviewed_at = "pending", utc_now(), None
    db.commit()
    return status(db, user_id, course_id)


def withdraw(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    """Take back the caller's offer of a course's outline.

    An outline already approved stays shared: it is world knowledge by then.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        True if an offer was deleted; False when there was none, or the course is
        missing or another user's.

    Note:
        Commits.
    """
    course = _own(db, user_id, course_id)
    if course is None or course.outline_offer is None:
        return False
    db.delete(course.outline_offer)
    db.commit()
    return True


def apply(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> OutlineStatus | None:
    """Fill an empty course from the reviewed outline for its course and term.

    Sets the course's weights to the outline's (every other category to 0) and adds
    each assessment unmarked, an exam as a calendar block and the rest as tasks.
    Everything stays the student's own to change.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The status after applying; None when the course is missing or another user's.

    Raises:
        OutlineError: If there is no reviewed outline for the course and term, or the
            course already has grades.

    Note:
        Two commits: the weights, then every assessment together. The grades check
        comes first, so a filled course is never written over.
    """
    found = status(db, user_id, course_id)
    if found is None:
        return None
    if found.shared is None:
        raise OutlineError("There's no reviewed outline for this course and term yet.")
    if not found.can_apply:
        raise OutlineError("This course already has grades; an outline only fills an empty course.")
    outline = found.shared.outline
    update_category_weights(db, user_id, course_id, {c: outline.weights.get(c, 0.0) for c in GradeCategory})
    add_grades_bulk(db, user_id, course_id, [
        GradeCreate(name=a.name, category=a.category, max_score=OUTLINE_MAX_SCORE, due_date=a.due_date,
                    schedule_as=GradeSchedule.EVENT if a.category in EXAM_CATEGORIES else GradeSchedule.TASK)
        for a in outline.assessments
    ])
    return status(db, user_id, course_id)
