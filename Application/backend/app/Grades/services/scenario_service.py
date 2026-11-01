"""Grade scenarios: a course's projected grade under scores you choose (§13.6).

The simulator pattern on the existing grade engine. Every figure comes from
`project_course`, the same function behind the grade band and the cheapest path,
so a scenario can never disagree with them. Nothing is written.
"""

import uuid

from sqlalchemy.orm import Session

from app.Grades.schemas.scenario import GradeScenario, GradeScenarioIn, ScenarioItem
from app.Grades.services.grade_service import (
    calculate_letter_grade,
    course_grade,
    empty_weighted_categories,
    get_user_course,
    project_course,
)
from app.Grades.utils.marks import counts_toward_average


def outstanding_items(course) -> list:
    """Return a course's unmarked, counted assessments, by due date, then name.

    Args:
        course: Course with its grades loaded.

    Returns:
        The grade rows a scenario may set.
    """
    items = [
        g for g in course.grades
        if g.score is None and g.max_score > 0 and counts_toward_average(g)
    ]
    return sorted(items, key=lambda g: (g.due_date is None, g.due_date, g.name.lower()))


def scenario(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, body: GradeScenarioIn) -> GradeScenario | None:
    """Return a course's projected grade with chosen scores on its unmarked work.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        body: The assumed score for the rest, and any scores set per assessment.

    Returns:
        The projection beside the current grade and the band; None when the course is
        missing or another user's.

    Raises:
        ValueError: If `body.scores` names anything but this course's unmarked,
            counted assessments.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None

    items = outstanding_items(course)
    settable = {g.id for g in items}
    if set(body.scores) - settable:
        raise ValueError("Only this course's unmarked assessments can be given a score")

    overrides = {grade_id: percent / 100 for grade_id, percent in body.scores.items()}
    projected = project_course(course, body.assume / 100, overrides)
    empty = empty_weighted_categories(course)

    assumptions = [f"Everything you haven't set scores {body.assume:g}%."]
    if empty:
        assumptions.append(
            "Nothing is entered yet in " + ", ".join(empty)
            + f", so each counts at {body.assume:g}% whole."
        )
    if body.scores:
        assumptions.append(f"{len(body.scores)} assessment{'s' if len(body.scores) != 1 else ''} set by you.")
    assumptions.append("Marked work counts as marked; dropped work stays out.")

    return GradeScenario(
        course_id=course.id,
        current=course_grade(course),
        projected=projected,
        letter=calculate_letter_grade(course, projected),
        best=project_course(course, 1.0),
        worst=project_course(course, 0.0),
        assume=body.assume,
        items=[
            ScenarioItem(
                grade_id=g.id, name=g.name, category=g.category, max_score=g.max_score,
                due_date=g.due_date,
                percent=body.scores.get(g.id, body.assume),
                set=g.id in body.scores,
            )
            for g in items
        ],
        empty_categories=empty,
        assumptions=assumptions,
    )
