"""Schemas for end-of-term reviews of finished courses."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TermReviewIn(BaseModel):
    """Request body for answering a term review; every answer is optional.

    Attributes:
        hours_per_week: Typical weekly hours, 0-80.
        difficulty: Rating 1-5.
        clarity: Rating 1-5.
        would_take_again: Yes or no; None for no answer.
        contribute_grade: Opt in to adding the course's grade to its distribution.
    """

    hours_per_week: int | None = Field(default=None, ge=0, le=80)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    clarity: int | None = Field(default=None, ge=1, le=5)
    would_take_again: bool | None = None
    contribute_grade: bool = False


class TermReview(TermReviewIn):
    """A saved term review as the API returns it.

    Attributes:
        skipped: Whether the student declined the review.
        created_at: When it was first saved (naive UTC).
        answers_editable: False once the answers have locked; the contribution stays
            changeable.
    """
    skipped: bool = False
    created_at: datetime
    #: False once the answers have locked. The contribution stays changeable.
    answers_editable: bool


class ReviewCourse(BaseModel):
    """A finished course in its review window, and the student's review of it if any.

    Attributes:
        course_id: The course.
        code: Its code.
        name: Its title.
        term_label: The term, such as "Fall 2025".
        has_grade: Whether there is a grade to contribute.
        can_contribute: Whether the course can be counted at all: its code reads as a
            course and its term's dates are known.
        review: The review, or None if not answered yet.
    """

    course_id: UUID
    code: str
    name: str
    #: "Fall 2025".
    term_label: str
    #: Whether there is a grade to contribute.
    has_grade: bool
    #: Whether this course can be counted at all: its code reads as a course
    #: and its term's dates are known.
    can_contribute: bool
    review: TermReview | None = None


class TermReviews(BaseModel):
    """The courses awaiting or holding a term review.

    Attributes:
        courses: Each course in its review window.
        pending: Finished courses not yet answered or skipped.
    """
    courses: list[ReviewCourse]
    #: Finished courses not yet answered or skipped.
    pending: int
