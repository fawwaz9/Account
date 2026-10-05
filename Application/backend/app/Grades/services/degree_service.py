"""The degree audit: your requirements against your courses (Phase 1 item 5, D31).

Deterministic and single-user. Requirements and equivalences are what you
entered; courses are your own, with the term rule the dashboard uses. The
audit is computed on every read, never stored, so it can't drift from the
courses it describes.

**Units.** What counts toward a requirement is a unit: one of your courses, or
an equivalence standing in for its source courses. An equivalence applies when
every source course is on your record (it takes the least-finished one's
status); it then replaces them, so a course is never counted both as itself
and as what it maps to.

**Status.** A unit is completed, in progress or planned. A multi-course
equivalence takes its least-finished source's status. A course that did not
pass (a recorded result under 50) counts nowhere and is listed as failed.

**Assignment.** "courses" requirements are filled first, then "credits" ones,
each in the order you set. A unit counts toward one requirement unless that
requirement shares; completed units are preferred over in-progress ones, and
those over planned. A credits requirement takes units only until it is met, so
the rest stay free for the next.
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


@dataclass
class Unit:
    label: str
    codes: set[tuple[str, int]]
    credits: float
    status: str
    used_by: set[uuid.UUID] = field(default_factory=set)

    def counted(self) -> Counted:
        return Counted(label=self.label, credits=self.credits, status=self.status)


def course_status(course) -> str | None:
    """completed / in_progress / planned, or None for a course that didn't pass."""
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
    return any(
        (subject is None or subject == code_subject) and low <= number <= high
        for code_subject, number in unit.codes
        for subject, low, high in alternatives
    )


def audit_rows(courses, requirements, equivalences, credit_target: int) -> DegreeAudit:
    units, failed = build_units(courses, equivalences)
    ordered = sorted(requirements, key=lambda r: (r.kind != "courses", r.position, r.created_at))
    results: dict[uuid.UUID, RequirementResult] = {}

    def free(unit: Unit, requirement) -> bool:
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
    if unit.status == "completed":
        result.credits_completed += unit.credits
    elif unit.status == "in_progress":
        result.credits_in_progress += unit.credits
    else:
        result.credits_planned += unit.credits


# --- reading and writing ---------------------------------------------------

def _requirements(db: Session, user_id: uuid.UUID) -> list[DegreeRequirementModel]:
    return (db.query(DegreeRequirementModel).filter(DegreeRequirementModel.user_id == user_id)
            .order_by(DegreeRequirementModel.position, DegreeRequirementModel.created_at).all())


def _equivalences(db: Session, user_id: uuid.UUID) -> list[CourseEquivalenceModel]:
    return (db.query(CourseEquivalenceModel).filter(CourseEquivalenceModel.user_id == user_id)
            .order_by(CourseEquivalenceModel.created_at).all())


def audit(db: Session, user_id: uuid.UUID) -> DegreeAudit | None:
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None
    return audit_rows(get_all_courses(db, user_id), _requirements(db, user_id), _equivalences(db, user_id),
                      get_preferences(user).credit_target)


def create_requirement(db: Session, user_id: uuid.UUID, data: RequirementWrite) -> Requirement:
    row = DegreeRequirementModel(id=uuid.uuid4(), user_id=user_id, position=len(_requirements(db, user_id)),
                                 **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return Requirement.model_validate(row)


def _owned(db: Session, model, user_id: uuid.UUID, row_id: uuid.UUID):
    return db.query(model).filter(model.id == row_id, model.user_id == user_id).first()


def update_requirement(db: Session, user_id: uuid.UUID, requirement_id: uuid.UUID,
                       data: RequirementWrite) -> Requirement | None:
    row = _owned(db, DegreeRequirementModel, user_id, requirement_id)
    if row is None:
        return None
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return Requirement.model_validate(row)


def delete_requirement(db: Session, user_id: uuid.UUID, requirement_id: uuid.UUID) -> bool:
    row = _owned(db, DegreeRequirementModel, user_id, requirement_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def create_equivalence(db: Session, user_id: uuid.UUID, data: EquivalenceWrite) -> Equivalence:
    row = CourseEquivalenceModel(id=uuid.uuid4(), user_id=user_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return Equivalence.model_validate(row)


def update_equivalence(db: Session, user_id: uuid.UUID, equivalence_id: uuid.UUID,
                       data: EquivalenceWrite) -> Equivalence | None:
    row = _owned(db, CourseEquivalenceModel, user_id, equivalence_id)
    if row is None:
        return None
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return Equivalence.model_validate(row)


def delete_equivalence(db: Session, user_id: uuid.UUID, equivalence_id: uuid.UUID) -> bool:
    row = _owned(db, CourseEquivalenceModel, user_id, equivalence_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
