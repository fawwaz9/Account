from uuid import UUID, uuid4
from typing import List
from pydantic import BaseModel, Field, model_validator

from app.Grades.schemas.grade import Grade
from app.Grades.utils.enums import GradeCategory, Semester
from app.shared.errors import weight_error

def default_category_weights() -> dict[GradeCategory, float]:
    return dict.fromkeys(GradeCategory, 0.0)

def normalize_category_weights(
    weights: dict[GradeCategory, float] | None
) -> dict[GradeCategory, float]:
    normalized = default_category_weights()
    if weights:
        normalized.update(weights)

    for weight in normalized.values():
        if weight < 0 or weight > 100:
            raise ValueError(weight_error["invalid_weight_value"])

    total_weight = sum(normalized.values())
    if total_weight > 100:
        raise ValueError(weight_error["invalid_weights"])

    return normalized

class CourseBase(BaseModel):
    code: str = Field(..., min_length=3, max_length=20, description="The unique code for the course (e.g., CS101, MATH202)")
    name: str = Field(..., min_length=1, max_length=100, description="The name of the course (e.g., Introduction to Computer Science, Calculus II)")
    year: int = Field(..., ge=1, le=10, description="The academic year of the course (e.g., 1 for first year, 2 for second year, etc.)")
    semester: Semester = Field(..., description="The semester in which the course is offered")
    credits: float = Field(default=3.0, ge=0.5, le=10.0, description="The number of credits for the course")
    required: bool = Field(default=True, description="Indicates if the course is required or elective")
    professor: str = Field(..., min_length=3, max_length=100, description="The name of the professor teaching the course")
    final_grade: float = Field(default=0.0, ge=0, le=100, description="The final grade for the course submitted by the professor")
    category_weights: dict[GradeCategory, float] = Field(default_factory=default_category_weights, description="Weights by grade category")
    
    @model_validator(mode="after")
    def validate_course_logic(self):
        if self.code.strip() == "":
            raise ValueError("course code cannot be empty")

        if self.name.strip() == "":
            raise ValueError("course name cannot be empty")

        if self.final_grade > 0 and self.final_grade < 0:
            raise ValueError("invalid final grade")

        self.category_weights = normalize_category_weights(self.category_weights)
        return self

class CourseCreate(CourseBase):
    pass

class CategoryWeightsUpdate(BaseModel):
    category_weights: dict[GradeCategory, float] = Field(..., description="Category weights to update")

    @model_validator(mode="after")
    def validate_category_weights(self):
        for weight in self.category_weights.values():
            if weight < 0 or weight > 100:
                raise ValueError(weight_error["invalid_weight_value"])

        return self

class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=3, max_length=20, description="The unique code for the course (e.g., CS101, MATH202)")
    name: str | None = Field(default=None, min_length=1, max_length=100, description="The name of the course (e.g., Introduction to Computer Science, Calculus II)")
    year: int | None = Field(default=None, ge=1, le=10, description="The academic year of the course (e.g., 1 for first year, 2 for second year, etc.)")
    semester: Semester | None = Field(default=None, description="The semester in which the course is offered")
    credits: float | None = Field(default=None, ge=0.5, le=10.0, description="The number of credits for the course")
    required: bool | None = Field(default=None, description="Indicates if the course is required or elective")
    professor: str | None = Field(default=None, min_length=3, max_length=100, description="The name of the professor teaching the course")
    final_grade: float | None = Field(default=None, ge=0, le=100, description="The final grade for the course submitted by the professor")
    category_weights: dict[GradeCategory, float] | None = Field(default=None, description="Weights by grade category")

    @model_validator(mode="after")
    def validate_course_update(self):
        if self.category_weights is not None:
            for weight in self.category_weights.values():
                if weight < 0 or weight > 100:
                    raise ValueError(weight_error["invalid_weight_value"])

        return self

class Course(CourseBase):
    id: UUID = Field(default_factory=uuid4)
    average: float = 0.0

    class Config:
        from_attributes = True

class CourseDetail(Course):
    grades: List[Grade] =  Field(default_factory=list)
    start_date: str | None = Field(default=None, description="The start date of the course in YYYY-MM-DD format")
    end_date: str | None = Field(default=None, description="The end date of the course in YYYY-MM-DD format")

    class Config:
        from_attributes = True
