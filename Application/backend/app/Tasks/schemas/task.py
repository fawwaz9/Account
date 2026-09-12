from datetime import date, datetime, time
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

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


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    due_time: time | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=MAX_ESTIMATED_MINUTES)
    course_id: UUID | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    #: Checking a task sets `completed_at`; unchecking clears it.
    done: bool | None = None
    archived: bool | None = None


class Task(TaskBase):
    id: UUID = Field(default_factory=uuid4)
    done: bool = False
    completed_at: datetime | None = None
    archived: bool = False
    created_at: datetime | None = None
    #: Set when this task was raised from a dated grade. It closes itself when
    #: that grade's score lands, and the client hides the delete control so the
    #: two cannot drift apart.
    grade_id: UUID | None = None
    #: Denormalised, so a list of tasks can be labelled by course without the
    #: client holding every course to look them up.
    course_code: str | None = None
    #: How far behind the course this task belongs to is: "mild", "moderate" or
    #: "severe", and null when there is nothing to flag. Computed here rather
    #: than in the client, which would otherwise need every course, every target
    #: and the current-term rule just to colour a row.
    risk: str | None = None

    class Config:
        from_attributes = True
