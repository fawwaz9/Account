"""Syllabus intake: a model reads it, and only what the student confirms is written.

Nothing becomes a record without confirmation: `parse` writes only the parse row
(for the daily cap and the no-change measure), and `apply` or `add_to_course` write
what the student checked. Deterministic checks flag weights not summing to 100,
undated weighted work and dates outside the term. Only the document and the term's
dates are sent to the model.
"""

import base64
import binascii
import re
import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import CourseModel, PrerequisiteProposalModel, SyllabusParseModel, UserModel, utc_now
from app.Grades.schemas.prerequisite import RuleWrite
from app.Grades.services.prerequisite_service import set_own
from app.Grades.utils.prerequisites import render
from app.config import settings
from app.Grades.schemas.course import CourseCreate
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.course_service import create_course, delete_course
from app.Grades.services.grade_service import add_grades_bulk, get_user_course
from app.Grades.utils.enums import GradeCategory, GradeSchedule, Semester
from app.Grades.utils.terms import term_dates
from app.Intake.schemas.syllabus import (
    MAX_FILE_BYTES,
    MEDIA_TYPES,
    AddPreview,
    AddRequest,
    AddResult,
    ApplyRequest,
    ConfirmedRule,
    ApplyResult,
    ProposedRow,
    WeightNote,
    ParseResult,
    SyllabusExtract,
    SyllabusUpload,
)
from app.Intake.services import llm
from app.Intake.services.kept_files import keep_file
from app.shared.dates import local_day_in_utc, local_today

#: Weights are percentages; a syllabus rounds.
WEIGHT_TOLERANCE = 0.5
#: Exams are sat, not completed, so they go on the calendar rather than a list.
EXAM_CATEGORIES = {GradeCategory.MIDTERM, GradeCategory.FINAL}

SYSTEM = (
    "You extract the grading structure of a university course from its syllabus. "
    "Report only what the document says. Never invent an assessment, a weight or a date. "
    "Answer with a single JSON object and nothing else."
)
"""System instruction: report only what the document says, as JSON."""


def prompt(term_start: date | None, term_end: date | None) -> str:
    """Return the extraction prompt, with the term's dates when known.

    Args:
        term_start: First day of the course's term, or None when unknown.
        term_end: Last day of the course's term, or None when unknown.

    Returns:
        The instruction text sent with the document.
    """
    categories = ", ".join(category.value for category in GradeCategory)
    term = (
        f"The term runs from {term_start.isoformat()} to {term_end.isoformat()}; "
        "resolve week numbers and weekdays against it."
        if term_start and term_end else
        "The term's dates are not known; leave a date null rather than guess a year."
    )
    return f"""Read the syllabus and return this JSON object:
{{
  "course_code": "e.g. CPSC 221",
  "course_name": "e.g. Basic Algorithms and Data Structures",
  "section": "the section this syllabus is for, e.g. 101 or V01, or null if it does not say",
  "professor": "the instructor's name, or null",
  "multiple_schemes": true if the syllabus offers more than one way the grade can be calculated,
  "assessments": [
    {{
      "name": "e.g. Midterm 1",
      "category": one of {categories},
      "weight": percent of the final grade, as a number (for all of them together if there are several),
      "count": how many there are (e.g. 10 for "10 weekly quizzes"), 1 if one,
      "due_date": "YYYY-MM-DD", or null if no date is given,
      "date_tba": true if it is scheduled later (a final exam set by the registrar), else false
    }}
  ],
  "prerequisites": null if the syllabus states none, else {{
    "rule": RULE, or null if it cannot be written as one,
    "note": "what RULE cannot say, e.g. third-year standing or permission of the instructor", or null,
    "sentence": "the syllabus's own sentence about prerequisites, copied exactly"
  }},
  "corequisites": the same shape, for courses to be taken at the same time, or null
}}
RULE is one of: {{"course": "CPSC 210"}}, optionally with "min_grade": 64 for a minimum percentage;
{{"credits": 6, "subject": "MATH", "level": 100}} for a number of credits, subject and level optional;
{{"all": [RULE, ...]}}; {{"any": [RULE, ...]}}.
Rules:
- One entry per distinct graded item or group; if the schedule lists dated items of a group
  separately (Assignment 1 due Sep 26, Assignment 2 due Oct 10), give each its own entry and
  split the group's weight evenly between them.
- If there is more than one grading scheme, extract only the first and set multiple_schemes.
- Bonus or extra credit uses the category Bonus.
- Prerequisites only as the syllabus states them; never from what the course usually requires.
- {term}"""


