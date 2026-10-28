"""The degree audit: the student's requirements checked against their own courses.

Computed on every read, never stored. Courses become units (an equivalence replaces
the courses it maps once all of them are on the record); "courses" requirements are
filled first, then "credits" ones, each in the student's order, and a unit counts
toward one requirement unless that requirement shares. Also the CRUD for
requirements and equivalences.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app._database.models import CourseEquivalenceModel, DegreeRequirementModel, UserModel
from app.Grades.schemas.degree import (
    Counted,
    DegreeAudit,
    Equivalence,
    EquivalenceWrite,
    ItemResult,
    Requirement,
    RequirementResult,
    RequirementWrite,
    parse_code,
    parse_item,
)
from app.Grades.services.course_service import get_all_courses
from app.Grades.utils.terms import CURRENT, PAST, course_result_grade
from app.Users.services.user_service import get_preferences

#: UBC's passing grade.
PASS = 50.0
ORDER = {"completed": 0, "in_progress": 1, "planned": 2}
"""Rank of each status, most finished first, for choosing and sorting units."""


@dataclass
class Unit:
    """What can count toward a requirement: a course or an applied equivalence.

    Attributes:
        label: How it is named, such as "CPSC 110" or "COSC 111 + COSC 121 as CPSC 110".
        codes: (subject, number) keys it counts as.
        credits: Credits it carries.
        status: "completed", "in_progress" or "planned".
        used_by: Ids of the non-sharing requirements it has been used for.
    """
    label: str
    codes: set[tuple[str, int]]
    credits: float
    status: str
    used_by: set[uuid.UUID] = field(default_factory=set)

    def counted(self) -> Counted:
        """Return the unit as the `Counted` schema.

        Returns:
            The unit's label, credits and status.
        """
        return Counted(label=self.label, credits=self.credits, status=self.status)


def course_status(course) -> str | None:
    """Return a course's audit status, or None for a course that did not pass.

    Transfer credit is completed. A past course is completed unless its result is under
    `PASS`; a current course is completed once it has a final grade (None if under
    `PASS`), else in progress; anything later is planned.

    Args:
        course: A course with `term_bucket` set.

    Returns:
        "completed", "in_progress", "planned", or None when it failed.
    """
    if course.transfer_credit:
        return "completed"
    result = course_result_grade(course)
    if course.term_bucket == PAST:
        if result is not None and result < PASS:
            return None
        return "completed"
    if course.term_bucket == CURRENT:
        if course.final_grade and course.final_grade > 0:
            return "completed" if course.final_grade >= PASS else None
        return "in_progress"
    return "planned"


def build_units(courses, equivalences) -> tuple[list[Unit], list[str]]:
    """Return the units the record offers, and the codes of failed courses.

    Archived and unreadable codes are skipped; of two courses with one code (a retake)
    the more finished counts. Equivalences whose every source is present replace those
    sources.

    Args:
        courses: The student's courses with `term_bucket` attached.
        equivalences: The student's equivalence rows.

    Returns:
        (units ordered completed first, then by label; sorted failed course codes).
    """
    by_code: dict[tuple[str, int], tuple[object, str]] = {}
    failed: list[str] = []
    for course in courses:
        if course.archived:
            continue
        status = course_status(course)
        if status is None:
            failed.append(course.code)
            continue
        code = parse_code(course.code)
        if code is None:
            continue
        # Two rows for one code (a retake): the more finished one counts.
        held = by_code.get(code)
        if held is None or ORDER[status] < ORDER[held[1]]:
            by_code[code] = (course, status)

    replaced: set[tuple[str, int]] = set()
    units: list[Unit] = []
    for equivalence in equivalences:
        sources = [parse_code(c) for c in equivalence.from_codes]
        if not sources or any(s is None or s not in by_code for s in sources):
            continue
        statuses = [by_code[s][1] for s in sources]
        status = max(statuses, key=lambda st: ORDER[st])
        credits = equivalence.credits if equivalence.credits is not None else sum(
            (by_code[s][0].credits or 0.0) for s in sources)
        units.append(Unit(
            label=f"{' + '.join(by_code[s][0].code for s in sources)} as {', '.join(equivalence.counts_as)}",
            codes={parse_code(c) for c in equivalence.counts_as},
            credits=credits, status=status,
        ))
        replaced.update(sources)

    for code, (course, status) in by_code.items():
        if code in replaced:
            continue
        units.append(Unit(label=course.code, codes={code}, credits=course.credits or 0.0, status=status))
    units.sort(key=lambda u: (ORDER[u.status], u.label))
    return units, sorted(failed)


def matches(unit: Unit, alternatives) -> bool:
    """Return whether any of a unit's codes falls within any of the alternatives.

    Args:
        unit: A course, or an equivalence standing in for its sources.
        alternatives: (subject or None, lowest number, highest number) ranges.

    Returns:
        True when one of the unit's codes is in one of the ranges.
    """
    return any(
        (subject is None or subject == code_subject) and low <= number <= high
        for code_subject, number in unit.codes
        for subject, low, high in alternatives
    )


def audit_rows(courses, requirements, equivalences, credit_target: int) -> DegreeAudit:
    """Return the degree audit from already-loaded rows.

    Args:
        courses: The student's courses with `term_bucket` attached.
        requirements: Requirement rows.
        equivalences: Equivalence rows.
        credit_target: Credits the degree needs.

    Returns:
        Each requirement's result in display order, the equivalences, overall credits,
        completed units no requirement used, and failed courses.
    """
    units, failed = build_units(courses, equivalences)
    ordered = sorted(requirements, key=lambda r: (r.kind != "courses", r.position, r.created_at))
    results: dict[uuid.UUID, RequirementResult] = {}

    def free(unit: Unit, requirement) -> bool:
        """Return whether a unit may count toward this requirement."""
        return requirement.shares or not unit.used_by

    for requirement in ordered:
        schema = Requirement.model_validate(requirement)
        result = RequirementResult(requirement=schema)
        if requirement.kind == "courses":
            taken_here: list[Unit] = []
            for item in requirement.items:
                alternatives = parse_item(item) or []
                # A unit already used for another item here may serve again:
                # one course counting as three is the point of a mapping.
                unit = next((u for u in units if matches(u, alternatives)
                             and (u in taken_here or free(u, requirement))), None)
                if unit is not None and unit not in taken_here:
                    taken_here.append(unit)
                    if not requirement.shares:
                        unit.used_by.add(requirement.id)
                result.items.append(ItemResult(item=item, met_by=unit.counted() if unit else None))
            for unit in taken_here:
                _add(result, unit)
            result.done = all(i.met_by and i.met_by.status == "completed" for i in result.items)
        else:
            alternatives = [alt for item in requirement.items for alt in (parse_item(item) or [])]
            needed = requirement.credits_needed or 0.0
            for unit in units:
                if result.credits_completed + result.credits_in_progress + result.credits_planned >= needed:
                    break
                if matches(unit, alternatives) and free(unit, requirement):
                    if not requirement.shares:
                        unit.used_by.add(requirement.id)
                    result.counted.append(unit.counted())
                    _add(result, unit)
            result.done = result.credits_completed >= needed
        results[requirement.id] = result

    completed = sum(c.credits or 0.0 for c in courses
                    if not c.archived and course_status(c) == "completed")
    in_progress = sum(c.credits or 0.0 for c in courses
                      if not c.archived and course_status(c) == "in_progress")
    not_counted = [u.counted() for u in units if u.status == "completed" and not u.used_by
                   and not any(matches(u, [alt for item in r.items for alt in (parse_item(item) or [])])
                               for r in requirements if r.shares)]
    return DegreeAudit(
        requirements=[results[r.id] for r in sorted(requirements, key=lambda r: (r.position, r.created_at))],
        equivalences=[Equivalence.model_validate(e) for e in equivalences],
        credits_completed=round(completed, 2), credits_in_progress=round(in_progress, 2),
        credit_target=credit_target, not_counted=not_counted, failed=failed,
    )


def _add(result: RequirementResult, unit: Unit) -> None:
    """Add a unit's credits to the result's total for its status."""
    if unit.status == "completed":
        result.credits_completed += unit.credits
    elif unit.status == "in_progress":
        result.credits_in_progress += unit.credits
    else:
        result.credits_planned += unit.credits


# --- reading and writing ---------------------------------------------------

def _requirements(db: Session, user_id: uuid.UUID) -> list[DegreeRequirementModel]:
    """Return the user's requirement rows in display order."""
    return (db.query(DegreeRequirementModel).filter(DegreeRequirementModel.user_id == user_id)
            .order_by(DegreeRequirementModel.position, DegreeRequirementModel.created_at).all())


