"""Alternative grading schemes and their comparison (Phase 1 item 4, vision §7)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import GradeCategory
from app.shared.errors import MAX_TOTAL_WEIGHT


class SchemeComponent(BaseModel):
    category: GradeCategory
    weight: float = Field(..., ge=0, le=100)
    #: Leave out this many of the category's lowest marks ("best 3 of 4 quizzes").
    #: The category always keeps at least one mark.
    drop_lowest: int = Field(default=0, ge=0, le=20)
    #: If this category's average is higher, it stands in for this one
    #: ("the final replaces the midterm if higher").
    replace_with: GradeCategory | None = None


class SchemeWrite(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    components: list[SchemeComponent] = Field(..., min_length=1, max_length=len(GradeCategory))

    @model_validator(mode="after")
    def _valid(self):
        seen = [c.category for c in self.components]
        if len(seen) != len(set(seen)):
            raise ValueError("Each category can appear once in a scheme")
        if sum(c.weight for c in self.components) > MAX_TOTAL_WEIGHT:
            raise ValueError(f"A scheme's weights cannot add up to more than {MAX_TOTAL_WEIGHT:g}%")
        for c in self.components:
            if c.replace_with == c.category:
                raise ValueError(f"{c.category.value} cannot replace itself")
        return self


class GradingScheme(SchemeWrite):
    id: UUID
    course_id: UUID
    created_at: datetime


class SchemeLine(BaseModel):
    """One category's part in a scheme's figure: the working, shown."""

    category: GradeCategory
    weight: float
    #: The category's average after this scheme's rules; null with nothing marked.
    average: float | None = None
    dropped: int = 0
    #: The category whose higher average replaced this one's, if any.
    replaced_by: GradeCategory | None = None


class SchemeResult(BaseModel):
    #: Null for the course's own weights.
    id: UUID | None = None
    label: str
    #: The course average under this scheme, on the same rules as the course's
    #: own: graded categories only, bonus added on top, capped at 100.
    average: float
    lines: list[SchemeLine] = Field(default_factory=list)
    #: The scheme as written, rules included -- what an editor starts from. The
    #: lines say what the rules did to the marks so far, which can be less.
    components: list[SchemeComponent] = Field(default_factory=list)


class SchemeComparison(BaseModel):
    current: SchemeResult
    schemes: list[SchemeResult] = Field(default_factory=list)
    #: The scheme with the highest average, when one beats the course's own.
    best_id: UUID | None = None
