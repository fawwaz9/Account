"""Prerequisites for a course: the student's own rule, the catalogue's, and the verdict.

The student's rule lives in `prerequisite_proposals` and applies to them at once;
the shared rule comes from the course's catalogue link, for the session the course
was in. Both are shown, the student's winning when present. Advisory only: nothing
is ever refused because of a verdict.
"""
import uuid

from sqlalchemy.orm import Session

from app._database.models import (
    CataloguePrerequisiteModel,
    CourseEquivalenceModel,
    CourseModel,
    PREREQUISITE_KINDS,
    PrerequisiteProposalModel,
    UserModel,
    utc_now,
)
from app.Grades.schemas.prerequisite import (
    PrerequisitePreview,
    PrerequisiteKind,
    PrerequisiteSide,
    Prerequisites,
    RuleResult,
    RuleWrite,
)
from app.Grades.services.catalogue_service import link_of, match
from app.Grades.services.course_service import current_term_of, get_all_courses
from app.Grades.services.degree_service import course_status
from app.Grades.utils.prerequisites import Result, Taken, code_key, evaluate, parse_text, render, validate
from app.Grades.utils.terms import calendar_year_of, course_result_grade, term_key


def session_of(semester: str | None, school_year: int | None, first_year: int | None) -> str | None:
    """Return UBC's session name for a term: "2026W" (Sep-Apr) or "2027S" (May-Aug).

    Args:
        semester: The term.
        school_year: The term's school year.
        first_year: The first-year anchor.

    Returns:
        The session, or None when the anchor or term is missing or unknown.
    """
    began = calendar_year_of(school_year, first_year)
    if began is None or semester is None:
        return None
    if semester in ("Fall", "Winter"):
        return f"{began}W"
    if semester in ("Spring", "Summer"):
        return f"{began + 1}S"
    return None


def _session_order(session: str) -> tuple[int, int]:
    """Return a sortable key for a session name: (year, starting month)."""
    try:
        return int(session[:4]), (9 if session.endswith("W") else 5)
    except ValueError:
        return 0, 0


def _record(db: Session, user_id: uuid.UUID, leave_out: uuid.UUID | None) -> list[Taken]:
    """Return the student's record as rules read it, leaving one course out.

    Archived courses are left out, as in the degree audit; a course that did not pass
    is kept with status "failed". Equivalences whose sources are all present add an item
    for the courses they count as.

    Args:
        db: Open database session.
        user_id: Whose record.
        leave_out: The course being asked about, which cannot be its own prerequisite;
            None leaves nothing out.

    Returns:
        One `Taken` per course and applied equivalence.
    """
    courses = [c for c in get_all_courses(db, user_id) if c.id != leave_out and not c.archived]
    record: list[Taken] = []
    by_key: dict[tuple[str, int], Taken] = {}
    for course in courses:
        key = code_key(course.code)
        if key is None:
            continue
        status = course_status(course) or "failed"
        item = Taken(label=course.code, codes=frozenset({key}), credits=course.credits or 0.0,
                     status=status, term=term_key(course.year, course.semester),
                     grade=None if course.transfer_credit else course_result_grade(course))
        record.append(item)
        if status != "failed":
            by_key[key] = item

    order = {"completed": 0, "in_progress": 1, "planned": 2}
    equivalences = db.query(CourseEquivalenceModel).filter(CourseEquivalenceModel.user_id == user_id).all()
    for equivalence in equivalences:
        sources = [code_key(code) for code in equivalence.from_codes]
        if not sources or any(s is None or s not in by_key for s in sources):
            continue
        held = [by_key[s] for s in sources]
        targets = frozenset(k for k in (code_key(c) for c in equivalence.counts_as) if k is not None)
        record.append(Taken(
            label=" + ".join(item.label for item in held), codes=targets,
            credits=equivalence.credits if equivalence.credits is not None else sum(i.credits for i in held),
            status=max((item.status for item in held), key=lambda s: order[s]),
            term=max(item.term for item in held),
        ))
    return record


def _result(result: Result) -> RuleResult:
    """Return a verdict tree as the `RuleResult` schema."""
    return RuleResult(status=result.status, text=result.text, detail=result.detail, group=result.group,
                      parts=[_result(part) for part in result.parts])


def _shared_rule(db: Session, catalogue_course_id: uuid.UUID, kind: str,
                 session: str | None) -> CataloguePrerequisiteModel | None:
    """Return the catalogue's rule of one kind for a session, or None if there is none.

    The latest rule at or before the session wins; with none that old, or an unknown
    session, the latest of all.
    """
    rows = db.query(CataloguePrerequisiteModel).filter(
        CataloguePrerequisiteModel.catalogue_course_id == catalogue_course_id,
        CataloguePrerequisiteModel.kind == kind,
    ).all()
    if not rows:
        return None
    rows.sort(key=lambda row: _session_order(row.session))
    if session is not None:
        earlier = [row for row in rows if _session_order(row.session) <= _session_order(session)]
        if earlier:
            return earlier[-1]
    return rows[-1]


def _owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    """Return the caller's course with this id, or None."""
    return db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()