class RateLimited(Exception):
    """Raised when the user has used today's syllabus parses."""
    pass


def parse(db: Session, user_id: uuid.UUID, upload: SyllabusUpload, *, transport=None) -> ParseResult:
    """Read an uploaded syllabus into a checkable extract; builds nothing.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        upload: The file, base64-encoded, with its name and type.
        transport: Stand-in for the provider call in tests.

    Returns:
        The stored parse's id, the extract, the warnings to check, and when it ran.

    Raises:
        ValueError: If the type is not PDF or plain text, the content is not base64,
            empty or over 8 MB, or the model's answer fails the extract schema.
        llm.NotConfigured: If no model is configured.
        RateLimited: If today's `LLM_PARSES_PER_DAY` parses are used, counted by the
            user's local day.
        llm.ProviderError: If the provider fails or answers unusably.

    Note:
        Commits the parse row, then keeps the file in the bucket when one is set. The
        cap counts stored parses only, so a failed parse is not counted.
    """
    if upload.media_type not in MEDIA_TYPES:
        raise ValueError("Upload a PDF or a plain-text file")
    try:
        content = base64.b64decode(upload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The file could not be read") from exc
    if not content:
        raise ValueError("The file is empty")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("The file is larger than 8 MB")
    if not llm.configured():
        raise llm.NotConfigured

    # The student's own day, as the UTC span it covers: `created_at` is UTC.
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    day_starts, day_ends = local_day_in_utc(user, local_today(user))
    used_today = (
        db.query(func.count(SyllabusParseModel.id))
        .filter(
            SyllabusParseModel.user_id == user_id,
            SyllabusParseModel.created_at >= day_starts,
            SyllabusParseModel.created_at < day_ends,
        )
        .scalar()
    )
    if used_today >= settings.LLM_PARSES_PER_DAY:
        raise RateLimited

    span = term_dates(user.current_semester, user.current_school_year, user.first_year_calendar_year)
    start, end = span if span else (None, None)
    raw = llm.extract_document(
        content, upload.media_type, upload.filename, SYSTEM, prompt(start, end), transport=transport,
    )
    extract = SyllabusExtract.model_validate(_clean(raw))

    row = SyllabusParseModel(
        id=uuid.uuid4(), user_id=user_id, filename=upload.filename,
        provider=settings.LLM_PROVIDER, model=settings.LLM_MODEL_EXTRACT,
        result=extract.model_dump(mode="json"), media_type=upload.media_type,
    )
    db.add(row)
    db.commit()
    keep_file(db, row, content)
    return ParseResult(id=row.id, extract=extract, warnings=check(extract, start, end), created_at=row.created_at)


def _clean(raw: dict) -> dict:
    """Return the raw answer minus assessment entries with no name."""
    items = raw.get("assessments") if isinstance(raw.get("assessments"), list) else []
    raw = dict(raw)
    raw["assessments"] = [item for item in items if isinstance(item, dict) and item.get("name")]
    return raw


def check(extract: SyllabusExtract, term_start: date | None, term_end: date | None) -> list[str]:
    """Return the warnings a person should look at before confirming a parse.

    Args:
        extract: The parsed syllabus.
        term_start: First day of the term, if known.
        term_end: Last day of the term, if known.

    Returns:
        Sentences for weights (bonus aside) not within 0.5 of 100, a weighted item with
        no date and not TBA, a date outside the term, several grading schemes, and rules
        that could not be read; empty when nothing stands out.
    """
    warnings: list[str] = []
    counted = [a for a in extract.assessments if a.category != GradeCategory.BONUS]
    total = sum(a.weight for a in counted)
    if counted and abs(total - 100) > WEIGHT_TOLERANCE:
        warnings.append(f"The weights add up to {total:g}%, not 100%.")
    for a in extract.assessments:
        if a.weight > 0 and a.due_date is None and not a.date_tba:
            warnings.append(f"{a.name} has {a.weight:g}% weight but no date.")
        if a.due_date and term_start and term_end and not (term_start <= a.due_date <= term_end):
            warnings.append(f"{a.name} is dated {a.due_date.isoformat()}, outside the term.")
    if extract.multiple_schemes:
        warnings.append("The syllabus offers more than one grading scheme; only the first was read.")
    for label, found in (("prerequisites", extract.prerequisites), ("co-requisites", extract.corequisites)):
        if found is not None and found.rule is None and found.sentence:
            warnings.append(f"The syllabus's {label} couldn't be read as a rule; type them in, or leave them out.")
    return warnings


def file_rules(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, extract: SyllabusExtract,
               prerequisites: ConfirmedRule | None, corequisites: ConfirmedRule | None) -> int:
    """File the confirmed prerequisite and co-requisite rules as the student's own.

    Only kinds that were sent are filed, marked as from the syllabus with its sentence.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course the rules are for.
        extract: The parse, for the syllabus's wording.
        prerequisites: The confirmed prerequisite rule, or None.
        corequisites: The confirmed co-requisite rule, or None.

    Returns:
        How many rules were filed; each commits.
    """
    filed = 0
    for kind, confirmed, found in (("prerequisite", prerequisites, extract.prerequisites),
                                   ("corequisite", corequisites, extract.corequisites)):
        if confirmed is None:
            continue
        set_own(db, user_id, course_id, RuleWrite(kind=kind, text=confirmed.text, note=confirmed.note),
                source="syllabus", source_text=found.sentence if found else None)
        filed += 1
    return filed


FIELDS = ("name", "category", "weight", "count", "due_date", "date_tba")
"""The assessment fields the no-change measure compares."""


def changes(extracted: SyllabusExtract, confirmed: ApplyRequest) -> tuple[int, int]:
    """Return (fields produced, fields the student changed) for the no-change measure.

    Compared row by row, plus the course code and name; an added or removed row counts
    all its fields as changed.

    Args:
        extracted: What the model read from the syllabus.
        confirmed: What the student confirmed.

    Returns:
        (fields produced, fields changed), the second capped at the first.
    """
    before = [a.model_dump() for a in extracted.assessments]
    after = [a.model_dump() for a in confirmed.assessments]
    total = len(before) * len(FIELDS) + 2  # plus the course code and name
    changed = int(confirmed.course_code.strip() != extracted.course_code.strip())
    changed += int(confirmed.course_name.strip() != extracted.course_name.strip())
    for index in range(max(len(before), len(after))):
        if index >= len(before) or index >= len(after):
            changed += len(FIELDS)
            continue
        changed += sum(1 for field in FIELDS if before[index][field] != after[index][field])
    return total, min(changed, total)


def grade_rows(assessment) -> list[GradeCreate]:
    """Return the gradebook rows one assessment becomes: one per item.

    Each is out of 100; only the first of a counted group keeps the date, and exams are
    scheduled as calendar events, everything else as tasks.

    Args:
        assessment: One confirmed assessment.

    Returns:
        One `GradeCreate` per item, numbered when `count` is above 1.
    """
    names = (
        [assessment.name] if assessment.count == 1
        else [f"{assessment.name} {n}" for n in range(1, assessment.count + 1)]
    )
    schedule = GradeSchedule.EVENT if assessment.category in EXAM_CATEGORIES else GradeSchedule.TASK
    return [
        GradeCreate(
            name=name[:100], max_score=100.0, category=assessment.category,
            # Only the first of a counted group can carry the date the syllabus gave.
            due_date=assessment.due_date if index == 0 else None,
            schedule_as=schedule,
        )
        for index, name in enumerate(names)
    ]


def apply(db: Session, user_id: uuid.UUID, parse_id: uuid.UUID, confirmed: ApplyRequest) -> ApplyResult | None:
    """Build a new course, its weights and its grades from a confirmed parse.

    Everything is validated before anything is written: the term, weights summing to
    100 (bonus aside, within 0.5) and the code being new.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        parse_id: The parse being applied.
        confirmed: The course and assessments as the student confirmed them.

    Returns:
        The new course's id, grades created and the no-change measure; None when the
        parse is missing or another user's.

    Raises:
        ValueError: If the parse was already applied, no term is set or chosen, the
            term is unknown, the weights do not sum to 100, or the code already exists.

    Note:
        Not one transaction: the course commits first, then the grades (deleting the
        course again if they fail), then the rules, then the parse row.
    """
    row = (
        db.query(SyllabusParseModel)
        .filter(SyllabusParseModel.id == parse_id, SyllabusParseModel.user_id == user_id)
        .first()
    )
    if row is None:
        return None
    if row.applied_at is not None:
        raise ValueError("This syllabus has already built a course")

    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    year = confirmed.year or user.current_school_year
    semester = confirmed.semester or user.current_semester
    if not year or not semester:
        raise ValueError("Set your current term in Settings first, or choose the course's term")
    if semester not in {s.value for s in Semester}:
        raise ValueError("That term is not one of Fall, Winter, Spring or Summer")

    weights: dict[GradeCategory, float] = {}
    for a in confirmed.assessments:
        weights[a.category] = weights.get(a.category, 0.0) + a.weight
    counted = sum(weight for category, weight in weights.items() if category != GradeCategory.BONUS)
    if abs(counted - 100) > WEIGHT_TOLERANCE:
        raise ValueError(f"The weights add up to {counted:g}%; they need to add up to 100%")

    # Everything validated before anything is written: a course left behind
    # by a failed grade would be a half-built term nobody asked for.
    course_data = CourseCreate(
        code=confirmed.course_code.strip(), name=confirmed.course_name.strip(),
        year=year, semester=semester, credits=confirmed.credits, professor=confirmed.professor,
        section=confirmed.section,
        category_weights={category: round(weight, 2) for category, weight in weights.items()},
        no_final=GradeCategory.FINAL not in weights,
    )
    grades = [grade for a in confirmed.assessments for grade in grade_rows(a)]
    if db.query(CourseModel).filter(CourseModel.user_id == user_id, CourseModel.code == course_data.code).first():
        raise ValueError(f"You already have a course {course_data.code}")

    course = create_course(db, user_id, course_data)
    try:
        add_grades_bulk(db, user_id, course.id, grades)
    except Exception:
        db.rollback()
        delete_course(db, user_id, course.id)
        raise

    extract = SyllabusExtract.model_validate(row.result)
    file_rules(db, user_id, course.id, extract, confirmed.prerequisites, confirmed.corequisites)
    total, changed = changes(extract, confirmed)
    row.course_id, row.applied_at = course.id, utc_now()
    row.fields_total, row.fields_changed = total, changed
    db.commit()
    return ApplyResult(course_id=course.id, grades_created=len(grades), fields_total=total, fields_changed=changed)


# --- adding to a course you already have (Phase 1 D27) ---------------------
#
# Add-only: a syllabus may give an existing course the assessments it does not
# have yet, and nothing else. It never changes a mark, a weight, a date or a
# name you entered. Weights that differ are reported, not applied.


def _words(name: str) -> tuple[str, ...]:
    """Return a name as comparable words: no case, punctuation or plurals."""
    words = []
    for word in re.sub(r"[^a-z0-9]+", " ", name.lower()).split():
        if word.endswith("zzes"):
            word = word[:-3]          # quizzes -> quiz
        elif word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"    # studies -> study
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]          # assignments -> assignment
        words.append(word)
    return tuple(words)


