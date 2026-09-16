from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class Semester(str, Enum):
    FALL = "Fall"
    WINTER = "Winter"
    SPRING = "Spring"
    SUMMER = "Summer"


class AcademicStatusBase(BaseModel):
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
        if self.term_label is not None and self.term_label.strip() == "":
            raise ValueError("term_label cannot be blank if provided")
        return self


class AcademicStatusCreate(AcademicStatusBase):
    pass


class AcademicStatusUpdate(BaseModel):
    school_year: int | None = Field(default=None, ge=1, le=10)
    semester: Semester | None = None
    term_label: str | None = Field(default=None, max_length=20)
    first_year_calendar_year: int | None = Field(default=None, ge=1990, le=2100)

    @model_validator(mode="after")
    def validate_update(self):
        if self.term_label is not None and self.term_label.strip() == "":
            raise ValueError("term_label cannot be blank if provided")
        return self


class AcademicStatus(AcademicStatusBase):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    updated_at: datetime | None = None

    class Config:
        from_attributes = True