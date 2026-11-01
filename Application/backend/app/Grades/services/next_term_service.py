"""The next-term planner: candidate courses, past students' figures added up (item 12).

Reads the shared catalogue and the course figures through the floor, exactly as
the course page's "From past students" does (Phase 3 D11), so a figure below the
floor never shows here either. Nothing is written. Professor ratings are a link
out, built in the browser from a name you type; nothing is fetched from elsewhere
(§13.6: link out, never scrape).
"""

import uuid

from sqlalchemy.orm import Session

from app._database import aggregates
from app._database.models import COHORT_FLOOR, CatalogueCourseModel
from app.Grades.schemas.next_term import NextTermCourse, NextTermIn, NextTermPlan
from app.Grades.services.class_figures_service import intel_out


def next_term(db: Session, user_id: uuid.UUID, body: NextTermIn) -> NextTermPlan:
    """Return the candidates with their figures and the combination's totals.

    Args:
        db: Request-scoped database session, acting as the caller.
        user_id: The verified caller's id; the figures read are shared aggregates.
        body: The candidate catalogue courses.

    Returns:
        The plan.

    Raises:
        ValueError: If an id repeats or is not in the catalogue.
    """
    ids = body.catalogue_ids
    if len(set(ids)) != len(ids):
        raise ValueError("Each course can be in the plan once")
    rows = {row.id: row for row in db.query(CatalogueCourseModel).filter(CatalogueCourseModel.id.in_(ids)).all()}
    if len(rows) != len(ids):
        raise ValueError("Every course has to come from the catalogue")

    courses: list[NextTermCourse] = []
    for catalogue_id in ids:
        row = rows[catalogue_id]
        key = f"{row.campus} {row.subject} {row.number}"
        courses.append(NextTermCourse(
            catalogue_id=row.id, code=f"{row.subject} {row.number}", campus=row.campus, title=row.title,
            credits=row.credits, intel=intel_out(aggregates.course_intel(db, key)),
        ))

    hours = [c.intel.hours_median for c in courses if c.intel and c.intel.hours_median is not None]
    difficulty = [c.intel.difficulty_mean for c in courses if c.intel and c.intel.difficulty_mean is not None]
    missing = [c.code for c in courses if not (c.intel and c.intel.hours_median is not None)]

    assumptions = [
        f"Hours are the median weekly hours past students reported, shown once {COHORT_FLOOR} or more answered.",
        "Your own hours will differ: these are other people's terms, with their own loads and instructors.",
    ]
    if missing:
        assumptions.append("Courses without a figure yet are left out of the total, not counted as zero.")

    return NextTermPlan(
        courses=courses,
        total_hours=round(sum(hours), 1) if hours else None,
        courses_with_hours=len(hours),
        total_credits=float(sum(c.credits or 0.0 for c in courses)),
        mean_difficulty=round(sum(difficulty) / len(difficulty), 1) if difficulty else None,
        missing=missing,
        floor=COHORT_FLOOR,
        assumptions=assumptions,
    )
