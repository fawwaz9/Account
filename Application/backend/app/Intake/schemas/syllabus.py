"""Schemas for syllabus intake: what a parse returns, and what the student confirms.

The `Extracted*` and `SyllabusExtract` models read a language model's answer and are
meant to be lenient, coercing what they can; the `Apply*`, `Add*` and
`ConfirmedRule` models are what the student sends back after checking it.
"""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.Grades.utils.enums import GradeCategory
from app.Grades.utils.prerequisites import RuleError, parse_text, render, validate

#: A syllabus is a few pages. The cap is about the wrong file, not abuse.
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_BASE64_CHARS = (MAX_FILE_BYTES * 4) // 3 + 4
"""Longest base64 text a `MAX_FILE_BYTES` file can encode to."""
MEDIA_TYPES = ("application/pdf", "text/plain")
"""The file types a syllabus may be uploaded as."""


class ExtractedAssessment(BaseModel):
    """One graded item as the model read it; the student checks and fixes it before use.

    Attributes:
        name: Item name, at most 100 characters.
        category: Grade category; an unrecognised one becomes Other.
        weight: Percent of the course grade, 0-100, for all of them together when
            `count` is above 1.
        count: How many there are, 1-60 ("10 weekly quizzes" is one line with 10).
        due_date: Due date; anything unreadable, or "TBA", becomes None.
        date_tba: Known to exist but not yet scheduled, such as a final exam.
    """

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
        """Match a category name case-insensitively, falling back to Other."""
        if isinstance(value, str):
            for category in GradeCategory:
                if category.value.lower() == value.strip().lower():
                    return category
            return GradeCategory.OTHER
        return value

    @field_validator("due_date", mode="before")
    @classmethod
    def _date(cls, value):
        """Read an ISO date from the first ten characters, else None."""
        if value in ("", None, "TBA", "tba"):
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


class ExtractedRule(BaseModel):
    """A prerequisite or co-requisite as the model read it.

    A tree that fails validation becomes None with empty text, and the student types
    the rule instead.

    Attributes:
        rule: The rule tree, validated; None when absent or unusable.
        text: The tree in its typed form; empty when there is none.
        note: What the tree cannot say, at most 300 characters.
        sentence: The syllabus's own wording, at most 500 characters; kept with the
            student and never shared.
    """

    rule: dict | None = None
    text: str = ""
    note: str | None = Field(default=None, max_length=300)
    sentence: str | None = Field(default=None, max_length=500)

    @field_validator("note", "sentence", mode="before")
    @classmethod
    def _trim(cls, value):
        """Strip a note or sentence, cut to 500 characters; non-text is None."""
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value[:500] or None

    @model_validator(mode="after")
    def _readable(self):
        """Validate the tree, dropping it if invalid, and render its text."""
        try:
            self.rule = validate(self.rule) if self.rule is not None else None
        except RuleError:
            self.rule = None
        self.text = render(self.rule) if self.rule is not None else ""
        return self


def _rule_or_none(value):
    """Return the model's rule object, or None if not an object or empty."""
    if not isinstance(value, dict):
        return None
    if not any(value.get(key) for key in ("rule", "note", "sentence")):
        return None
    return value


class SyllabusExtract(BaseModel):
    """Everything a parse read from one syllabus.

    Attributes:
        course_code: Course code, at most 20 characters.
        course_name: Course title, at most 100 characters.
        section: Section the syllabus is for, at most 20 characters, if it says.
        professor: Instructor's name, at most 100 characters.
        assessments: At most 80 graded items.
        multiple_schemes: The syllabus offers more than one grading scheme; only the
            first was read.
        prerequisites: What must come before, or None.
        corequisites: What must be taken alongside, or None.
    """
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
        """Turn an empty or non-object rule answer into None."""
        return _rule_or_none(value)


