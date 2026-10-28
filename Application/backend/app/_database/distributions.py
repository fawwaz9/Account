"""The recount of opted-in grades into the sealed `grade_distributions` table.

On Postgres it is one call to the definer function
`account_recount_grade_distributions`, the only writer of a table the app role can
neither read nor write. On SQLite, which has no row security, `recount` rebuilds the
same counts with plain queries; the tests run both.
"""
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    COHORT_FLOOR, CourseModel, GradeDistributionModel, TermReviewModel, UserModel, utc_now,
)


def bucket_of(grade: float) -> int:
    """Return the lower bound of the five-point band a grade falls in.

    Args:
        grade: Percentage grade.

    Returns:
        0 for anything below 50, otherwise 50, 55 ... 95; 100 and bonus above it land
        in 95.
    """
    if grade < 50:
        return 0
    return min(95, int(grade // 5) * 5)


def _grade(course: CourseModel) -> float | None:
    """Return the final grade if recorded, else the average if above 0, else None."""
    if course.final_grade and course.final_grade > 0:
        return course.final_grade
    if course.average and course.average > 0:
        return course.average
    return None


def recount(db: Session) -> int:
    """Rebuild the grade distributions from scratch from every opted-in term review.

    Counts each contributing review's grade into its course-term's band, skipping
    skipped reviews, transfer credit, accounts being deleted and reviews without a
    course key or term code, and writes nothing for a course-term with fewer than
    `COHORT_FLOOR` contributions.

    Args:
        db: Open database session; needs no acting user.

    Returns:
        The number of band rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
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