def match_rows(existing: list, proposed: list) -> list[str | None]:
    """Return, for each proposed (name, category), the existing grade name it matches.

    Same category first by the same words, then by one's words containing the other's
    ("Midterm" covers "Midterm 1"); each existing grade matches at most once.

    Args:
        existing: The course's grade rows.
        proposed: (name, category value) pairs.

    Returns:
        One existing name or None per proposed row, in order.
    """
    available = [(g.name, g.category, set(_words(g.name)), _words(g.name)) for g in existing]
    used: set[int] = set()
    result: list[str | None] = [None] * len(proposed)
    # Exact first, so a loose match never takes a grade an exact one needed.
    for exact in (True, False):
        for index, (name, category) in enumerate(proposed):
            if result[index] is not None:
                continue
            words = _words(name)
            for at, (other_name, other_category, other_set, other_words) in enumerate(available):
                if at in used or other_category != category:
                    continue
                same = words == other_words
                contained = set(words) <= other_set or other_set <= set(words)
                if same if exact else contained:
                    used.add(at)
                    result[index] = other_name
                    break
    return result


def _parse_for(db: Session, user_id: uuid.UUID, parse_id: uuid.UUID) -> SyllabusParseModel | None:
    """Return the caller's parse with this id, or None."""
    return (
        db.query(SyllabusParseModel)
        .filter(SyllabusParseModel.id == parse_id, SyllabusParseModel.user_id == user_id)
        .first()
    )