def _equivalences(db: Session, user_id: uuid.UUID) -> list[CourseEquivalenceModel]:
    """Return the user's equivalence rows, oldest first."""
    return (db.query(CourseEquivalenceModel).filter(CourseEquivalenceModel.user_id == user_id)
            .order_by(CourseEquivalenceModel.created_at).all())


def audit(db: Session, user_id: uuid.UUID) -> DegreeAudit | None:
    """Return the degree audit for a user.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The audit, or None when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None
    return audit_rows(get_all_courses(db, user_id), _requirements(db, user_id), _equivalences(db, user_id),
                      get_preferences(user).credit_target)


def create_requirement(db: Session, user_id: uuid.UUID, data: RequirementWrite) -> Requirement:
    """Add a degree requirement, last in display order.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The validated requirement.

    Returns:
        The stored requirement.

    Note:
        Commits.
    """
    row = DegreeRequirementModel(id=uuid.uuid4(), user_id=user_id, position=len(_requirements(db, user_id)),
                                 **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return Requirement.model_validate(row)


def _owned(db: Session, model, user_id: uuid.UUID, row_id: uuid.UUID):
    """Return the user's row of a model with this id, or None."""
    return db.query(model).filter(model.id == row_id, model.user_id == user_id).first()


def update_requirement(db: Session, user_id: uuid.UUID, requirement_id: uuid.UUID,
                       data: RequirementWrite) -> Requirement | None:
    """Replace a degree requirement's fields.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        requirement_id: The requirement.
        data: Its new fields.

    Returns:
        The updated requirement, or None when it is missing or another user's.

    Note:
        Commits.
    """
    row = _owned(db, DegreeRequirementModel, user_id, requirement_id)
    if row is None:
        return None
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return Requirement.model_validate(row)


