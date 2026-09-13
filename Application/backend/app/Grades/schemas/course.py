from datetime import date
from uuid import UUID, uuid4
from typing import List
from pydantic import BaseModel, Field, model_validator

from app.Grades.schemas.grade import Grade
from app.Grades.utils.enums import GradeCategory, Semester
from app.shared.errors import MAX_TOTAL_WEIGHT, weight_error

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
    if total_weight > MAX_TOTAL_WEIGHT:
        raise ValueError(weight_error["invalid_weights"])

    return normalized

class CourseBase(BaseModel):
    code: str = Field(..., min_length=3, max_length=20, description="The unique code for the course (e.g., CS101, MATH202)")
    name: str = Field(..., min_length=1, max_length=100, description="The name of the course (e.g., Introduction to Computer Science, Calculus II)")
    year: int = Field(..., ge=1, le=10, description="The academic year of the course (e.g., 1 for first year, 2 for second year, etc.)")
    semester: Semester = Field(..., description="The semester in which the course is offered")
    credits: float = Field(default=3.0, ge=0.5, le=10.0, description="The number of credits for the course")
    required: bool = Field(default=True, description="Indicates if the course is required or elective")
    professor: str | None = Field(default=None, max_length=100, description="The name of the professor teaching the course")
    final_grade: float = Field(default=0.0, ge=0, le=100, description="The final grade for the course submitted by the professor")
    target_grade: float | None = Field(default=None, ge=0, le=100, description="The grade you are aiming for; null uses the account default")
    category_weights: dict[GradeCategory, float] = Field(default_factory=default_category_weights, description="Weights by grade category")
    # Typed as date, not str: the column is Column(Date), and Pydantic v2 will not
    # coerce a date into a str -- it raises. Serialization still emits ISO strings.
    start_date: date | None = Field(default=None, description="The date the course starts")
    end_date: date | None = Field(default=None, description="The date the course ends")
    # Three independent flags rather than one status, because they combine: a
    # transfer credit can also be archived.
    no_final: bool = Field(default=False, description="No final exam, so a missing final grade is not a problem to act on")
    transfer_credit: bool = Field(default=False, description="Credit granted without taking the course; contributes credits and no grade")
    archived: bool = Field(default=False, description="Still searchable and still in the average, but no longer counted toward credits completed")

    @model_validator(mode="after")
    def validate_course_logic(self):
        if self.code.strip() == "":
            raise ValueError("course code cannot be empty")

        if self.name.strip() == "":
            raise ValueError("course name cannot be empty")

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end date cannot be before start date")

        # Nothing is marked in a transfer credit, so a final grade on one is a
        # contradiction rather than a value to store and then have to explain
        # every time an average leaves it out.
        if self.transfer_credit and self.final_grade:
            raise ValueError("A transfer credit carries credits, not a grade")

        self.category_weights = normalize_category_weights(self.category_weights)
        return self

class CourseCreate(CourseBase):
    pass

class CategoryWeightsUpdate(BaseModel):
    category_weights: dict[GradeCategory, float] = Field(..., description="Category weights to update")

    @model_validator(mode="after")
    def validate_category_weights(self):
        total = 0.0
        for weight in self.category_weights.values():
            if weight < 0 or weight > 100:
                raise ValueError(weight_error["invalid_weight_value"])
            total += weight

        if total > MAX_TOTAL_WEIGHT:
            raise ValueError(weight_error["invalid_weights"])

        return self

class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=3, max_length=20, description="The unique code for the course (e.g., CS101, MATH202)")
    name: str | None = Field(default=None, min_length=1, max_length=100, description="The name of the course (e.g., Introduction to Computer Science, Calculus II)")
    year: int | None = Field(default=None, ge=1, le=10, description="The academic year of the course (e.g., 1 for first year, 2 for second year, etc.)")
    semester: Semester | None = Field(default=None, description="The semester in which the course is offered")
    credits: float | None = Field(default=None, ge=0.5, le=10.0, description="The number of credits for the course")
    required: bool | None = Field(default=None, description="Indicates if the course is required or elective")
    professor: str | None = Field(default=None, max_length=100, description="The name of the professor teaching the course")
    final_grade: float | None = Field(default=None, ge=0, le=100, description="The final grade for the course submitted by the professor")
    target_grade: float | None = Field(default=None, ge=0, le=100, description="The grade you are aiming for; null uses the account default")
    category_weights: dict[GradeCategory, float] | None = Field(default=None, description="Weights by grade category")
    start_date: date | None = Field(default=None, description="The date the course starts")
    end_date: date | None = Field(default=None, description="The date the course ends")
    no_final: bool | None = Field(default=None, description="No final exam, so a missing final grade is not a problem to act on")
    transfer_credit: bool | None = Field(default=None, description="Credit granted without taking the course; contributes credits and no grade")
    archived: bool | None = Field(default=None, description="Still searchable and still in the average, but no longer counted toward credits completed")

    @model_validator(mode="after")
    def validate_course_update(self):
        if self.category_weights is not None:
            total = 0.0
            for weight in self.category_weights.values():
                if weight < 0 or weight > 100:
                    raise ValueError(weight_error["invalid_weight_value"])
                total += weight

            if total > MAX_TOTAL_WEIGHT:
                raise ValueError(weight_error["invalid_weights"])

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end date cannot be before start date")

        return self

class Course(CourseBase):
    id: UUID = Field(default_factory=uuid4)
    #: Null when the course has no marked work, rather than 0.0.
    #:
    #: Zero is a real grade and "not marked yet" is not, and reporting the
    #: second as the first makes a course you have not started read as a
    #: course you are failing. Same reason the cumulative average is nullable.
    #:
    #: Read from `reported_average`, which the service attaches, specifically so
    #: that deciding what to report never means assigning to the mapped
    #: `average` column -- a read that writes is one stray commit from a GET
    #: that changes data.
    average: float | None = Field(default=None, validation_alias="reported_average")
    # Both computed server-side so one grade scale and one term comparison
    # serve the list, the course page, and search alike.
    letter_grade: str = Field(default="", description="Letter grade for the current average")
    grade_points: float = Field(default=0.0, description="Grade points on the configured scale")
    term_bucket: str = Field(
        default="current",
        description="past, current, or future, relative to the student's term",
    )

    class Config:
        from_attributes = True
        # So `Course(average=...)` still works by field name alongside the alias.
        populate_by_name = True

class CourseDetail(Course):
    grades: List[Grade] =  Field(default_factory=list)
    # Point-weighted average per category, computed server-side so the client
    # renders one authoritative number instead of reimplementing the formula.
    # Defaults to empty so any path that does not populate it still serializes.
    category_averages: dict[GradeCategory, float] = Field(
        default_factory=dict,
        description="Current average per category, 0-100",
    )
    #: What each category contributes, in marks out of its weight. Sent rather
    #: than derived: deriving it meant multiplying the rounded average above by
    #: the weight, a second rounding that showed 11.82 for an exact 11.825.
    category_points: dict[GradeCategory, float] = Field(
        default_factory=dict,
        description="Marks each category contributes, out of its weight",
    )

    class Config:
        from_attributes = True
