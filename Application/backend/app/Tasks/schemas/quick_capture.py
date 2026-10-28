"""Request and response bodies for quick capture: one typed line turned into a task.

The client previews the line as the student types and then submits the same
text; `quick_capture_service` parses it with the shared tokenizer and matches
any course code against the user's own courses.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.Tasks.schemas.task import Task


class QuickCaptureRequest(BaseModel):
    """Request body carrying the line to turn into a task.

    Attributes:
        text: The typed line, 1-300 characters.
    """

    text: str = Field(..., min_length=1, max_length=300)


class QuickCapturePreview(BaseModel):
    """What one typed line would create, worked out before anything is written.

    Attributes:
        text: The line exactly as typed.
        title: What remains once recognised tokens are taken out; it becomes the
            task's title. An unmatched course code stays in it.
        due_date: The date the line names, read against the user's today; None
            when it names none.
        estimated_minutes: The duration the line names, 1-2400; None when absent
            or out of range.
        course_id: The user's course the typed code matched; None without a
            single match.
        course_code: That course's code.
        unmatched_course: A typed code that matched none, or several, of the
            user's courses.
        matched: Which kinds of token were recognised: course, date, duration,
            amount, score.
        can_create: False when nothing is left to be a title, so the client can
            keep submit disabled.
    """

    #: Exactly what was typed, so the client can always fall back to it.
    text: str
    #: What is left after every token was taken out. This becomes the task.
    title: str
    due_date: date | None = None
    estimated_minutes: int | None = None
    #: The course this was matched to, if a real one matched.
    course_id: UUID | None = None
    course_code: str | None = None
    #: A code was typed but matches no course of yours -- or matches several.
    #: The code stays in the title in that case rather than being swallowed.
    unmatched_course: str | None = None
    #: Which kinds the parser recognised: course, date, duration, amount, score.
    matched: list[str] = Field(default_factory=list)
    #: False when there is nothing left to call a task, so the client can keep
    #: the submit button disabled rather than letting the server refuse.
    can_create: bool = False


class QuickCaptureResult(BaseModel):
    """Response body for a capture: the task created and the reading behind it.

    Attributes:
        task: The new task.
        preview: The reading it was created from.
    """

    task: Task
    preview: QuickCapturePreview
