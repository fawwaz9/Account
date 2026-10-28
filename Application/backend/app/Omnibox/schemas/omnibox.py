"""Bodies for the omnibox, which files one typed line as a task, an expense or a grade.

The client previews the line as the student types and then files the same text.
`omnibox_service` routes it (a score out of a maximum is a grade, an amount is
an expense, anything else a task) and files it through that module's service.
"""

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class OmniboxKind(str, Enum):
    """Which module a line is filed into: a task, an expense or a grade."""

    TASK = "task"
    EXPENSE = "expense"
    GRADE = "grade"


class OmniboxRequest(BaseModel):
    """Request body carrying the typed line.

    Attributes:
        text: The line, 1-300 characters.
    """

    text: str = Field(..., min_length=1, max_length=300)


class OmniboxPreview(BaseModel):
    """What one line was read as, and what filing it would do.

    Flat rather than one shape per kind: the client shows the fields that are set
    and ignores the rest.

    Attributes:
        text: The line exactly as typed.
        kind: Where it would be filed.
        summary: One sentence saying what filing will do.
        can_create: Whether it can be filed as it stands.
        reason: What to do about it, when it cannot.
        title: The task title, expense description or grade name.
        on_date: A task's due date, or an expense's date (today when the line
            names none).
        course_id: The user's course the typed code matched.
        course_code: That course's code.
        unmatched_course: A typed code that matched none, or several, of the
            user's courses; it is kept in the title.
        estimated_minutes: Task only: the duration the line names, 1-2400.
        amount: Expense only: the amount, in dollars.
        account_id: Expense only: the account named in the line, otherwise the
            first spending account.
        account_name: That account's name.
        category_id: Expense only: the category named in the line, or suggested.
        category_name: That category's name.
        category_suggested: True when the category was suggested rather than
            named.
        score: Grade only: the mark.
        max_score: Grade only: what it is out of.
        grade_category: Grade only: taken from a word in the title such as
            "midterm"; "other" when none matches.
        matched: Which kinds of token the parser recognised, for debugging.
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
    """Response body for filing a line: what was created and where.

    Attributes:
        kind: Where it was filed.
        id: The created row: the task, the transaction or the grade.
        course_id: The course a grade (or a task) landed on, for linking.
        summary: The preview's summary.
        preview: The reading it was filed from.
    """

    kind: OmniboxKind
    #: The row that was created.
    id: UUID
    #: Set for a grade, so the client can link to the course page it landed on.
    course_id: UUID | None = None
    summary: str
    preview: OmniboxPreview
