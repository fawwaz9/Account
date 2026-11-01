"""Response bodies for the course-drop simulator (Phase 4 item 11, §13.6).

Before and after figures for dropping one course this term, the full-time check
and a refund ceiling. Information with disclaimers, never advice (§15).
"""

from uuid import UUID

from pydantic import BaseModel, Field

#: The full-time threshold when none is given: credits a term (D9).
DEFAULT_FULL_TIME_CREDITS = 9.0


class DropFigures(BaseModel):
    """The figures a drop moves, on one side of it.

    Attributes:
        semester_average: Plain mean of this term's results; None with none.
        cumulative_average: The official average, finished courses only.
        cgpa: The official CGPA; None when the GPA scale is off or nothing has a final.
        cumulative_average_including_term: With this term's running averages (D5).
        cgpa_including_term: The CGPA on the same courses.
        term_credits: Credits taken this term, archived and transfer credit left out.
    """
    semester_average: float | None = None
    cumulative_average: float = 0.0
    cgpa: float | None = None
    cumulative_average_including_term: float | None = None
    cgpa_including_term: float | None = None
    term_credits: float = 0.0


class DropPreview(BaseModel):
    """What dropping one course this term changes.

    Attributes:
        course_id: The course.
        course_code: Its code.
        credits: Its credits.
        before: The figures as they stand.
        after: The figures without the course.
        full_time_credits: The threshold the check used.
        below_full_time: True when the term falls below it after the drop.
        was_full_time: True when the term was at or above it before.
        tuition_share: The course's gross tuition (credits times the term's recorded
            rate), the most a refund could return; None when no rate is recorded.
        warnings: What to check before deciding, most serious first.
        disclaimers: What this is not.
    """
    course_id: UUID
    course_code: str
    credits: float
    before: DropFigures
    after: DropFigures
    full_time_credits: float
    below_full_time: bool
    was_full_time: bool
    tuition_share: float | None = None
    warnings: list[str] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)
