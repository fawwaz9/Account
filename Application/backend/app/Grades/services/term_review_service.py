"""End-of-term reviews of finished courses, and the opt-in to add a grade to the counts.

Everything here reads and writes the caller's own rows only. A course is asked about
from `ASK_AFTER_DAYS` to `ASK_UNTIL_DAYS` after its term ends; answers lock after
`EDIT_DAYS`, while the grade opt-in stays changeable. The cross-user recount lives
in `_database/distributions.py`.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import CourseModel, TermReviewModel, utc_now
from app.Grades.schemas.term_review import ReviewCourse, TermReview, TermReviewIn, TermReviews
from app.Grades.services.catalogue_service import key_of, link_of
from app.Grades.services.prerequisite_service import session_of
from app.Grades.utils.terms import course_result_grade, term_dates
from app.shared.dates import user_for, user_today

#: Grades take about two weeks to post after a term ends.
ASK_AFTER_DAYS = 14
#: Long enough to catch a term's courses, short enough never to ask about old ones.
ASK_UNTIL_DAYS = 180
#: How long answers stay changeable: post-final feelings, then reflection.
EDIT_DAYS = 14

#: Which half of a session a semester is.
TERM_PART = {"Fall": "1", "Winter": "2", "Spring": "1", "Summer": "2"}


class ReviewError(ValueError):
    """Raised when a review cannot be saved or skipped; the message says why."""
    pass


def term_code_of(course: CourseModel, first_year: int | None) -> str | None:
    """Return UBC's code for a course's term, such as "2025W1" for Fall 2025, or None.

    Args:
        course: The course row.
        first_year: The first-year anchor.

    Returns:
        The session plus the half ("1" or "2"); None when the anchor or term is unknown.
    """
    session = session_of(course.semester, course.year, first_year)
    part = TERM_PART.get(course.semester or "")
    return f"{session}{part}" if session and part else None


def course_key_of(db: Session, course: CourseModel) -> str | None:
    """Return the key a course's grades are counted under, such as "UBCV CPSC 221".

    Args:
        db: Open database session.
        course: The course row.

    Returns:
        The linked catalogue course's campus, subject and number; otherwise the course's
        own code read as a key (no campus when it names none); None when the code is not
        a course code.
    """
    linked = link_of(db, course).course
    if linked is not None:
        return f"{linked.campus} {linked.subject} {linked.number}"
    key = key_of(course.code or "")
    if key is None:
        return None
    return " ".join(part for part in (key.campus, key.subject, key.number) if part)


def _window(course: CourseModel, first_year: int | None, today: date) -> tuple[date, str] | None:
    """Return (term end, label) if the course is in its review window today, else None.

    Transfer credit and undated terms are never asked about.
    """
    if course.transfer_credit:
        return None
    dates = term_dates(course.semester, course.year, first_year)
    if dates is None:
        return None
    start, end = dates
    if not (end + timedelta(days=ASK_AFTER_DAYS) <= today <= end + timedelta(days=ASK_UNTIL_DAYS)):
        return None
    return end, f"{course.semester} {start.year}"


def _editable(review: TermReviewModel) -> bool:
    """Return whether a review's answers are still inside their edit window."""
    return utc_now() <= review.created_at + timedelta(days=EDIT_DAYS)


def _out(review: TermReviewModel) -> TermReview:
    """Return a review row as the `TermReview` schema."""
    return TermReview(
        hours_per_week=review.hours_per_week, difficulty=review.difficulty, clarity=review.clarity,
        would_take_again=review.would_take_again, contribute_grade=review.contribute_grade,
        skipped=review.skipped, created_at=review.created_at, answers_editable=_editable(review),
    )


