"""A syllabus in, a course out -- with a person checking everything in between.

Phase 1 item 1 (account-vision.md §13.8, §13.12). Upload a syllabus and the
term builds itself: assessments, weights, dated exams, due dates. Three rules
carry it:

* **Nothing becomes a record without confirmation.** The parse is shown, every
  field editable; only what the person confirms is written. A hallucinated
  weight in a grade projection is exactly the failure this exists to avoid
  (§9.4).
* **Checks are deterministic and run on every parse,** so the screen can point
  at what to look at: weights that do not sum to 100, a weighted assessment
  with no date that is not marked TBA, a date outside the term. A UBC final is
  TBA -- a state, not a failure.
* **The no-change measure is recorded.** Of the fields the parse produced, how
  many the person changed (§15): the precision proxy that says whether the
  extraction can be trusted, and which fields to improve next.

What is sent to the model is the syllabus and the term's dates, nothing else:
no name, no email, no id.
"""

import base64
import binascii
import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import CourseModel, SyllabusParseModel, UserModel, utc_now
from app.config import settings
from app.Grades.schemas.course import CourseCreate
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.course_service import create_course, delete_course
from app.Grades.services.grade_service import add_grades_bulk
from app.Grades.utils.enums import GradeCategory, GradeSchedule, Semester
from app.Grades.utils.terms import term_dates
from app.Intake.schemas.syllabus import (
    MAX_FILE_BYTES,
    MEDIA_TYPES,
    ApplyRequest,
    ApplyResult,
    ParseResult,
    SyllabusExtract,
    SyllabusUpload,
)
from app.Intake.services import llm
from app.shared.dates import user_today

#: Weights are percentages; a syllabus rounds.
WEIGHT_TOLERANCE = 0.5
#: Exams are sat, not completed, so they go on the calendar rather than a list.
EXAM_CATEGORIES = {GradeCategory.MIDTERM, GradeCategory.FINAL}

SYSTEM = (
    "You extract the grading structure of a university course from its syllabus. "
    "Report only what the document says. Never invent an assessment, a weight or a date. "
    "Answer with a single JSON object and nothing else."
)


def prompt(term_start: date | None, term_end: date | None) -> str:
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
  ]
}}
Rules:
- One entry per distinct graded item or group; if the schedule lists dated items of a group
  separately (Assignment 1 due Sep 26, Assignment 2 due Oct 10), give each its own entry and
  split the group's weight evenly between them.
- If there is more than one grading scheme, extract only the first and set multiple_schemes.
- Bonus or extra credit uses the category Bonus.
- {term}"""


class RateLimited(Exception):
    pass


def parse(db: Session, user_id: uuid.UUID, upload: SyllabusUpload, *, transport=None) -> ParseResult:
    """Read a syllabus. Writes no course and no grade -- only the parse, for the cap and the measure."""
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

    today = user_today(db, user_id)
    used_today = (
        db.query(func.count(SyllabusParseModel.id))
        .filter(SyllabusParseModel.user_id == user_id, func.date(SyllabusParseModel.created_at) == today)
        .scalar()
    )
    if used_today >= settings.LLM_PARSES_PER_DAY:
        raise RateLimited

    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    span = term_dates(user.current_semester, user.current_school_year, user.first_year_calendar_year)
    start, end = span if span else (None, None)
    raw = llm.extract_document(
        content, upload.media_type, upload.filename, SYSTEM, prompt(start, end), transport=transport,
    )
    extract = SyllabusExtract.model_validate(_clean(raw))

    row = SyllabusParseModel(
        id=uuid.uuid4(), user_id=user_id, filename=upload.filename,
        provider=settings.LLM_PROVIDER, model=settings.LLM_MODEL_EXTRACT,
        result=extract.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    return ParseResult(id=row.id, extract=extract, warnings=check(extract, start, end), created_at=row.created_at)


def _clean(raw: dict) -> dict:
    """Drop assessment entries the model left unusable rather than fail the whole parse."""
    items = raw.get("assessments") if isinstance(raw.get("assessments"), list) else []
    raw = dict(raw)
    raw["assessments"] = [item for item in items if isinstance(item, dict) and item.get("name")]
    return raw


def check(extract: SyllabusExtract, term_start: date | None, term_end: date | None) -> list[str]:
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
    return warnings


FIELDS = ("name", "category", "weight", "count", "due_date", "date_tba")


def changes(extracted: SyllabusExtract, confirmed: ApplyRequest) -> tuple[int, int]:
    """(fields the parse produced, fields the person changed). Row by row; a row
    added or removed counts every one of its fields as changed."""
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
    """One gradebook row per assessment, or per item of a counted group."""
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
    """Build the course from what the person confirmed. None if the parse is not theirs."""
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

    total, changed = changes(SyllabusExtract.model_validate(row.result), confirmed)
    row.course_id, row.applied_at = course.id, utc_now()
    row.fields_total, row.fields_changed = total, changed
    db.commit()
    return ApplyResult(course_id=course.id, grades_created=len(grades), fields_total=total, fields_changed=changed)
