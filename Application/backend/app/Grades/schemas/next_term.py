"""Request and response bodies for the next-term planner (Phase 4 item 12, §13.6).

Candidate courses from the shared catalogue, with past students' figures above
the floor added up: "this combination is about 42 hours a week". Nothing stored.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.Grades.schemas.class_figures import CourseIntelOut

#: Candidate courses in one plan; more than a term holds.
MAX_CANDIDATES = 8


class NextTermIn(BaseModel):
    """The candidate courses.

    Attributes:
        catalogue_ids: Catalogue courses, 1 to `MAX_CANDIDATES`, no repeats.
    """
    catalogue_ids: list[UUID] = Field(..., min_length=1, max_length=MAX_CANDIDATES)


class NextTermCourse(BaseModel):
    """One candidate, with whatever past students' figures have reached the floor.

    Attributes:
        catalogue_id: The catalogue course.
        code: "CPSC 221".
        campus: "UBCV", "UBCO".
        title: Its title, if the catalogue has one.
        credits: Its credits, if known.
        intel: Hours, difficulty, clarity and "take again" above the floor; None when
            no figure has reached it.
    """
    catalogue_id: UUID
    code: str
    campus: str
    title: str | None = None
    credits: float | None = None
    intel: CourseIntelOut | None = None


class NextTermPlan(BaseModel):
    """The candidates added up.

    Attributes:
        courses: The candidates, in the order given.
        total_hours: Median weekly hours summed over the courses that have them; None
            when none does.
        courses_with_hours: How many courses that sum covers.
        total_credits: Credits summed where known.
        mean_difficulty: Mean of the difficulty figures present, 1-5; None with none.
        missing: Codes with no hours figure yet, which the sum leaves out.
        floor: People a figure needs before it shows.
        assumptions: What the figures are and aren't, in words.
    """
    courses: list[NextTermCourse] = Field(default_factory=list)
    total_hours: float | None = None
    courses_with_hours: int = 0
    total_credits: float = 0.0
    mean_difficulty: float | None = None
    missing: list[str] = Field(default_factory=list)
    floor: int
    assumptions: list[str] = Field(default_factory=list)
