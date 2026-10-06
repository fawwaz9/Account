"""Syllabus intake: what a parse returns, and what a person confirms (Phase 1 item 1)."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.Grades.utils.enums import GradeCategory
from app.Grades.utils.prerequisites import RuleError, parse_text, render, validate

#: A syllabus is a few pages. The cap is about the wrong file, not abuse.
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_BASE64_CHARS = (MAX_FILE_BYTES * 4) // 3 + 4
MEDIA_TYPES = ("application/pdf", "text/plain")


class ExtractedAssessment(BaseModel):
    """One graded thing, as the model read it. Lenient on purpose: whatever the
    model gets wrong, the person sees and fixes on the verification screen."""

    name: str = Field(default="", max_length=100)
    category: GradeCategory = GradeCategory.OTHER
    #: Percent of the course grade, for all of them together when count > 1.
    weight: float = Field(default=0.0, ge=0, le=100)
    #: How many there are: "10 weekly quizzes" is one line with count 10.
    count: int = Field(default=1, ge=1, le=60)
    due_date: date | None = None
    #: Known to exist but not yet scheduled -- a UBC final, most of all.
    date_tba: bool = False

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value):
        """An unrecognised category is Other, never a failed parse."""
        if isinstance(value, str):
            for category in GradeCategory:
                if category.value.lower() == value.strip().lower():
                    return category
            return GradeCategory.OTHER
        return value

    @field_validator("due_date", mode="before")
    @classmethod
    def _date(cls, value):
        if value in ("", None, "TBA", "tba"):
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


class ExtractedRule(BaseModel):
    """Prerequisites as the model read them (Phase 2 item 5). Lenient like the
    rest: a tree that does not hold up becomes None and ``text`` empty, and the
    person types the rule on the check screen. ``sentence`` is the syllabus's
    own words -- kept with the person, never shared (D6)."""

    rule: dict | None = None
    text: str = ""
    note: str | None = Field(default=None, max_length=300)
    sentence: str | None = Field(default=None, max_length=500)

    @field_validator("note", "sentence", mode="before")
    @classmethod
    def _trim(cls, value):
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value[:500] or None

    @model_validator(mode="after")
    def _readable(self):
        try:
            self.rule = validate(self.rule) if self.rule is not None else None
        except RuleError:
            self.rule = None
        self.text = render(self.rule) if self.rule is not None else ""
        return self


def _rule_or_none(value):
    """A model answer that is not an object, or says nothing, is no rule."""
    if not isinstance(value, dict):
        return None
    if not any(value.get(key) for key in ("rule", "note", "sentence")):
        return None
    return value


class SyllabusExtract(BaseModel):
    course_code: str = Field(default="", max_length=20)
    course_name: str = Field(default="", max_length=100)
    #: The section the syllabus is for ("101"), when it says. A syllabus
    #: belongs to one section, so this is what it will be matched on.
    section: str | None = Field(default=None, max_length=20)
    professor: str | None = Field(default=None, max_length=100)
    assessments: list[ExtractedAssessment] = Field(default_factory=list, max_length=80)
    #: True when the syllabus offers more than one grading scheme. Only the
    #: first is extracted for now; this says so rather than hiding it.
    multiple_schemes: bool = False
    #: Phase 2 item 5: what the syllabus says must come before, and alongside.
    prerequisites: ExtractedRule | None = None
    corequisites: ExtractedRule | None = None

    @field_validator("prerequisites", "corequisites", mode="before")
    @classmethod
    def _rules(cls, value):
        return _rule_or_none(value)


class ConfirmedRule(BaseModel):
    """A rule as the person confirmed it on the check screen, in the typed form."""

    text: str = Field(..., min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _readable(self):
        parse_text(self.text)  # RuleError is a ValueError: a 422 naming the problem
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class SyllabusUpload(BaseModel):
    filename: str = Field(default="syllabus.pdf", max_length=200)
    media_type: str = Field(default="application/pdf")
    content_base64: str = Field(..., max_length=MAX_BASE64_CHARS)


class ParseResult(BaseModel):
    id: UUID
    extract: SyllabusExtract
    #: Things to look at before confirming: weights that do not sum to 100, a
    #: weighted assessment with no date, a date outside the term.
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class ApplyAssessment(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: GradeCategory
    weight: float = Field(..., ge=0, le=100)
    count: int = Field(default=1, ge=1, le=60)
    due_date: date | None = None
    date_tba: bool = False


class ApplyRequest(BaseModel):
    """What the person confirmed: the course, and every assessment as edited."""

    course_code: str = Field(..., min_length=3, max_length=20)
    course_name: str = Field(..., min_length=1, max_length=100)
    section: str | None = Field(default=None, max_length=20)
    professor: str | None = Field(default=None, max_length=100)
    credits: float = Field(default=3.0, ge=0.5, le=10.0)
    #: The term the course is in. Null uses the term set in Settings.
    year: int | None = Field(default=None, ge=1, le=10)
    semester: str | None = None
    assessments: list[ApplyAssessment] = Field(..., min_length=1, max_length=80)
    #: Filed as your own rules (Phase 2 item 5) -- only when sent. Leaving one
    #: out files nothing: nothing becomes a record without confirmation.
    prerequisites: ConfirmedRule | None = None
    corequisites: ConfirmedRule | None = None


class ApplyResult(BaseModel):
    course_id: UUID
    grades_created: int
    #: The no-change measure (account-vision.md §15): how many of the parse's
    #: fields the person changed before confirming.
    fields_total: int
    fields_changed: int


class IntakeStatus(BaseModel):
    #: False until a provider and key are configured on the server.
    available: bool


class KeptSyllabus(BaseModel):
    """A syllabus file kept behind a course (Phase 1 D24)."""

    id: UUID
    filename: str | None
    media_type: str | None
    created_at: datetime


# --- adding to a course you already have (Phase 1 D27) ---------------------

class ProposedRow(BaseModel):
    """One gradebook row the syllabus implies, and whether the course has it."""

    name: str
    category: GradeCategory
    due_date: date | None = None
    #: The course already has this; it is shown, never added.
    exists: bool
    #: The existing row it was matched to, when it exists.
    matched: str | None = None


class WeightNote(BaseModel):
    """A weight the syllabus states that differs from the course's. Information
    only: adding never changes a weight."""

    category: GradeCategory
    syllabus: float
    course: float


class AddPreview(BaseModel):
    rows: list[ProposedRow]
    weight_notes: list[WeightNote] = Field(default_factory=list)
    #: Categories new rows would go into that the course weights at 0%, so they
    #: would not count until a weight is set.
    unweighted: list[GradeCategory] = Field(default_factory=list)
    #: The syllabus's section, offered only when the course has none.
    section_offer: str | None = None
    #: What the syllabus says the course requires (Phase 2 item 5), and your
    #: own rule for it now, which confirming would replace.
    prerequisites: ExtractedRule | None = None
    corequisites: ExtractedRule | None = None
    own_prerequisites: str | None = None
    own_corequisites: str | None = None


class AddRow(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: GradeCategory
    due_date: date | None = None


class AddRequest(BaseModel):
    rows: list[AddRow] = Field(..., max_length=200)
    #: Fill in the course's empty section from the syllabus.
    set_section: bool = False
    prerequisites: ConfirmedRule | None = None
    corequisites: ConfirmedRule | None = None


class AddResult(BaseModel):
    added: int
    #: Rows sent that the course already had by the time they arrived.
    skipped: int
    section_set: bool = False
    #: Prerequisite rules filed as yours (Phase 2 item 5).
    rules_filed: int = 0

