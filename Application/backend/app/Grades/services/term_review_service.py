"""End-of-term reviews: what you thought of a finished course, and whether
to add your grade to its distribution (Phase 2 item 13, D25).

Everything here reads and writes only the caller's own rows. The cross-user
step is the daily recount (``distributions``), which no request triggers.
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
    pass


def term_code_of(course: CourseModel, first_year: int | None) -> str | None:
    """UBC's name for the term: "2025W1" is Fall 2025, "2025W2" the Winter after."""
    session = session_of(course.semester, course.year, first_year)
    part = TERM_PART.get(course.semester or "")
    return f"{session}{part}" if session and part else None


def course_key_of(db: Session, course: CourseModel) -> str | None:
    """"UBCV CPSC 221": the catalogue's course when the course is linked to
    one, otherwise its own code (with no campus when the code names none)."""
    linked = link_of(db, course).course
    if linked is not None:
        return f"{linked.campus} {linked.subject} {linked.number}"
    key = key_of(course.code or "")
    if key is None:
        return None
    return " ".join(part for part in (key.campus, key.subject, key.number) if part)


def _window(course: CourseModel, first_year: int | None, today: date) -> tuple[date, str] | None:
    """When this course's term ended and its label, if it is in its asking window."""
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
    return utc_now() <= review.created_at + timedelta(days=EDIT_DAYS)


def _out(review: TermReviewModel) -> TermReview:
    return TermReview(
        hours_per_week=review.hours_per_week, difficulty=review.difficulty, clarity=review.clarity,
        would_take_again=review.would_take_again, contribute_grade=review.contribute_grade,
        skipped=review.skipped, created_at=review.created_at, answers_editable=_editable(review),
    )


def overview(db: Session, user_id: uuid.UUID) -> TermReviews | None:
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
    user = user_for(db, user_id)
    course = db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()
    if user is None or course is None:
        return None, None
    return user, course


def save(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, data: TermReviewIn) -> TermReview | None:
    """None when the course is not yours. ReviewError when it can't be saved."""
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
    """Don't ask about this course again. Only for one not yet answered."""
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
    """Delete your review, contribution and all. The next recount drops it."""
    gone = db.query(TermReviewModel).filter(
        TermReviewModel.user_id == user_id, TermReviewModel.course_id == course_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0