def preview_add(db: Session, user_id: uuid.UUID, parse_id: uuid.UUID, course_id: uuid.UUID) -> AddPreview | None:
    """Return what a syllabus would add to an existing course; writes nothing.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        parse_id: The parse.
        course_id: The course to add to.

    Returns:
        Every implied row and whether the course has it, weights that differ, unweighted
        categories new rows would use, a section offer, and the rules; None when the
        parse or course is missing or another user's.
    """
    row = _parse_for(db, user_id, parse_id)
    course = get_user_course(db, user_id, course_id)
    if row is None or course is None:
        return None
    extract = SyllabusExtract.model_validate(row.result)
    proposed = [grade for a in extract.assessments for grade in grade_rows(a)]
    matches = match_rows(course.grades, [(g.name, g.category.value) for g in proposed])
    rows = [
        ProposedRow(name=g.name, category=g.category, due_date=g.due_date, exists=m is not None, matched=m)
        for g, m in zip(proposed, matches)
    ]

    stated: dict[GradeCategory, float] = {}
    for a in extract.assessments:
        stated[a.category] = stated.get(a.category, 0.0) + a.weight
    weights = course.category_weights
    notes = [
        WeightNote(category=category, syllabus=round(weight, 2), course=weights.get(category.value, 0.0))
        for category, weight in stated.items()
        if abs(weight - weights.get(category.value, 0.0)) > WEIGHT_TOLERANCE
    ]
    unweighted = sorted(
        {r.category for r in rows if not r.exists and r.category != GradeCategory.BONUS
         and not weights.get(r.category.value, 0.0)},
        key=lambda c: c.value,
    )
    offer = extract.section.strip() if extract.section and not course.section else None
    own = {
        p.kind: render(p.rule) for p in db.query(PrerequisiteProposalModel).filter(
            PrerequisiteProposalModel.user_id == user_id, PrerequisiteProposalModel.course_id == course.id)
    }
    return AddPreview(rows=rows, weight_notes=notes, unweighted=unweighted, section_offer=offer or None,
                      prerequisites=extract.prerequisites, corequisites=extract.corequisites,
                      own_prerequisites=own.get("prerequisite"), own_corequisites=own.get("corequisite"))


