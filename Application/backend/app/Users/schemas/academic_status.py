"""Request bodies for the student's academic status: school year, term and anchor.

Only `AcademicStatusUpdate` is used, by `PATCH /api/users/{user_id}/academic-status`
through `user_service.update_academic_status`.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class Semester(str, Enum):
    """A term of the school year; a copy of `app.Grades.utils.enums.Semester`."""
    FALL = "Fall"
    WINTER = "Winter"
    SPRING = "Spring"
    SUMMER = "Summer"


class AcademicStatusBase(BaseModel):
    """The academic status fields with their limits.

    Attributes:
        school_year: School year the student is in, 1-10.
        semester: The term they are in now; Fall by default.
        term_label: Display label such as "2025-2026", at most 20 characters, not blank.
        first_year_calendar_year: First-year anchor, 1990-2100; None leaves terms
            undated.
    """
    school_year: int = Field(..., ge=1, le=10, description="1 = first year, 2 = second year, etc.")
    semester: Semester = Field(default=Semester.FALL)
    term_label: str | None = Field(
        default=None,
        max_length=20,
        description="Optional display label, e.g. '2025-2026'",
    )
    #: The calendar year school year 1's Fall began, which is what turns
    #: "Fall of year 3" into real dates. Bounded to keep a typo out: a course
    #: dated 202 or 20250 would sort before or after everything forever.
    first_year_calendar_year: int | None = Field(
        default=None, ge=1990, le=2100,
        description="Calendar year in which first year began, e.g. 2023",
    )

    @model_validator(mode="after")
    def validate_term_label(self):
        """Reject a term label that is only whitespace.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If `term_label` is given but blank (a 422).
        """
        if self.term_label is not None and self.term_label.strip() == "":
            raise ValueError("term_label cannot be blank if provided")
        return self


class AcademicStatusCreate(AcademicStatusBase):
    """A complete academic status; the same fields as `AcademicStatusBase`."""
    pass


class AcademicStatusUpdate(BaseModel):
    """Request body for changing the academic status; omitted fields stay as they are.

    Attributes:
        school_year: New school year, 1-10; null clears it.
        semester: New current term; null clears it.
        term_label: New label, at most 20 characters, not blank; null clears it.
        first_year_calendar_year: New first-year anchor, 1990-2100; null clears it.
    """
    school_year: int | None = Field(default=None, ge=1, le=10)
    semester: Semester | None = None
    term_label: str | None = Field(default=None, max_length=20)
    first_year_calendar_year: int | None = Field(default=None, ge=1990, le=2100)

    @model_validator(mode="after")
    def validate_update(self):
        """Reject a term label that is only whitespace.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If `term_label` is given but blank (a 422).
        """
        if self.term_label is not None and self.term_label.strip() == "":
            raise ValueError("term_label cannot be blank if provided")
        return self


class AcademicStatus(AcademicStatusBase):
    """An academic status as a stored record; nothing in the app builds one.

    Attributes:
        id: Record id; a fresh UUID by default.
        user_id: The student it belongs to.
        updated_at: When it last changed; None if unknown.
    """
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    updated_at: datetime | None = None

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True
