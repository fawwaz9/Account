"""Request and response bodies for the weekly planner (Phase 4 item 2, §4, D7).

Constraint scheduling over free blocks: tasks sorted by due date and priority,
filled greedily, each choice explained. A proposal stores nothing; accepting it
writes ordinary calendar events marked as the planner's.
"""

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

#: Blocks one acceptance may write.
MAX_ACCEPTED = 60


class PlannedBlock(BaseModel):
    """A stretch of free time given to one task.

    Attributes:
        task_id: The task.
        title: Its title.
        course_code: Its course's code, if any.
        due_date: When it is due.
        on_date: The day of the block.
        starts_at: Local start.
        ends_at: Local end.
        minutes: Its length.
        reason: Why here, in words.
    """
    task_id: UUID
    title: str
    course_code: str | None = None
    due_date: date
    on_date: date
    starts_at: time
    ends_at: time
    minutes: int
    reason: str


class Unplaced(BaseModel):
    """A task that didn't fit before it is due.

    Attributes:
        task_id: The task.
        title: Its title.
        due_date: When it is due.
        minutes_needed: What it needed.
        minutes_short: What couldn't be placed.
        reason: Why, in words.
    """
    task_id: UUID
    title: str
    due_date: date
    minutes_needed: int
    minutes_short: int
    reason: str


class WeekPlan(BaseModel):
    """A proposed week.

    Attributes:
        starts_on: The first day planned (today).
        ends_on: The last day planned.
        blocks: The proposal, by day and time.
        unplaced: Tasks that didn't fit, soonest due first.
        assumptions: Every assumption, in words.
    """
    starts_on: date
    ends_on: date
    blocks: list[PlannedBlock] = Field(default_factory=list)
    unplaced: list[Unplaced] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class AcceptBlock(BaseModel):
    """One block to put on the calendar.

    Attributes:
        task_id: The task it is for; must be the caller's open task.
        on_date: The day.
        starts_at: Local start.
        ends_at: Local end, after the start.
    """
    task_id: UUID
    on_date: date
    starts_at: time
    ends_at: time

    @model_validator(mode="after")
    def ends_after_it_starts(self) -> "AcceptBlock":
        """Refuse a block that ends before it starts.

        Returns:
            The block.

        Raises:
            ValueError: If `ends_at` is not after `starts_at`.
        """
        if self.ends_at <= self.starts_at:
            raise ValueError("A block has to end after it starts")
        return self


class AcceptPlan(BaseModel):
    """The blocks to accept.

    Attributes:
        blocks: One to `MAX_ACCEPTED`.
    """
    blocks: list[AcceptBlock] = Field(..., min_length=1, max_length=MAX_ACCEPTED)


class AcceptedPlan(BaseModel):
    """What was written.

    Attributes:
        created: Events written, one per block.
    """
    created: int
