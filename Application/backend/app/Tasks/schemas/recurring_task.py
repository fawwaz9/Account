from datetime import date, datetime, time
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.schemas.event import Recurrence
from app.Grades.utils.enums import DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY
from app.Tasks.schemas.task import MAX_ESTIMATED_MINUTES, Task


class RecurringTaskBase(BaseModel):
    """A chore that comes back, and the template each occurrence is stamped from."""

    title: str = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_time: time | None = None
    estimated_minutes: int | None = Field(
        default=None, ge=1, le=MAX_ESTIMATED_MINUTES,
        description="Applied to every occurrence, so a repeating chore counts toward a week's hours",
    )
    course_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    priority: int = Field(default=DEFAULT_PRIORITY, ge=MIN_PRIORITY, le=MAX_PRIORITY)
    starts_on: date
    recurrence: Recurrence
    active: bool = True

    @model_validator(mode="after")
    def validate_repeating_task(self):
        if self.title.strip() == "":
            raise ValueError("A task needs a title")

        if self.recurrence.until is not None and self.recurrence.until < self.starts_on:
            raise ValueError("A repeat cannot end before it starts")

        cleaned = []
        for tag in self.tags:
            tag = tag.strip()
            if not tag:
                continue
            if len(tag) > 30:
                raise ValueError("A tag cannot be longer than 30 characters")
            if tag.lower() not in {existing.lower() for existing in cleaned}:
                cleaned.append(tag)

        self.tags = cleaned
        return self


class RecurringTaskCreate(RecurringTaskBase):
    pass


class RecurringTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_time: time | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=MAX_ESTIMATED_MINUTES)
    course_id: UUID | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    priority: int | None = Field(default=None, ge=MIN_PRIORITY, le=MAX_PRIORITY)
    starts_on: date | None = None
    recurrence: Recurrence | None = None
    active: bool | None = None


class RecurringTask(RecurringTaskBase):
    id: UUID = Field(default_factory=uuid4)
    skipped_dates: list[date] = Field(default_factory=list)
    created_at: datetime | None = None
    #: Denormalised so a list can be labelled by course without holding them all.
    course_code: str | None = None
    #: The next occurrence still outstanding, or null once the rule has run out.
    next_due_on: date | None = None

    class Config:
        from_attributes = True


class RecurringTaskRun(BaseModel):
    """What materialising the window actually created."""

    created: int = 0
    tasks: list[Task] = Field(default_factory=list)
