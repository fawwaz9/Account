"""The daily recount of anonymous grade contributions (Phase 2 item 13, D25).

On Postgres it is one definer function, ``account_recount_grade_distributions``,
which reads across users and writes only bucket counts into a table the API's
role can't read (rls.SEALED_TABLES). On SQLite, which has no row security,
the same rebuild is a plain query written to mean exactly what the function
means; the tests run both.
"""
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    COHORT_FLOOR, CourseModel, GradeDistributionModel, TermReviewModel, UserModel, utc_now,
)


def bucket_of(grade: float) -> int:
    """The band's lower bound: 0 below 50, then 50, 55, ... 95 (100 and any
    bonus above it land in 95)."""
    if grade < 50:
        return 0
    return min(95, int(grade // 5) * 5)


def _grade(course: CourseModel) -> float | None:
    """The same rule as the function: the final grade, else the running average."""
    if course.final_grade and course.final_grade > 0:
        return course.final_grade
    if course.average and course.average > 0:
        return course.average
    return None


def recount(db: Session) -> int:
    """Rebuild the sealed table from scratch. Returns how many rows it wrote."""
    if db.get_bind().dialect.name == "postgresql":
        written = db.execute(text("SELECT account_recount_grade_distributions()")).scalar()
        db.commit()
        return int(written or 0)
    db.query(GradeDistributionModel).delete(synchronize_session=False)
    rows = (
        db.query(TermReviewModel, CourseModel)
        .join(CourseModel, CourseModel.id == TermReviewModel.course_id)
        .join(UserModel, UserModel.id == TermReviewModel.user_id)
        .filter(TermReviewModel.contribute_grade.is_(True), TermReviewModel.skipped.is_(False),
                UserModel.deleted_at.is_(None), CourseModel.transfer_credit.is_(False),
                TermReviewModel.course_key.isnot(None), TermReviewModel.term_code.isnot(None))
        .all()
    )
    counted = Counter()
    for review, course in rows:
        grade = _grade(course)
        if grade is not None:
            counted[(review.course_key, review.term_code, bucket_of(grade))] += 1
    per_group = Counter()
    for (key, term, _bucket), n in counted.items():
        per_group[(key, term)] += n
    now = utc_now()
    written = 0
    for (key, term, bucket), n in counted.items():
        if per_group[(key, term)] >= COHORT_FLOOR:
            db.add(GradeDistributionModel(course_key=key, term_code=term, bucket=bucket, contributors=n,
                                          computed_at=now))
            written += 1
    db.commit()
    return written
