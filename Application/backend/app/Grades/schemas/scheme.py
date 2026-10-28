"""Schemas for alternative grading schemes and their comparison."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import GradeCategory
from app.shared.errors import MAX_TOTAL_WEIGHT


class SchemeComponent(BaseModel):
    """One category's part in a grading scheme.

    Attributes:
        category: The grade category.
        weight: Its weight, 0-100.
        drop_lowest: How many of its lowest marks to leave out, 0-20; at least one
            mark is always kept.
        replace_with: A category whose higher average stands in for this one, such as
            the final replacing the midterm; None for no replacement.
    """
    category: GradeCategory
    weight: float = Field(..., ge=0, le=100)
    #: Leave out this many of the category's lowest marks ("best 3 of 4 quizzes").
    #: The category always keeps at least one mark.
    drop_lowest: int = Field(default=0, ge=0, le=20)
    #: If this category's average is higher, it stands in for this one
    #: ("the final replaces the midterm if higher").
    replace_with: GradeCategory | None = None


class SchemeWrite(BaseModel):
    """Request body for creating or replacing a grading scheme.

    Attributes:
        label: Scheme name, 1-60 characters.
        components: One component per category, each category at most once.
    """
    label: str = Field(..., min_length=1, max_length=60)
    components: list[SchemeComponent] = Field(..., min_length=1, max_length=len(GradeCategory))

    @model_validator(mode="after")
    def _valid(self):
        """Check categories are unique, weights total at most 200, no self-replacement.

        Raises:
            ValueError: If any rule is broken (a 422).
        """
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
    """A stored grading scheme as the API returns it.

    Attributes:
        id: The scheme's id.
        course_id: The course it belongs to.
        created_at: When it was created (naive UTC).
    """
    id: UUID
    course_id: UUID
    created_at: datetime


class SchemeLine(BaseModel):
    """One category's working in a scheme's figure.

    Attributes:
        category: The grade category.
        weight: Its weight in the scheme.
        average: The category's average after the scheme's rules; null with nothing
            marked.
        dropped: How many lowest marks were dropped.
        replaced_by: The category whose higher average replaced this one, or None.
    """

    category: GradeCategory
    weight: float
    #: The category's average after this scheme's rules; null with nothing marked.
    average: float | None = None
    dropped: int = 0
    #: The category whose higher average replaced this one's, if any.
    replaced_by: GradeCategory | None = None


class SchemeResult(BaseModel):
    """The course average under one scheme, with the working.

    Attributes:
        id: The scheme's id; None for the course's own weights.
        label: The scheme's name.
        average: The course average under it: marked categories only, bonus on top,
            capped at 100.
        lines: The working per category.
        components: The scheme as written, which an editor starts from.
    """
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
    """The course's own figure beside every scheme's.

    Attributes:
        current: The course's own weights.
        schemes: Each scheme's result.
        best_id: The scheme with the highest average, when it beats the course's own.
        counting_id: The scheme picked as the course's grade; null when the course's
            own weights are the grade.
    """
    current: SchemeResult
    schemes: list[SchemeResult] = Field(default_factory=list)
    #: The scheme with the highest average, when one beats the course's own.
    best_id: UUID | None = None
    #: The scheme picked as the course's grade (Phase 1 D25); null when the
    #: course's own weights are the grade.
    counting_id: UUID | None = None


class CountingScheme(BaseModel):
    """Request body choosing which scheme is the course's grade.

    Attributes:
        scheme_id: The scheme to count; null puts the course's own weights back.
    """

    scheme_id: UUID | None = None