def add_to_course(
    db: Session, user_id: uuid.UUID, parse_id: uuid.UUID, course_id: uuid.UUID, request: AddRequest,
) -> AddResult | None:
    """Add the confirmed rows an existing course still lacks; never changes what it has.

    Rows are matched again against the course as it is now, so nothing is duplicated.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        parse_id: The parse.
        course_id: The course to add to.
        request: The rows, the section choice and the rules confirmed.

    Returns:
        How many rows were added and skipped, whether the section was set, and how many
        rules were filed; None when the parse or course is missing or another user's.

    Raises:
        ValueError: If the parse was already used.

    Note:
        Several commits: the new grades with the section, each rule, then the parse row.
    """
    row = _parse_for(db, user_id, parse_id)
    course = get_user_course(db, user_id, course_id)
    if row is None or course is None:
        return None
    if row.applied_at is not None:
        raise ValueError("This syllabus has already been used")

    matches = match_rows(course.grades, [(r.name.strip(), r.category.value) for r in request.rows])
    # Within the request too: two identical rows sent are one row added.
    seen: set[tuple[str, tuple[str, ...]]] = set()
    new: list[GradeCreate] = []
    for r, m in zip(request.rows, matches):
        key = (r.category.value, _words(r.name))
        if m is not None or key in seen:
            continue
        seen.add(key)
        new.append(GradeCreate(
            name=r.name.strip()[:100], max_score=100.0, category=r.category, due_date=r.due_date,
            schedule_as=GradeSchedule.EVENT if r.category in EXAM_CATEGORIES else GradeSchedule.TASK,
        ))

    section_set = False
    if request.set_section and not course.section:
        section = SyllabusExtract.model_validate(row.result).section
        if section and section.strip():
            course.section = section.strip()[:20]
            section_set = True

    if new:
        add_grades_bulk(db, user_id, course.id, new)  # commits, with the section
    filed = file_rules(db, user_id, course.id, SyllabusExtract.model_validate(row.result),
                       request.prerequisites, request.corequisites)
    row.course_id, row.applied_at = course.id, utc_now()
    db.commit()
    return AddResult(added=len(new), skipped=len(request.rows) - len(new), section_set=section_set,
                     rules_filed=filed)

