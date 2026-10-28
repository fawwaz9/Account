"""Request and response bodies for repeating tasks: a rule plus a template.

Each occurrence is a real task row stamped from the template; `recurring_task_service`
writes them for a window from 14 days back to 60 days ahead.
"""

from datetime import date, datetime, time
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.schemas.event import Recurrence
from app.Grades.utils.enums import DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY
from app.Tasks.schemas.task import MAX_ESTIMATED_MINUTES, Task


class RecurringTaskBase(BaseModel):
    """Fields shared by a repeating task's create body and its response.

    Attributes:
        title: Title of every occurrence, 1-200 characters and not blank.
        notes: Notes copied to every occurrence, up to 2000 characters.
        due_time: Local time each occurrence is due; None means the end of the day.
        estimated_minutes: Effort per occurrence in minutes, 1-2400.
        course_id: The course it is school work for.
        tags: Labels copied to every occurrence, at most 10, each up to 30
            characters; tidied as a task's are.
        priority: Priority of every occurrence, 1-5; defaults to 3.
        starts_on: First date of the series, which anchors the rule.
        recurrence: The repeat rule.
        active: False pauses the series, so no new occurrences are written.
    """

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
        """Check the title and the rule's end, and tidy the tags.

        Returns:
            The model, with `tags` trimmed and deduplicated.

        Raises:
            ValueError: If the title is blank, the rule's `until` is before
                `starts_on`, or a tag is longer than 30 characters.

        Note:
            This also runs whenever a stored rule is serialised as `RecurringTask`,
            so a row that breaks these rules makes its response fail.
        """
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
    """Request body for creating a repeating task: the fields of `RecurringTaskBase`."""

    pass


class RecurringTaskUpdate(BaseModel):
    """Request body for editing a repeating task; only the fields sent are changed.

    Outstanding occurrences take the new template, and dates the rule no longer
    produces are dropped from today on; ticked-off occurrences are never touched.

    Attributes:
        title: New title, 1-200 characters.
        notes: New notes, up to 2000 characters; null clears them.
        due_time: New local due time; null clears it.
        estimated_minutes: New estimate, 1-2400; null clears it.
        course_id: New course; null detaches the series from its course.
        tags: Replaces the tags whole, at most 10.
        priority: New priority, 1-5.
        starts_on: New first date of the series.
        recurrence: New repeat rule; null leaves the rule as it is.
        active: Pause (False) or resume (True) the series.
    """

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
    """A repeating task as the API returns it: the base fields plus these.

    Attributes:
        id: The rule's id.
        skipped_dates: Occurrences cancelled one at a time, ascending.
        created_at: When the rule was made, naive UTC.
        course_code: The course's code, for labelling without a course list.
        next_due_on: The first occurrence from the user's today that is not yet
            done; None when none falls in the next 60 days.
    """

    id: UUID = Field(default_factory=uuid4)
    skipped_dates: list[date] = Field(default_factory=list)
    created_at: datetime | None = None
    #: Denormalised so a list can be labelled by course without holding them all.
    course_code: str | None = None
    #: The next occurrence still outstanding, or null once the rule has run out.
    next_due_on: date | None = None

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class RecurringTaskRun(BaseModel):
    """Response body for writing out the repeating tasks that have come due.

    Attributes:
        created: How many occurrences this run wrote.
        tasks: The occurrences it wrote; empty when nothing was missing.
    """

    created: int = 0
    tasks: list[Task] = Field(default_factory=list)
