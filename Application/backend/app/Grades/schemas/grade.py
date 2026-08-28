from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import GradeCategory

class GradeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="The name of the grade (e.g., Midterm Exam, Final Project)")
    # Optional so an assignment can be added before it has been marked. Every
    # averaging function already skips grades whose score is None, and the
    # column is nullable; only this schema was forcing a score up front.
    score: float | None = Field(default=None, ge=0, description="The score obtained, or null if not yet graded")
    max_score: float = Field(..., gt=0, description="The maximum possible score for the grade")
    category: GradeCategory = Field(..., description="The category of the grade (e.g., Assignment, Lab, Quiz, etc.)")

    @model_validator(mode="after")
    def validate_grade_logic(self):
        if self.name.strip() == "":
            raise ValueError("Grade name cannot be empty")
        if self.score is not None and self.score > self.max_score:
            raise ValueError("Score cannot be greater than max score")

        return self
 
class GradeCreate(GradeBase):
    pass

class GradeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    category: GradeCategory | None = Field(default=None)

class Grade(GradeBase):
    id: UUID = Field(default_factory=uuid4)
    weight: float = Field(..., ge=0, le=100, description="The weight assigned by the grade category")

    class Config:
        from_attributes = True
