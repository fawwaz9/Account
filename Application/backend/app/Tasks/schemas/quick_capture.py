from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.Tasks.schemas.task import Task


class QuickCaptureRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)


class QuickCapturePreview(BaseModel):
    """What one line was understood to mean, before anything is written.

    Sent back as the student types so the guess is visible while it is still
    cheap to reword. A capture box that silently files things wrongly is worse
    than a form, because nothing on screen says what it did.
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
    """The task that was created, and the reading it came from."""

    task: Task
    preview: QuickCapturePreview
