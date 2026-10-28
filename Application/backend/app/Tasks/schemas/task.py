"""Request and response bodies for tasks, snoozes, timers and the estimate ratio.

A task is something to do, with or without a due date; a dated one also shows on
the calendar. `task_service` and `estimates_service` build these.
"""

from datetime import date, datetime, time
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY

#: A day is 1440 minutes; nothing you can sit down and do is longer than a
#: working week, and a figure past that is a slipped digit rather than a plan.
MAX_ESTIMATED_MINUTES = 2400


class TaskBase(BaseModel):
    """Fields shared by a task's create body and its response.

    Attributes:
        title: What to do, 1-200 characters and not blank; the service strips it.
        notes: Free text, up to 2000 characters.
        due_date: When it is due; None for an undated task.
        due_time: Local time of day it is due, which needs a `due_date`; None
            means the end of the day.
        estimated_minutes: Expected effort in minutes, 1-2400.
        course_id: The course it is school work for; the course code then serves
            as its category.
        tags: Free-text labels, at most 10, each up to 30 characters; trimmed,
            with blanks and case-insensitive duplicates dropped.
        priority: 1 (lowest) to 5 (highest); defaults to 3.
    """

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
        """Check the title and the date-time pair, and tidy the tags.

        Returns:
            The model, with `tags` trimmed and deduplicated.

        Raises:
            ValueError: If the title is blank, `due_time` is set without `due_date`,
                or a tag is longer than 30 characters.

        Note:
            This also runs whenever a stored row is serialised as `Task`, so a row
            that breaks these rules makes its response fail.
        """
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
    """Request body for creating a task: the fields of `TaskBase`."""

    pass


class SnoozeRequest(BaseModel):
    """Request body for snoozing a task: hide it until a date, and say why.

    The due date never moves; each snooze is kept as history.

    Attributes:
        until: The date the task reappears; must be after the user's today.
        reason: Why it was put off, up to 200 characters; blank becomes None.
    """

    until: date
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_snooze(self):
        """Treat a blank reason as no reason.

        Returns:
            The model, with a whitespace-only `reason` replaced by None.
        """
        if self.reason is not None and self.reason.strip() == "":
            self.reason = None
        return self


class TaskSnooze(BaseModel):
    """One time a task was snoozed, as recorded.

    Attributes:
        id: The snooze record's id.
        snoozed_at: When the snooze was made, naive UTC.
        until: The date the task was hidden until.
        reason: The reason given; None when none was.
    """

    id: UUID = Field(default_factory=uuid4)
    snoozed_at: datetime
    until: date
    reason: str | None = None

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class TaskUpdate(BaseModel):
    """Request body for editing a task; only the fields sent are changed.

    Attributes:
        title: New title, 1-200 characters; the service strips it.
        notes: New notes, up to 2000 characters; null clears them.
        due_date: New due date; null makes the task undated, which is refused
            while a `due_time` remains.
        due_time: New local due time; null clears it.
        estimated_minutes: New estimate, 1-2400; null clears it.
        course_id: New course; null detaches the task from its course.
        tags: Replaces the tags whole, at most 10.
        priority: New priority, 1-5.
        done: True ticks the task off (stamps `completed_at`, stops a running
            timer and archives it); False unticks and unarchives it.
        archived: Archive or unarchive without changing `done`.
        actual_minutes: How long it really took, 1-2400; null clears it.
    """

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
    """A task as the API returns it: the `TaskBase` fields plus these.

    Attributes:
        id: The task's id.
        done: Whether it is ticked off.
        completed_at: When it was ticked off, naive UTC; None while open.
        archived: Whether it is archived; ticking a task off archives it.
        created_at: When it was made, naive UTC.
        actual_minutes: How long it really took; None when not recorded.
        timer_started_at: When the running timer started, naive UTC; None when no
            timer runs.
        grade_id: The dated grade that raised it; the task closes when that grade
            is marked, so the client offers no delete.
        recurring_id: The repeating task this occurrence came from, if any.
        course_code: The course's code, for labelling without a course list.
        risk: "mild", "moderate" or "severe" when its course is below target this
            term; None otherwise. Computed on list reads only; single-task
            responses carry None.
        snoozed_until: Hidden from the list until this date; the due date is
            unaffected.
        snooze_count: How many times it has been snoozed.
        last_snooze_reason: The latest snooze's reason.
        shared_with: Names of the people it is shared with, in joining order;
            empty when it is private.
    """

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
    #: The names of the people you have shared it with (Phase 2 D23). Empty
    #: when it is yours alone.
    shared_with: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class TimerStop(BaseModel):
    """Response body for stopping a task's timer.

    Attributes:
        task: The task after the stop.
        added_minutes: Minutes added to `actual_minutes`; 0 when nothing was
            recorded.
        discarded: True when the timer had run for more than 12 hours, or its
            start was in the future, so nothing was recorded.
    """

    task: Task
    #: Minutes the stop added to `actual_minutes`; 0 when it recorded nothing.
    added_minutes: int = 0
    #: True when the timer had run too long to trust, so nothing was recorded.
    discarded: bool = False


class EstimateRatio(BaseModel):
    """How long the user's tasks really take compared with their estimates.

    Attributes:
        ratio: Total actual minutes over total estimated, across tasks finished
            in the last 90 days with both figures; None until `needed` such tasks
            exist.
        tasks: Finished tasks in the window with both figures.
        needed: How many such tasks a ratio requires.
        estimated_minutes: Their estimates, summed.
        actual_minutes: Their actual times, summed.
        applied: True when a ratio exists and the user chose to have the workload
            forecast scaled by it.
    """

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
