"""The course-drop simulator: one course out of this term, before and after (item 11).

The simulator pattern on engines that already exist: the dashboard's own
averaging functions, run on the course list with and without the course, and the
course's tuition share from the tuition service. Academic to money only, so the
silo holds (§13.6). Nothing is written. Information with disclaimers, never
advice: full-time status can affect loans, housing and study permits (§15).
"""

import uuid

from sqlalchemy.orm import Session

from app.Finances.services.tuition_service import course_cost
from app.Grades.schemas.drop import DEFAULT_FULL_TIME_CREDITS, DropFigures, DropPreview
from app.Grades.services.course_service import get_all_courses
from app.Grades.services.dash_services import (
    averages_including_this_term,
    calculate_cgpa,
    calculate_cumulative_average,
    counts_toward_credits,
    is_graded,
    plain_average,
)
from app.Grades.utils.terms import CURRENT
from app.Users.services.user_service import get_preferences, get_user


def term_credits(courses) -> float:
    """Return the credits taken this term: current courses, not archived, not transfer.

    Args:
        courses: Course rows with `term_bucket` set.

    Returns:
        The credits.
    """
    return float(sum(
        c.credits or 0.0 for c in courses
        if c.term_bucket == CURRENT and counts_toward_credits(c) and is_graded(c)
    ))


def figures(courses, gpa_scale_enabled: bool) -> DropFigures:
    """Return the figures a drop moves, for one course list.

    Args:
        courses: Course rows with `term_bucket` set.
        gpa_scale_enabled: The user's GPA-scale setting.

    Returns:
        The figures, through the dashboard's own functions.
    """
    current = [c for c in courses if c.term_bucket == CURRENT and is_graded(c)]
    semester = plain_average(current)
    with_term, cgpa_with_term = averages_including_this_term(courses, gpa_scale_enabled)
    return DropFigures(
        semester_average=semester if semester else None,
        cumulative_average=calculate_cumulative_average(courses),
        cgpa=calculate_cgpa(courses) if gpa_scale_enabled else None,
        cumulative_average_including_term=with_term,
        cgpa_including_term=cgpa_with_term,
        term_credits=term_credits(courses),
    )


def drop_preview(
    db: Session,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    full_time_credits: float = DEFAULT_FULL_TIME_CREDITS,
) -> DropPreview | None:
    """Return what dropping one of this term's courses would change.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course to leave out.
        full_time_credits: Credits a term below which full-time status may be lost.

    Returns:
        Before and after figures, the full-time check, the tuition share and every
        warning; None when the course is missing or another user's.

    Raises:
        ValueError: If the course is not in the current term.
    """
    user = get_user(db, user_id)
    if user is None:
        return None
    courses = get_all_courses(db, user_id)
    target = next((c for c in courses if c.id == course_id), None)
    if target is None:
        return None
    if target.term_bucket != CURRENT:
        raise ValueError("Only a course in the current term can be dropped here")

    scale = get_preferences(user).gpa_scale_enabled
    remaining = [c for c in courses if c.id != course_id]
    before = figures(courses, scale)
    after = figures(remaining, scale)

    cost = course_cost(db, user_id, course_id)
    tuition_share = cost.tuition_share if cost and cost.cost_per_credit > 0 else None

    below = after.term_credits < full_time_credits
    was = before.term_credits >= full_time_credits
    warnings: list[str] = []
    if below:
        warnings.append(
            f"This term would fall to {after.term_credits:g} credits, under the {full_time_credits:g} you set "
            "as full-time. Full-time status can decide student loans and grants, residence and housing "
            "eligibility, scholarships, and a study permit's conditions. Check each of yours before dropping."
        )
        if full_time_credits < 12:
            warnings.append("Some loans and awards use a higher bar, often 12 credits or 60% of a full load.")
    if tuition_share is not None:
        warnings.append(
            f"This course's tuition was about ${tuition_share:,.2f}. How much comes back depends on the date "
            "you drop: before the refund deadline usually most of it, after it often nothing."
        )
    else:
        warnings.append("No tuition is recorded for this term, so no refund can be estimated.")
    warnings.append("After the drop deadline a withdrawal can stay on your transcript as a W.")

    return DropPreview(
        course_id=target.id,
        course_code=target.code,
        credits=target.credits or 0.0,
        before=before,
        after=after,
        full_time_credits=full_time_credits,
        below_full_time=below,
        was_full_time=was,
        tuition_share=tuition_share,
        warnings=warnings,
        disclaimers=[
            "Information, not advice. Your school's calendar and your funders' rules decide.",
            "The averages use the same rules as your grades page; nothing is changed until you drop.",
        ],
    )
