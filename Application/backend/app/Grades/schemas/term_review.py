"""End-of-term reviews (Phase 2 item 13, D25)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TermReviewIn(BaseModel):
    """Four questions and one opt-in. Every answer is optional."""

    hours_per_week: int | None = Field(default=None, ge=0, le=80)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    clarity: int | None = Field(default=None, ge=1, le=5)
    would_take_again: bool | None = None
    contribute_grade: bool = False


class TermReview(TermReviewIn):
    skipped: bool = False
    created_at: datetime
    #: False once the answers have locked. The contribution stays changeable.
    answers_editable: bool


class ReviewCourse(BaseModel):
    """A finished course in its asking window, and your review of it, if any."""

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
    courses: list[ReviewCourse]
    #: Finished courses not yet answered or skipped.
    pending: int
