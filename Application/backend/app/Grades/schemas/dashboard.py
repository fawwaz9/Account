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


class TermPoint(BaseModel):
    """One term on the grade trend: how it went, and where it left the total."""

    school_year: int
    semester: str
    label: str
    #: Plain mean across the term's courses, matching how a term average reads.
    term_average: float
    #: Credit-weighted cumulative up to and including this term. None until
    #: some course has a final grade -- an in-progress term leaves the
    #: cumulative undefined rather than zero.
    cumulative_average: float | None = None


class AttentionItem(BaseModel):
    """Something worth acting on, surfaced on the grades page."""

    #: missing_final | below_target | weight_problem
    kind: str
    course_id: UUID
    course_code: str
    message: str


class UserGradeDashboard(BaseModel):
    total_courses: int
    #: Credit-weighted mean, so a 6-credit course counts double a 3-credit one.
    #: The plain mean that used to sit beside this was removed with the tile that
    #: rendered it -- it counted a 1-credit elective the same as a 6-credit course.
    cumulative_average: float = 0.0
    #: Plain mean across the current term's courses only.
    semester_average: float = 0.0
    #: Credit-weighted grade points. None when the GPA scale is switched off.
    cgpa: float | None = None
    credits_completed: float = 0.0
    credits_in_progress: float = 0.0
    #: Completed credits split by the course's required flag.
    credits_required: float = 0.0
    credits_elective: float = 0.0
    credit_target: int = 120
    best_course: CourseDashboardEntry | None = None
    weakest_course: CourseDashboardEntry | None = None
    courses_needing_final_score: list[CourseDashboardEntry] = Field(default_factory=list)
    unfinished_categories_by_course: dict[str, list[str]] = Field(default_factory=dict)
    attention: list[AttentionItem] = Field(default_factory=list)
    term_history: list[TermPoint] = Field(default_factory=list)
    past_years: list[YearSummary] = Field(default_factory=list)
    future_years: list[YearSummary] = Field(default_factory=list)

