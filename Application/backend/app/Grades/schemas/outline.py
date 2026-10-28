"""Schemas for course outlines shared between students (Phase 3 item 2, D12)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.Grades.utils.enums import GradeCategory

#: The most assessments one outline carries.
MAX_ASSESSMENTS = 60


class OutlineAssessment(BaseModel):
    """One assessment in an outline: what it is called, its category and when it's due.

    Attributes:
        name: Its name, such as "Midterm 1", 1-100 characters.
        category: Its grade category.
        due_date: When it's due in that term; None when the outline doesn't say.
    """

    name: str = Field(..., min_length=1, max_length=100)
    category: GradeCategory
    due_date: date | None = None


class Outline(BaseModel):
    """A course's structure as shared: its weights and assessments, never a score or note.

    Attributes:
        weights: Category to weight percentage, only categories above 0.
        assessments: At most 60, by due date then name.
    """

    weights: dict[GradeCategory, float]
    assessments: list[OutlineAssessment] = Field(default_factory=list, max_length=MAX_ASSESSMENTS)


class OutlineOffer(BaseModel):
    """Where the caller's own offer of this course's outline stands.

    Attributes:
        status: "pending", "accepted" or "rejected".
        created_at: When it was offered (naive UTC).
    """

    status: Literal["pending", "accepted", "rejected"]
    created_at: datetime


class SharedOutline(BaseModel):
    """A reviewed outline for the caller's course and term.

    Attributes:
        outline: The weights and assessments.
        approved_at: When it was approved (naive UTC).
    """

    outline: Outline
    approved_at: datetime


class OutlineStatus(BaseModel):
    """What the caller can do with outlines on one of their courses.

    Attributes:
        course_key: The key it would be shared under; None when its code isn't a
            course code.
        term_code: The term, such as "2026W1"; None without the first-year setting.
        can_offer: Whether this course's outline can be offered now.
        offer_blocked: Why not, when it can't; None when it can.
        offer: The caller's own offer, if any.
        shared: A reviewed outline for this course and term, if one exists.
        can_apply: Whether `shared` can fill this course: it has no grades yet.
    """

    course_key: str | None
    term_code: str | None
    can_offer: bool
    offer_blocked: str | None = None
    offer: OutlineOffer | None = None
    shared: SharedOutline | None = None
    can_apply: bool = False
