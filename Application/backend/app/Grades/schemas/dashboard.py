"""Response schemas for the grades dashboard: averages, credits, trend and attention."""

from uuid import UUID

from pydantic import BaseModel, Field


class CourseDashboardEntry(BaseModel):
    """One course as the dashboard lists it.

    Attributes:
        course_id: The course.
        course_code: Its code.
        course_name: Its title.
        average: Current average; None when nothing is marked.
        needed_final_score: Score needed on the final to reach the target; None when not
            applicable.
        unfinished_categories: Weighted categories, final and bonus aside, with nothing
            marked yet.
    """
    course_id: UUID
    course_code: str
    course_name: str
    #: Null when the course has nothing marked. See Course.average.
    average: float | None = None
    needed_final_score: float | None = None
    unfinished_categories: list[str] = Field(default_factory=list)


class YearSummary(BaseModel):
    """One school year's courses, for the past and future sections.

    Attributes:
        school_year: The school year.
        average: Plain mean of the year's course grades; None when none is recorded.
        course_count: Courses in the year.
    """

    school_year: int
    #: None when no course that year has anything recorded.
    average: float | None = None
    course_count: int = 0


class TermPoint(BaseModel):
    """One term on the grade trend: its average and the cumulative it left.

    Attributes:
        school_year: The term's school year.
        semester: The term.
        label: Display label for the term.
        term_average: Plain mean across the term's courses.
        cumulative_average: Credit-weighted cumulative up to and including this term;
            None until some course has a final grade.
    """

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
    """Something on the grades page worth acting on.

    Attributes:
        kind: "missing_final", "below_target", "weight_problem" or "missing_section".
        course_id: The course concerned.
        course_code: Its code.
        message: What to do, in words.
    """

    #: missing_final | below_target | weight_problem | missing_section
    kind: str
    course_id: UUID
    course_code: str
    message: str


class UserGradeDashboard(BaseModel):
    """The grades dashboard for one student.

    Attributes:
        total_courses: Graded courses on the record; transfer credit is left out.
        cumulative_average: Credit-weighted mean over courses with a final grade.
        semester_average: Plain mean across the current term's courses.
        cgpa: Credit-weighted grade points; None when the GPA scale is off.
        credits_completed: Credits finished.
        credits_in_progress: Credits in the current term not yet finished.
        credits_required: Completed credits from required courses.
        credits_elective: Completed credits from electives.
        credit_target: Credits the degree needs; 120 by default.
        best_course: The graded course with the highest average, any term; None when
            nothing is marked.
        weakest_course: The course with the lowest average among those with marks; None
            when nothing is marked.
        courses_needing_final_score: Courses whose final still needs a positive score to
            reach the target.
        unfinished_categories_by_course: "CODE - Name" to that course's
            `unfinished_categories`, for courses that have any.
        attention: Things to act on, most actionable first.
        term_history: The grade trend, one point per term.
        past_years: Past school years, summarised.
        future_years: Future school years, summarised.
    """
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