def overview(db: Session, user_id: uuid.UUID) -> TermReviews | None:
    """Return the student's courses in their review window, with any review of each.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The courses by code and how many are not yet answered or skipped; None when the
        user does not exist.
    """
    user = user_for(db, user_id)
    if user is None:
        return None
    today = user_today(db, user_id)
    reviews = {r.course_id: r for r in db.query(TermReviewModel).filter(TermReviewModel.user_id == user_id)}
    courses = []
    for course in db.query(CourseModel).filter(CourseModel.user_id == user_id).order_by(CourseModel.code):
        window = _window(course, user.first_year_calendar_year, today)
        if window is None:
            continue
        _end, label = window
        review = reviews.get(course.id)
        courses.append(ReviewCourse(
            course_id=course.id, code=course.code, name=course.name, term_label=label,
            has_grade=course_result_grade(course) is not None,
            can_contribute=(course_key_of(db, course) is not None
                            and term_code_of(course, user.first_year_calendar_year) is not None),
            review=_out(review) if review else None,
        ))
    return TermReviews(courses=courses, pending=sum(1 for c in courses if c.review is None))


def _own_course_in_window(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """Return (user, course) for the caller's course, or (None, None) if missing."""
    user = user_for(db, user_id)
    course = db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()
    if user is None or course is None:
        return None, None
    return user, course


def save(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, data: TermReviewIn) -> TermReview | None:
    """Answer, or change, the review of a finished course.

    The course key and term code are snapshotted on every save. A skipped review can be
    answered, which starts its edit window.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        data: The answers and the grade opt-in.

    Returns:
        The saved review, or None when the course is missing or another user's.

    Raises:
        ReviewError: If there is no review yet and the course is outside its window; if
            the answers changed after they locked; or if contributing is asked for a
            course with no grade, key or term.

    Note:
        Commits.
    """
    user, course = _own_course_in_window(db, user_id, course_id)
    if course is None:
        return None
    review = db.query(TermReviewModel).filter_by(user_id=user_id, course_id=course_id).first()
    if review is None and _window(course, user.first_year_calendar_year, user_today(db, user_id)) is None:
        raise ReviewError("This course isn't one to review right now.")
    answers = data.model_dump(exclude={"contribute_grade"})
    if review is not None and not review.skipped and not _editable(review):
        current = {k: getattr(review, k) for k in answers}
        if current != answers:
            raise ReviewError("Your answers have locked. You can still change whether your grade is added.")
    key = course_key_of(db, course)
    term = term_code_of(course, user.first_year_calendar_year)
    if data.contribute_grade and (course_result_grade(course) is None or key is None or term is None):
        raise ReviewError("This course has no grade, or no course code and term to count it under.")
    now = utc_now()
    if review is None:
        review = TermReviewModel(id=uuid.uuid4(), user_id=user_id, course_id=course_id, created_at=now)
        db.add(review)
    elif review.skipped:
        review.created_at = now  # answering a skipped course starts its edit window
    for field, value in answers.items():
        setattr(review, field, value)
    review.contribute_grade = data.contribute_grade
    review.skipped = False
    review.course_key, review.term_code = key, term
    review.updated_at = now
    db.commit()
    db.refresh(review)
    return _out(review)


def skip(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> TermReview | None:
    """Decline to review a course, so it is not asked about again.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The skipped review, or None when the course is missing or another user's.

    Raises:
        ReviewError: If the course was already answered, or has no review and is
            outside its window.

    Note:
        Commits.
    """
    user, course = _own_course_in_window(db, user_id, course_id)
    if course is None:
        return None
    review = db.query(TermReviewModel).filter_by(user_id=user_id, course_id=course_id).first()
    if review is not None and not review.skipped:
        raise ReviewError("You've already answered for this course. Delete the review to start again.")
    if review is None:
        if _window(course, user.first_year_calendar_year, user_today(db, user_id)) is None:
            raise ReviewError("This course isn't one to review right now.")
        review = TermReviewModel(id=uuid.uuid4(), user_id=user_id, course_id=course_id, skipped=True,
                                 created_at=utc_now(), updated_at=utc_now())
        db.add(review)
    db.commit()
    db.refresh(review)
    return _out(review)


def remove(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    """Delete the student's review of a course, grade contribution included.

    The next recount drops the contribution.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        True if a review was deleted.

    Note:
        Commits.
    """
    gone = db.query(TermReviewModel).filter(
        TermReviewModel.user_id == user_id, TermReviewModel.course_id == course_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0
