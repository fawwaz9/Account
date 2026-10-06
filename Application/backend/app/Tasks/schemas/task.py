from datetime import date, datetime, time
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY

#: A day is 1440 minutes; nothing you can sit down and do is longer than a
#: working week, and a figure past that is a slipped digit rather than a plan.
MAX_ESTIMATED_MINUTES = 2400


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    #: Optional, because a task with no date is still a task. One *with* a date
    #: also appears on the calendar.
    due_date: date | None = None
    due_time: time | None = None
    estimated_minutes: int | None = Field(
        default=None, ge=1, le=MAX_ESTIMATED_MINUTES,
        description="What you think it will take, so a week's load is a number of hours",
    )
    course_id: UUID | None = Field(
        default=None, description="School work; its course code is then its category"
    )
    tags: list[str] = Field(default_factory=list, max_length=10)
    priority: int = Field(
        default=DEFAULT_PRIORITY, ge=MIN_PRIORITY, le=MAX_PRIORITY,
        description="1 to 5, 5 being the most important",
    )

    @model_validator(mode="after")
    def validate_task(self):
        if self.title.strip() == "":
            raise ValueError("A task needs a title")

        if self.due_time is not None and self.due_date is None:
            raise ValueError("A time of day needs a date to go with it")

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


class TaskCreate(TaskBase):
    pass


class SnoozeRequest(BaseModel):
    """Push a task out of the way, and say why.

    The reason is the point of the feature rather than a nicety: a task snoozed
    three times for the same reason is a blocked task, and nothing else in the
    app would ever say so.
    """

    until: date
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_snooze(self):
        if self.reason is not None and self.reason.strip() == "":
            self.reason = None
        return self


class TaskSnooze(BaseModel):
    """One time a task was pushed back."""

    id: UUID = Field(default_factory=uuid4)
    snoozed_at: datetime
    until: date
    reason: str | None = None

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    due_time: time | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=MAX_ESTIMATED_MINUTES)
    course_id: UUID | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    priority: int | None = Field(default=None, ge=MIN_PRIORITY, le=MAX_PRIORITY)
    #: Checking a task sets `completed_at`; unchecking clears it.
    done: bool | None = None
    archived: bool | None = None
    #: How long it actually took (Phase 1 D35). Null clears it.
    actual_minutes: int | None = Field(default=None, ge=1, le=MAX_ESTIMATED_MINUTES)


class Task(TaskBase):
    id: UUID = Field(default_factory=uuid4)
    done: bool = False
    completed_at: datetime | None = None
    archived: bool = False
    created_at: datetime | None = None
    #: Phase 1 D35: what it actually took, and when a running timer started
    #: (UTC, null when none runs).
    actual_minutes: int | None = None
    timer_started_at: datetime | None = None
    #: Set when this task was raised from a dated grade. It closes itself when
    #: that grade's score lands -- and only ever in that direction, since
    #: finishing the work and having it marked are different facts. The client
    #: hides the delete control so the two cannot drift apart.
    grade_id: UUID | None = None
    #: Set when a repeating task produced this occurrence. Sent so the editor
    #: can say that a change lands on this one day and that editing the repeat
    #: itself will write over it -- a distinction the student cannot otherwise
    #: see, since an occurrence is an ordinary task row in every other respect.
    recurring_id: UUID | None = None
    #: Denormalised, so a list of tasks can be labelled by course without the
    #: client holding every course to look them up.
    course_code: str | None = None
    #: How far behind the course this task belongs to is: "mild", "moderate" or
    #: "severe", and null when there is nothing to flag. Computed here rather
    #: than in the client, which would otherwise need every course, every target
    #: and the current-term rule just to colour a row.
    risk: str | None = None
    #: Hidden from the list until this date. The due date is unaffected.
    snoozed_until: date | None = None
    #: How many times this has been pushed back. The count rather than the rows,
    #: because a list of tasks does not need a term of history in it.
    snooze_count: int = 0
    #: Why it was last pushed back, so a blocked task says so on its own row.
    last_snooze_reason: str | None = None

    class Config:
        from_attributes = True


class TimerStop(BaseModel):
    """What stopping a timer did."""

    task: Task
    #: Minutes the stop added to `actual_minutes`; 0 when it recorded nothing.
    added_minutes: int = 0
    #: True when the timer had run too long to trust, so nothing was recorded.
    discarded: bool = False


class EstimateRatio(BaseModel):
    """How long tasks really take against what was estimated (Phase 1 D36)."""

    #: Total actual over total estimated; null until enough tasks have both.
    ratio: float | None = None
    #: Completed tasks in the window with both numbers.
    tasks: int = 0
    #: How many are needed before a ratio is shown.
    needed: int
    estimated_minutes: int = 0
    actual_minutes: int = 0
    #: Whether the workload forecast is using it.
    applied: bool = False