class ConfirmedRule(BaseModel):
    """A rule as the student confirmed it, in the typed form.

    Attributes:
        text: The typed rule, 1-300 characters; must parse.
        note: What the rule cannot say, at most 300 characters; blank becomes None.
    """

    text: str = Field(..., min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _readable(self):
        """Parse the typed rule to prove it reads, and blank a whitespace note to None.

        Raises:
            RuleError: If the text is not a valid rule (a ValueError, so a 422).
        """
        parse_text(self.text)  # RuleError is a ValueError: a 422 naming the problem
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class SyllabusUpload(BaseModel):
    """Request body uploading a syllabus to read.

    Attributes:
        filename: File name as the browser gave it, at most 200 characters.
        media_type: "application/pdf" or "text/plain"; checked by the service.
        content_base64: The file, base64-encoded; at most `MAX_BASE64_CHARS` characters.
    """
    filename: str = Field(default="syllabus.pdf", max_length=200)
    media_type: str = Field(default="application/pdf")
    content_base64: str = Field(..., max_length=MAX_BASE64_CHARS)


class ParseResult(BaseModel):
    """A syllabus parse, for the verification screen.

    Attributes:
        id: The parse's id, used to apply it.
        extract: What was read.
        warnings: Things to check first: weights not summing to 100, a weighted item
            with no date, a date outside the term.
        created_at: When the parse ran (naive UTC).
    """
    id: UUID
    extract: SyllabusExtract
    #: Things to look at before confirming: weights that do not sum to 100, a
    #: weighted assessment with no date, a date outside the term.
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class ApplyAssessment(BaseModel):
    """One assessment as the student confirmed it.

    Attributes:
        name: Item name, 1-100 characters.
        category: Grade category.
        weight: Percent of the course grade, 0-100, for all of them together.
        count: How many there are, 1-60.
        due_date: Due date, or None.
        date_tba: Scheduled later, such as a final exam.
    """
    name: str = Field(..., min_length=1, max_length=100)
    category: GradeCategory
    weight: float = Field(..., ge=0, le=100)
    count: int = Field(default=1, ge=1, le=60)
    due_date: date | None = None
    date_tba: bool = False


class ApplyRequest(BaseModel):
    """Request body building a new course from a confirmed parse.

    Attributes:
        course_code: Course code, 3-20 characters.
        course_name: Course title, 1-100 characters.
        section: Section, at most 20 characters.
        professor: Instructor's name, at most 100 characters.
        credits: Credit value, 0.5-10.
        year: School year, 1-10; null uses the one in Settings.
        semester: Term name; null uses the one in Settings, and the service rejects an
            unknown term.
        assessments: 1-80 confirmed assessments.
        prerequisites: The rule to file as the student's own; omitted files nothing.
        corequisites: The co-requisite rule to file; omitted files nothing.
    """

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
    """What applying a parse built.

    Attributes:
        course_id: The new course.
        grades_created: Grades written.
        fields_total: Fields the parse produced.
        fields_changed: How many of them the student changed before confirming.
    """
    course_id: UUID
    grades_created: int
    #: The no-change measure (account-vision.md §15): how many of the parse's
    #: fields the person changed before confirming.
    fields_total: int
    fields_changed: int


class IntakeStatus(BaseModel):
    """Whether syllabus reading is set up on this server.

    Attributes:
        available: False until a provider, model and key are configured.
    """
    #: False until a provider and key are configured on the server.
    available: bool


class KeptSyllabus(BaseModel):
    """A syllabus file kept behind a course.

    Attributes:
        id: The parse's id, which names the stored file.
        filename: File name as uploaded, or None.
        media_type: MIME type, or None.
        created_at: When it was uploaded (naive UTC).
    """

    id: UUID
    filename: str | None
    media_type: str | None
    created_at: datetime


# --- adding to a course you already have (Phase 1 D27) ---------------------

class ProposedRow(BaseModel):
    """One gradebook row a syllabus implies for a course, and whether it exists.

    Attributes:
        name: Row name.
        category: Grade category.
        due_date: Due date, or None.
        exists: The course already has it; shown but never added.
        matched: Name of the existing row it matched, when it exists.
    """

    name: str
    category: GradeCategory
    due_date: date | None = None
    #: The course already has this; it is shown, never added.
    exists: bool
    #: The existing row it was matched to, when it exists.
    matched: str | None = None


class WeightNote(BaseModel):
    """A weight the syllabus states that differs from the course's; information only.

    Attributes:
        category: The grade category.
        syllabus: The syllabus's weight.
        course: The course's weight, which adding never changes.
    """

    category: GradeCategory
    syllabus: float
    course: float


class AddPreview(BaseModel):
    """What adding a syllabus to an existing course would do.

    Attributes:
        rows: Every row the syllabus implies, existing or new.
        weight_notes: Weights that differ from the course's.
        unweighted: Categories new rows would use that the course weights at 0%.
        section_offer: The syllabus's section, offered only when the course has none.
        prerequisites: The syllabus's prerequisite rule, or None.
        corequisites: The syllabus's co-requisite rule, or None.
        own_prerequisites: The student's current prerequisite rule, which confirming
            would replace.
        own_corequisites: The student's current co-requisite rule.
    """
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
    """One new gradebook row the student chose to add.

    Attributes:
        name: Row name, 1-100 characters.
        category: Grade category.
        due_date: Due date, or None.
    """
    name: str = Field(..., min_length=1, max_length=100)
    category: GradeCategory
    due_date: date | None = None


class AddRequest(BaseModel):
    """Request body adding confirmed rows and rules to an existing course.

    Attributes:
        rows: At most 200 rows to add.
        set_section: Fill the course's empty section from the syllabus.
        prerequisites: Prerequisite rule to file as the student's own.
        corequisites: Co-requisite rule to file as the student's own.
    """
    rows: list[AddRow] = Field(..., max_length=200)
    #: Fill in the course's empty section from the syllabus.
    set_section: bool = False
    prerequisites: ConfirmedRule | None = None
    corequisites: ConfirmedRule | None = None


class AddResult(BaseModel):
    """What adding to an existing course did.

    Attributes:
        added: Rows written.
        skipped: Rows the course already had by the time they arrived.
        section_set: Whether the section was filled in.
        rules_filed: Rules filed as the student's own.
    """
    added: int
    #: Rows sent that the course already had by the time they arrived.
    skipped: int
    section_set: bool = False
    #: Prerequisite rules filed as yours (Phase 2 item 5).
    rules_filed: int = 0

