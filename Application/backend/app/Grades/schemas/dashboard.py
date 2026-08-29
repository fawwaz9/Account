from uuid import UUID

from pydantic import BaseModel, Field


class CourseDashboardEntry(BaseModel):
    course_id: UUID
    course_code: str
    course_name: str
    average: float
    needed_final_score: float | None = None
    unfinished_categories: list[str] = Field(default_factory=list)


class YearSummary(BaseModel):
    """One school year's worth of courses, for the past/future sections."""

    school_year: int
    #: None when no course that year has anything recorded.
    average: float | None = None
    course_count: int = 0


class UserGradeDashboard(BaseModel):
    total_courses: int
    #: Plain mean across courses, every course counting equally.
    overall_average: float
    #: Credit-weighted mean, so a 6-credit course counts double a 3-credit one.
    cumulative_average: float = 0.0
    #: Plain mean across the current term's courses only.
    semester_average: float = 0.0
    #: Credit-weighted grade points. None when the GPA scale is switched off.
    cgpa: float | None = None
    credits_completed: float = 0.0
    credits_in_progress: float = 0.0
    credit_target: int = 120
    best_course: CourseDashboardEntry | None = None
    weakest_course: CourseDashboardEntry | None = None
    courses_needing_final_score: list[CourseDashboardEntry] = Field(default_factory=list)
    unfinished_categories_by_course: dict[str, list[str]] = Field(default_factory=dict)
    past_years: list[YearSummary] = Field(default_factory=list)
    future_years: list[YearSummary] = Field(default_factory=list)

