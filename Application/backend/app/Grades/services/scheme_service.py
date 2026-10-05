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
from app.Grades.services.grade_service import MAX_COURSE_PERCENT, counts_toward_average, get_user_course
from app.Grades.utils.enums import GradeCategory, is_additive


def category_average(course, category: str, drop_lowest: int = 0) -> tuple[float | None, int]:
    """(average, how many dropped), point-weighted like the course's own.

    Null when nothing in the category is marked. The same filter and the same
    formula as calculate_grade_category_average, so with nothing dropped the
    two agree to the cent.
    """
    marked = [
        g for g in course.grades
        if g.category == category and g.score is not None and g.max_score > 0 and counts_toward_average(g)
    ]
    if not marked:
        return None, 0
    dropped = min(drop_lowest, len(marked) - 1)
    if dropped:
        marked = sorted(marked, key=lambda g: g.score / g.max_score)[dropped:]
    total = sum(g.max_score for g in marked)
    weighted = sum((g.score / g.max_score) * 100 * g.max_score for g in marked)
    return round(weighted / total, 2), dropped


def project(course, components: list[SchemeComponent], label: str, scheme_id=None) -> SchemeResult:
    averages: dict[str, float | None] = {}
    drops: dict[str, int] = {}
    for c in components:
        averages[c.category.value], drops[c.category.value] = category_average(course, c.category.value, c.drop_lowest)

    lines: list[SchemeLine] = []
    final_average: dict[str, float | None] = {}
    for c in components:
        value = averages[c.category.value]
        replaced_by = None
        if c.replace_with is not None and value is not None:
            other = averages.get(c.replace_with.value)
            if other is None:
                other, _ = category_average(course, c.replace_with.value)
            if other is not None and other > value:
                value, replaced_by = other, c.replace_with
        final_average[c.category.value] = value
        lines.append(SchemeLine(
            category=c.category, weight=c.weight, average=value,
            dropped=drops[c.category.value], replaced_by=replaced_by,
        ))

    scoring = [c for c in components if not is_additive(c.category.value)
               and final_average[c.category.value] is not None]
    total_weight = sum(c.weight for c in scoring)
    earned = 0.0
    if total_weight > 0:
        weighted = sum(final_average[c.category.value] * c.weight for c in scoring)
        earned = weighted / min(total_weight, MAX_COURSE_PERCENT)
    bonus = sum(
        (final_average[c.category.value] or 0.0) * c.weight / 100.0
        for c in components if is_additive(c.category.value) and c.weight > 0
    )
    any_marked = any(value is not None for value in final_average.values())
    average = min(round(earned + bonus, 2), MAX_COURSE_PERCENT) if any_marked else 0.0
    return SchemeResult(id=scheme_id, label=label, average=average, lines=lines)


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
    if get_user_course(db, user_id, course_id) is None:
        return None
    row = _owned_scheme(db, course_id, scheme_id)
    if row is None:
        return None
    row.label = data.label.strip()
    row.components = [c.model_dump(mode="json") for c in data.components]
    db.commit()
    db.refresh(row)
    return as_schema(row)


def delete_scheme(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, scheme_id: uuid.UUID) -> bool:
    if get_user_course(db, user_id, course_id) is None:
        return False
    deleted = (
        db.query(GradingSchemeModel)
        .filter(GradingSchemeModel.id == scheme_id, GradingSchemeModel.course_id == course_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return bool(deleted)
