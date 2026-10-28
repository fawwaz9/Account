"""Response schema for blind spots: categories a student is weaker at across courses."""

from typing import Literal

from pydantic import BaseModel, Field

#: How far a category's average has to sit below the student's own overall
#: average, in percentage points, before it is worth naming -- and how far
#: before the tone changes. Same three tiers as the risk badge on the tasks
#: page (0-5 mild, 5-10 moderate, over 10 severe), so a student who already
#: reads one badge does not have to learn a second scale for this one.
BLIND_SPOT_BANDS: dict[str, tuple[float, float]] = {
    "mild": (2.0, 5.0),
    "moderate": (5.0, 10.0),
    "severe": (10.0, float("inf")),
}

#: A dip has to show up in at least this many different courses to be a blind
#: spot. One course's weak labs is that course's problem; the whole point of
#: this feature is the pattern that only shows up once courses are compared.
MIN_COURSES = 2


class CategoryBlindSpot(BaseModel):
    """A category that trails the student's own overall average in several courses.

    Computed on every read by pooling every marked item, so nothing is stored or kept in
    step.

    Attributes:
        category: Grade category name.
        average: Pooled percentage over every marked item in the category.
        overall_average: The same pooling over every marked item in every category.
        gap: `overall_average - average` in percentage points; always positive.
        severity: "mild", "moderate" or "severe", by `BLIND_SPOT_BANDS`.
        course_count: Courses the category's dip appears in, at least `MIN_COURSES`.
        item_count: Marked items pooled.
        course_codes: Codes of the courses involved.
    """

    category: str
    #: Pooled percentage across every marked item in this category.
    average: float
    #: The same pooling done across every marked item in every category.
    overall_average: float
    #: overall_average - average. Positive by construction -- a category ahead
    #: of the average is not a blind spot and never appears here.
    gap: float
    severity: Literal["mild", "moderate", "severe"]
    course_count: int
    item_count: int
    course_codes: list[str] = Field(default_factory=list)