def delete_requirement(db: Session, user_id: uuid.UUID, requirement_id: uuid.UUID) -> bool:
    """Delete a degree requirement.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        requirement_id: The requirement.

    Returns:
        True if deleted, False when it is missing or another user's.

    Note:
        Commits.
    """
    row = _owned(db, DegreeRequirementModel, user_id, requirement_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def create_equivalence(db: Session, user_id: uuid.UUID, data: EquivalenceWrite) -> Equivalence:
    """Add a course equivalence.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The validated equivalence.

    Returns:
        The stored equivalence.

    Note:
        Commits.
    """
    row = CourseEquivalenceModel(id=uuid.uuid4(), user_id=user_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return Equivalence.model_validate(row)


def update_equivalence(db: Session, user_id: uuid.UUID, equivalence_id: uuid.UUID,
                       data: EquivalenceWrite) -> Equivalence | None:
    """Replace a course equivalence's fields.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        equivalence_id: The equivalence.
        data: Its new fields.

    Returns:
        The updated equivalence, or None when it is missing or another user's.

    Note:
        Commits.
    """
    row = _owned(db, CourseEquivalenceModel, user_id, equivalence_id)
    if row is None:
        return None
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return Equivalence.model_validate(row)


def delete_equivalence(db: Session, user_id: uuid.UUID, equivalence_id: uuid.UUID) -> bool:
    """Delete a course equivalence.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        equivalence_id: The equivalence.

    Returns:
        True if deleted, False when it is missing or another user's.

    Note:
        Commits.
    """
    row = _owned(db, CourseEquivalenceModel, user_id, equivalence_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
