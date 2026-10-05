"""Alternative grading schemes: the same marks, read another way.

Phase 1 item 4 (account-vision.md §7). Courses with more than one rubric break
generic calculators. Here the course's own weights stay its grade, and each
scheme is projected beside it with the working shown, because "87.2% under
Scheme B" is meaningless without the breakdown (§7, "show the work").

**The arithmetic is the course average's, extended.** A scheme with the
course's own weights and no rules must give exactly the course's average --
that is tested, so a scheme can only ever differ for a reason it can show:
a different weight, a dropped mark, or a replacement.

Rules, as the vision lists them:

* **drop_lowest** -- leave out a category's N lowest marks by percentage,
  keeping at least one. The marks are not touched; this is a reading.
* **replace_with** -- when another category's average is higher, it stands in
  for this one ("the final replaces the midterm if higher"). Only between two
  categories that both have marks.

Versioning (keeping a professor's mid-term rubric change as history) is not
here yet: a scheme is edited in place.
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
    """(average, how many dropped) from what is marked. See scheme_math."""
    return scheme_math.category_average(course, category, drop_lowest)


def project(course, components: list[SchemeComponent], label: str, scheme_id=None) -> SchemeResult:
    """The live average under these components, with the working per category."""
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
    return [
        SchemeComponent(category=GradeCategory(category), weight=weight)
        for category, weight in course.category_weights.items()
        if weight > 0
    ]


def as_schema(row: GradingSchemeModel) -> GradingScheme:
    return GradingScheme(
        id=row.id, course_id=row.course_id, label=row.label,
        components=[SchemeComponent.model_validate(c) for c in row.components],
        created_at=row.created_at,
    )


def _owned_scheme(db: Session, course_id: uuid.UUID, scheme_id: uuid.UUID) -> GradingSchemeModel | None:
    return (
        db.query(GradingSchemeModel)
        .filter(GradingSchemeModel.id == scheme_id, GradingSchemeModel.course_id == course_id)
        .first()
    )


def compare(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> SchemeComparison | None:
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
    """Make a scheme the course's grade, or (None) put its own weights back.

    None when the course is not the caller's, or the scheme is not this
    course's -- a scheme is only ever reached through its course. Recomputes the
    stored average in the same commit, so every screen moves together.
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
