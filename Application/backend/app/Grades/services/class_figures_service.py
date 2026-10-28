"""What other students' shared answers say about one of the caller's own courses.

Reads the sealed aggregates only through `_database/aggregates.py`, whose functions
apply each figure's floor, and only for the key the caller's own course is counted
under. Nothing here reads another user's rows. See Ideas/overhaul/Phase 3, D11.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app._database import aggregates
from app._database.distributions import bucket_of
from app._database.models import COHORT_FLOOR, CourseModel
from app.Grades.schemas.class_figures import (
    ClassFigures, CourseIntelOut, GradeBandOut, OfficeHourSlotOut, TermDistribution,
)
from app.Grades.services.office_hours_service import reading
from app.Grades.services.term_review_service import course_key_of
from app.Grades.utils.terms import course_result_grade

#: What each term code's half is called, and the years to add to the code's year.
TERM_NAMES = {"W1": ("Fall", 0), "W2": ("Winter", 1), "S1": ("Spring", 0), "S2": ("Summer", 0)}


def term_label(code: str) -> str:
    """Return a term code as read, such as "Fall 2025" for "2025W1".

    Args:
        code: A term code.

    Returns:
        The term's name and calendar year; the code itself when it can't be read.
    """
    name = TERM_NAMES.get(code[4:])
    if name is None or not code[:4].isdigit():
        return code
    return f"{name[0]} {int(code[:4]) + name[1]}"


def median_bucket(bands: list[aggregates.Band]) -> int:
    """Return the band holding the middle grade of a term's bands.

    Args:
        bands: One term's bands, lowest first; at least one.

    Returns:
        The lower bound of the band where the running count first reaches half.
    """
    total = sum(band.contributors for band in bands)
    running = 0
    for band in bands:
        running += band.contributors
        if running * 2 >= total:
            return band.bucket
    return bands[-1].bucket


def _rounded(value: float | None, places: int = 1):
    """Return a figure rounded for showing, or None."""
    return None if value is None else round(value, places)


def intel_out(intel: aggregates.CourseIntel | None) -> CourseIntelOut | None:
    """Return the course figures as sent, or None when none has reached the floor.

    Args:
        intel: The figures as read through the floor.

    Returns:
        Hours and ratings to one decimal and the yes share as a whole percentage;
        None when there is no row or every figure is below the floor.
    """
    if intel is None or all(n is None for n in (intel.hours_answers, intel.difficulty_answers,
                                                 intel.clarity_answers, intel.again_answers)):
        return None
    return CourseIntelOut(
        hours_answers=intel.hours_answers, hours_median=_rounded(intel.hours_median),
        difficulty_answers=intel.difficulty_answers, difficulty_mean=_rounded(intel.difficulty_mean),
        clarity_answers=intel.clarity_answers, clarity_mean=_rounded(intel.clarity_mean),
        again_answers=intel.again_answers,
        again_share=None if intel.again_share is None else round(intel.again_share),
    )


def _utc_today():
    """Return today's date in UTC, the clock the Postgres read functions use."""
    return datetime.now(timezone.utc).date()


def class_figures(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> ClassFigures | None:
    """Return the shared figures for one of the caller's courses.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The figures, empty where nothing has reached its floor; None when the course is
        missing or another user's.
    """
    course = db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()
    if course is None:
        return None
    grade = course_result_grade(course)
    key = None if course.transfer_credit else course_key_of(db, course)
    distributions = []
    intel = None
    office_hours = []
    if key is not None:
        intel = intel_out(aggregates.course_intel(db, key))
        office_hours = [
            OfficeHourSlotOut(weekday=slot.weekday, hour=slot.hour, people=slot.people, reading=reading(slot))
            for slot in aggregates.office_hours(db, key)
        ]
        by_term: dict[str, list[aggregates.Band]] = {}
        for band in aggregates.grade_distribution(db, key, _utc_today()):
            by_term.setdefault(band.term_code, []).append(band)
        for code, bands in by_term.items():
            distributions.append(TermDistribution(
                term_code=code,
                term_label=term_label(code),
                contributors=sum(band.contributors for band in bands),
                median_bucket=median_bucket(bands),
                bands=[GradeBandOut(bucket=band.bucket, contributors=band.contributors) for band in bands],
            ))
    return ClassFigures(
        course_key=key,
        floor=COHORT_FLOOR,
        distributions=distributions,
        your_grade=grade,
        your_bucket=bucket_of(grade) if grade is not None else None,
        intel=intel,
        office_hours=office_hours,
    )
