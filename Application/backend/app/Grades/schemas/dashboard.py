from uuid import UUID

from pydantic import BaseModel, Field


class CourseDashboardEntry(BaseModel):
    course_id: UUID
    course_code: str
    course_name: str
    average: float
    needed_final_score: float | None = None
    unfinished_categories: list[str] = Field(default_factory=list)


class UserGradeDashboard(BaseModel):
    total_courses: int
    #: Plain mean across courses, every course counting equally.
    overall_average: float
    #: Credit-weighted mean, so a 6-credit course counts double a 3-credit one.
    cumulative_average: float = 0.0
    best_course: CourseDashboardEntry | None = None
    weakest_course: CourseDashboardEntry | None = None
    courses_needing_final_score: list[CourseDashboardEntry] = Field(default_factory=list)
    unfinished_categories_by_course: dict[str, list[str]] = Field(default_factory=dict)

