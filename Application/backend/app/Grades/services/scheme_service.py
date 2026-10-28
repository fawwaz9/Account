"""Alternative grading schemes: the same marks, read another way.

A scheme is a list of components with per-category weights and two rules,
`drop_lowest` and `replace_with`; with the course's own weights and no rules it gives
exactly the course's average. A picked scheme becomes the course's grade, and every
change to it rewrites the stored average in the same commit. Schemes are edited in
place, with no history.
"""

import uuid

from sqlalchemy.orm import Session

from app._database.models import GradingSchemeModel
from app.Grades.schemas.scheme import (
    GradingScheme,
    SchemeComparison,
    SchemeComponent,
    SchemeLine,
    SchemeResult,
    SchemeWrite,
)
from app.Grades.services.grade_service import course_grade, get_user_course
from app.Grades.utils import scheme_math
from app.Grades.utils.enums import GradeCategory


def category_average(course, category: str, drop_lowest: int = 0) -> tuple[float | None, int]:
    """Return a category's live average and how many marks were dropped.

    Args:
        course: The course with its grades loaded.
        category: Grade category value, such as "Quiz".
        drop_lowest: How many of the category's lowest marks to leave out.

    Returns:
        (average or None when nothing is marked, number of marks dropped).
    """
    return scheme_math.category_average(course, category, drop_lowest)


def project(course, components: list[SchemeComponent], label: str, scheme_id=None) -> SchemeResult:
    """Return the live average under some components, with the working per category.

    Args:
        course: Course with its grades loaded.
        components: The scheme's components.
        label: Name to report the result under.
        scheme_id: The scheme's id; None for the course's own weights.

    Returns:
        The scheme's result, components included.
    """
    average, lines = scheme_math.project(course, components)
    return SchemeResult(
        id=scheme_id, label=label, average=average, components=components,
        lines=[
            SchemeLine(category=l.category, weight=l.weight, average=l.average,
                       dropped=l.dropped, replaced_by=l.replaced_by)
            for l in lines
        ],
    )


def own_components(course) -> list[SchemeComponent]:
    """Return the course's own non-zero weights as scheme components.

    Args:
        course: The course whose weights to read.

    Returns:
        One component per category with a weight above 0.
    """
    return [
        SchemeComponent(category=GradeCategory(category), weight=weight)
        for category, weight in course.category_weights.items()
        if weight > 0
    ]


def as_schema(row: GradingSchemeModel) -> GradingScheme:
    """Return a stored scheme row as its API schema.

    Args:
        row: The stored scheme.

    Returns:
        The scheme with its components validated.
    """
    return GradingScheme(
        id=row.id, course_id=row.course_id, label=row.label,
        components=[SchemeComponent.model_validate(c) for c in row.components],
        created_at=row.created_at,
    )


def _owned_scheme(db: Session, course_id: uuid.UUID, scheme_id: uuid.UUID) -> GradingSchemeModel | None:
    """Return the scheme with this id if it belongs to this course, else None."""
    return (
        db.query(GradingSchemeModel)
        .filter(GradingSchemeModel.id == scheme_id, GradingSchemeModel.course_id == course_id)
        .first()
    )


def compare(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> SchemeComparison | None:
    """Return the course's own figure beside every scheme's.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The comparison, schemes in display order, or None when the course is missing or
        another user's.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    current = project(course, own_components(course), "As set on the course")
    rows = (
        db.query(GradingSchemeModel)
        .filter(GradingSchemeModel.course_id == course.id)
        .order_by(GradingSchemeModel.position, GradingSchemeModel.created_at)
        .all()
    )
    results = [
        project(course, [SchemeComponent.model_validate(c) for c in row.components], row.label, row.id)
        for row in rows
    ]
    best = max(results, key=lambda r: r.average, default=None)
    return SchemeComparison(
        current=current, schemes=results,
        best_id=best.id if best and best.average > current.average else None,
        counting_id=course.counting_scheme_id,
    )


def create_scheme(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, data: SchemeWrite) -> GradingScheme | None:
    """Add a grading scheme to a course, last in display order.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        data: The scheme's label and components.

    Returns:
        The new scheme, or None when the course is missing or another user's.

    Note:
        Commits.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    row = GradingSchemeModel(
        id=uuid.uuid4(), course_id=course.id, label=data.label.strip(),
        components=[c.model_dump(mode="json") for c in data.components],
        position=len(course.grading_schemes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return as_schema(row)


def update_scheme(
    db: Session, user_id: uuid.UUID, course_id: uuid.UUID, scheme_id: uuid.UUID, data: SchemeWrite,
) -> GradingScheme | None:
    """Replace a scheme's label and components, regrading the course if picked.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        scheme_id: The scheme.
        data: The new label and components.

    Returns:
        The updated scheme, or None when the course or scheme is missing or another
        user's.

    Note:
        Commits, with the course's new stored average when the scheme is its grade.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    row = _owned_scheme(db, course_id, scheme_id)
    if row is None:
        return None
    row.label = data.label.strip()
    row.components = [c.model_dump(mode="json") for c in data.components]
    if course.counting_scheme_id == row.id:
        # The grade is this scheme, so its new rules are the new grade.
        db.flush()
        course.average = course_grade(course)
    db.commit()
    db.refresh(row)
    return as_schema(row)


def delete_scheme(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, scheme_id: uuid.UUID) -> bool:
    """Delete a scheme; if it was picked, the course's own weights count again.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        scheme_id: The scheme.

    Returns:
        True if deleted, False when the course or scheme is missing or another user's.

    Note:
        Commits, clearing `counting_scheme_id` and rewriting the average in the same
        transaction.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return False
    row = _owned_scheme(db, course_id, scheme_id)
    if row is None:
        return False
    counting = course.counting_scheme_id == row.id
    db.delete(row)
    if counting:
        # Cleared in the same transaction as the delete: the grade goes back to
        # the course's own weights, never to a scheme that no longer exists.
        course.counting_scheme_id = None
        db.flush()
        db.expire(course, ["grading_schemes"])
        course.average = course_grade(course)
    db.commit()
    return True


def set_counting(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, scheme_id: uuid.UUID | None) -> SchemeComparison | None:
    """Make a scheme the course's grade, or put the course's own weights back.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        scheme_id: The scheme to count; None for the course's own weights.

    Returns:
        The comparison after the change, or None when the course is not the caller's
        or the scheme is not this course's.

    Note:
        Commits, with the recomputed stored average, so every screen moves together.
    """
    course = get_user_course(db, user_id, course_id)
    if course is None:
        return None
    if scheme_id is not None and _owned_scheme(db, course_id, scheme_id) is None:
        return None
    course.counting_scheme_id = scheme_id
    course.average = course_grade(course)
    db.commit()
    return compare(db, user_id, course_id)
