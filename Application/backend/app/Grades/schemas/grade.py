from datetime import date
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import GradeCategory, GradeSchedule

#: Kept in step with grade_service.MAX_SCORE_MULTIPLE; defined here to avoid a
#: schema -> service import.
MAX_SCORE_MULTIPLE = 2.0

class GradeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="The name of the grade (e.g., Midterm Exam, Final Project)")
    # Optional so an assignment can be added before it has been marked. Every
    # averaging function already skips grades whose score is None, and the
    # column is nullable; only this schema was forcing a score up front.
    score: float | None = Field(default=None, ge=0, description="The score obtained, or null if not yet graded")
    max_score: float = Field(..., gt=0, description="The maximum possible score for the grade")
    category: GradeCategory = Field(..., description="The category of the grade (e.g., Assignment, Lab, Quiz, etc.)")
    # When the work is due, as opposed to when it was marked.
    due_date: date | None = Field(default=None, description="When the work is due, if it has a deadline")
    # What that date means. An assignment is work to tick off; a midterm is
    # something to sit, which is a calendar block and not a chore. Ignored
    # without a date.
    schedule_as: GradeSchedule = Field(
        default=GradeSchedule.TASK,
        description="task: raises a task that closes when marked. event: a calendar block only.",
    )

    @model_validator(mode="after")
    def validate_grade_logic(self):
        if self.name.strip() == "":
            raise ValueError("Grade name cannot be empty")
        # Bonus marks are real, so a score may exceed its max -- but not by an
        # implausible multiple, which catches a slipped digit.
        if self.score is not None and self.score > self.max_score * MAX_SCORE_MULTIPLE:
            raise ValueError(f"Score cannot exceed {MAX_SCORE_MULTIPLE:g}x the max score")

        return self
 
class GradeCreate(GradeBase):
    pass

class GradeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    category: GradeCategory | None = Field(default=None)
    due_date: date | None = Field(default=None)
    schedule_as: GradeSchedule | None = Field(default=None)

class Grade(GradeBase):
    id: UUID = Field(default_factory=uuid4)
    weight: float = Field(..., ge=0, le=100, description="The weight assigned by the grade category")

    class Config:
        from_attributes = True
