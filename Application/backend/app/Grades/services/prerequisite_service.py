"""Your prerequisites, the catalogue's, and whether you meet them (Phase 2 items 4, 7).

Your own rule lives in ``prerequisite_proposals`` and applies to you at once.
The shared rule is the catalogue's, reached through the course's link (D11)
and picked for the session the course was in. Yours wins for you when you
have one; both are shown, each labelled by its source.

Advisory only (D3): the answer is met, on track or not met, phrased as a
warning, and no route anywhere refuses anything because of it.
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
    """UBC's name for the session a term falls in: "2026W" runs September 2026
    to April 2027, "2027S" May to August 2027. None when the first-year
    setting is missing, rather than a guess."""
    began = calendar_year_of(school_year, first_year)
    if began is None or semester is None:
        return None
    if semester in ("Fall", "Winter"):
        return f"{began}W"
    if semester in ("Spring", "Summer"):
        return f"{began + 1}S"
    return None


def _session_order(session: str) -> tuple[int, int]:
    """2026W (from September 2026) after 2026S (from May 2026), before 2027S."""
    try:
        return int(session[:4]), (9 if session.endswith("W") else 5)
    except ValueError:
        return 0, 0


def _record(db: Session, user_id: uuid.UUID, leave_out: uuid.UUID | None) -> list[Taken]:
    """Your courses and equivalences, as rules see them. The course being
    asked about is left out: it cannot be its own prerequisite.

    Archived courses are left out, as the degree audit leaves them out, so the
    two never disagree about what is on your record.
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
    return RuleResult(status=result.status, text=result.text, detail=result.detail, group=result.group,
                      parts=[_result(part) for part in result.parts])


def _shared_rule(db: Session, catalogue_course_id: uuid.UUID, kind: str,
                 session: str | None) -> CataloguePrerequisiteModel | None:
    """The catalogue's rule for the session the course was in: the latest one
    at or before it, or the latest of all when none is that old or the session
    is unknown."""
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
    return db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()


def prerequisites(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> Prerequisites | None:
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
    """Write your rule for one kind, replacing any you had. Back to pending
    review, since what the reviewer saw is no longer what you hold.

    RuleError (a ValueError) when the rule cannot be read.
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
    """The warning for a course not yet added: the shared rule its code
    matches, for the session it would be in, against your record."""
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
