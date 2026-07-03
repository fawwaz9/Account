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
    overall_average: float
    best_course: CourseDashboardEntry | None = None
    weakest_course: CourseDashboardEntry | None = None
    courses_needing_final_score: list[CourseDashboardEntry] = Field(default_factory=list)
    unfinished_categories_by_course: dict[str, list[str]] = Field(default_factory=dict)

