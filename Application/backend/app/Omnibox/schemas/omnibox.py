from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class OmniboxKind(str, Enum):
    """Which module one line belongs to."""

    TASK = "task"
    EXPENSE = "expense"
    GRADE = "grade"


class OmniboxRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)


class OmniboxPreview(BaseModel):
    """What one line was read as, and what filing it would do.

    Flat rather than a union per kind. The client renders the fields that are
    set as chips and ignores the rest, which is simpler than switching on a
    discriminator to draw four nearly identical rows -- and it matches how a
    Transaction already carries fields only some kinds use.
    """

    text: str
    kind: OmniboxKind
    #: One sentence saying what will happen, so the reader never has to infer it
    #: from which chips appear.
    summary: str
    can_create: bool = False
    #: Why not, when it cannot. Always phrased as something to do about it.
    reason: str | None = None

    #: Common to every kind.
    title: str = ""
    on_date: date | None = None
    course_id: UUID | None = None
    course_code: str | None = None
    #: A code was typed that matches no course of yours, or matches several.
    unmatched_course: str | None = None

    #: Task only.
    estimated_minutes: int | None = None

    #: Expense only.
    amount: float | None = None
    account_id: UUID | None = None
    account_name: str | None = None
    category_id: UUID | None = None
    category_name: str | None = None
    #: True when the line named no category and one was suggested from your own
    #: past choices or a curated rule (Phase 1 items 6 and 8). The summary says so.
    category_suggested: bool = False

    #: Grade only.
    score: float | None = None
    max_score: float | None = None
    grade_category: str | None = None

    #: Which kinds the parser recognised, for anyone debugging a bad reading.
    matched: list[str] = Field(default_factory=list)


class OmniboxResult(BaseModel):
    """What was filed, and where to find it."""

    kind: OmniboxKind
    #: The row that was created.
    id: UUID
    #: Set for a grade, so the client can link to the course page it landed on.
    course_id: UUID | None = None
    summary: str
    preview: OmniboxPreview