def prerequisites(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> Prerequisites | None:
    """Return a course's prerequisite rules, both versions, with verdicts.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The rules and verdicts per kind, and the catalogue link; None when the course is
        missing or another user's.
    """
    course = _owned_course(db, user_id, course_id)
    if course is None:
        return None
    user = db.get(UserModel, user_id)
    session = session_of(course.semester, course.year, user.first_year_calendar_year if user else None)
    link = link_of(db, course)
    record = _record(db, user_id, course.id)
    term = term_key(course.year, course.semester)
    yours = {
        row.kind: row for row in db.query(PrerequisiteProposalModel).filter(
            PrerequisiteProposalModel.user_id == user_id, PrerequisiteProposalModel.course_id == course.id,
        )
    }

    kinds = []
    for kind in PREREQUISITE_KINDS:
        entry = PrerequisiteKind(kind=kind)
        own = yours.get(kind)
        if own is not None:
            entry.yours = PrerequisiteSide(
                source=own.source, rule=own.rule, text=render(own.rule), note=own.note, session=own.session,
                source_text=own.source_text, review=own.status,
                result=_result(evaluate(own.rule, record, term, kind)),
            )
        shared = _shared_rule(db, link.course.id, kind, session) if link.course else None
        if shared is not None:
            entry.shared = PrerequisiteSide(
                source="reviewed" if shared.source == "reviewed-proposal" else "ubc-calendar",
                rule=shared.rule, text=render(shared.rule), note=shared.note, session=shared.session,
                # Only a calendar row can carry wording; the constraint holds it.
                source_text=shared.source_text if shared.source == "ubc-calendar" else None,
                result=_result(evaluate(shared.rule, record, term, kind)),
            )
        entry.applies = "yours" if entry.yours else ("shared" if entry.shared else None)
        kinds.append(entry)
    return Prerequisites(course_id=str(course.id), link=link, kinds=kinds)


def set_own(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, data: RuleWrite,
            source: str = "typed", source_text: str | None = None) -> Prerequisites | None:
    """Write the student's own rule of one kind for a course, replacing any they had.

    The rule goes back to pending review, since the reviewer saw something else.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        data: The rule, typed or as a tree, and its kind and note.
        source: "typed", or "syllabus" when filed from a syllabus.
        source_text: The syllabus sentence, kept only on the student's row.

    Returns:
        The course's prerequisites after the change, or None when the course is missing
        or another user's.

    Raises:
        RuleError: If the rule cannot be read (a ValueError).

    Note:
        Commits.
    """
    course = _owned_course(db, user_id, course_id)
    if course is None:
        return None
    rule = parse_text(data.text) if data.text is not None else validate(data.rule)
    user = db.get(UserModel, user_id)
    row = db.query(PrerequisiteProposalModel).filter(
        PrerequisiteProposalModel.user_id == user_id,
        PrerequisiteProposalModel.course_id == course.id,
        PrerequisiteProposalModel.kind == data.kind,
    ).first()
    if row is None:
        row = PrerequisiteProposalModel(id=uuid.uuid4(), user_id=user_id, course_id=course.id, kind=data.kind,
                                        created_at=utc_now())
        db.add(row)
    row.rule, row.note, row.source, row.source_text = rule, data.note, source, source_text
    row.session = session_of(course.semester, course.year, user.first_year_calendar_year if user else None)
    row.status, row.reviewed_at, row.updated_at = "pending", None, utc_now()
    db.commit()
    return prerequisites(db, user_id, course_id)


def delete_own(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, kind: str) -> Prerequisites | None:
    """Delete the student's own rule of one kind for a course.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        kind: "prerequisite" or "corequisite".

    Returns:
        The course's prerequisites after the change, or None when the course is missing
        or another user's.

    Note:
        Commits.
    """
    course = _owned_course(db, user_id, course_id)
    if course is None:
        return None
    db.query(PrerequisiteProposalModel).filter(
        PrerequisiteProposalModel.user_id == user_id,
        PrerequisiteProposalModel.course_id == course.id,
        PrerequisiteProposalModel.kind == kind,
    ).delete(synchronize_session=False)
    db.commit()
    return prerequisites(db, user_id, course_id)


def preview(db: Session, user_id: uuid.UUID, code: str, school_year: int, semester: str) -> PrerequisitePreview:
    """Return the shared rules for a course about to be added, with verdicts.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        code: The code being added.
        school_year: The school year it would be in.
        semester: The term it would be in.

    Returns:
        The matching catalogue course and its shared rules with verdicts; empty for a
        term already past or a code the catalogue does not match.
    """
    current_year, current_semester = current_term_of(db, user_id)
    term = term_key(school_year, semester)
    if current_year is not None and term < term_key(current_year, current_semester):
        return PrerequisitePreview()
    found = match(db, code)
    if found is None:
        return PrerequisitePreview()
    user = db.get(UserModel, user_id)
    session = session_of(semester, school_year, user.first_year_calendar_year if user else None)
    record = _record(db, user_id, None)
    kinds = []
    for kind in PREREQUISITE_KINDS:
        shared = _shared_rule(db, found.id, kind, session)
        if shared is None:
            continue
        kinds.append(PrerequisiteKind(kind=kind, applies="shared", shared=PrerequisiteSide(
            source="reviewed" if shared.source == "reviewed-proposal" else "ubc-calendar",
            rule=shared.rule, text=render(shared.rule), note=shared.note, session=shared.session,
            source_text=shared.source_text if shared.source == "ubc-calendar" else None,
            result=_result(evaluate(shared.rule, record, term, kind)),
        )))
    return PrerequisitePreview(catalogue=found, kinds=kinds)
