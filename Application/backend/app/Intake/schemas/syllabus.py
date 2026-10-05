"""Syllabus intake: what a parse returns, and what a person confirms (Phase 1 item 1)."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.Grades.utils.enums import GradeCategory

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

