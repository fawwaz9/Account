"""What a week actually costs, and where it has room.

Three readings of one window: the gaps between commitments, the hours those
commitments and their deadlines come to, and how the term's weight is spread
across its weeks.
"""

from datetime import date, time

from pydantic import BaseModel, Field


class FreeBlock(BaseModel):
    """A gap long enough to be worth putting something in."""

    on_date: date
    starts_at: time
    ends_at: time
    minutes: int


class WeekLoad(BaseModel):
    """What the window comes to, in hours rather than in item counts.

    Booked and estimated are kept apart on purpose. Booked time is not optional
    -- a lecture happens whether or not you are ready -- while estimated time is
    a guess you wrote down. One number combining them would hide which half is
    which, and hide that the estimate is missing entirely on most tasks.
    """

    starts_on: date
    ends_on: date
    #: Minutes of every timed event, work included. Unchanged in meaning, so
    #: anything already reading it still gets the whole commitment.
    booked_minutes: int = 0
    #: The part of `booked_minutes` that is paid work. Split out rather than
    #: replaced, because "am I over-committed" wants the total while "is the job
    #: eating the term" wants these two side by side.
    work_minutes: int = 0
    #: The part that is a class, a lab or a discussion.
    class_minutes: int = 0
    #: Minutes you estimated against tasks due in the window -- scaled by
    #: `estimate_ratio` when that is set.
    estimated_minutes: int = 0
    #: The estimates as typed, before any scaling.
    typed_estimated_minutes: int = 0
    #: How long tasks really take against their estimates, when the student
    #: asked for the forecast to use it (Phase 1 D36). Null: not applied.
    estimate_ratio: float | None = None
    task_count: int = 0
    #: Tasks with no estimate, so the number above can be read honestly.
    unestimated_tasks: int = 0
    event_count: int = 0


class CrunchWeek(BaseModel):
    """One week of the term, and how heavily it lands."""

    starts_on: date
    #: Weighted by kind: a final outweighs a midterm outweighs a deadline.
    weight: int = 0
    #: The raw tallies, so the strip can be read without trusting the weighting.
    exams: int = 0
    deadlines: int = 0
    tasks: int = 0
    is_current: bool = False


class CrunchStrip(BaseModel):
    weeks: list[CrunchWeek] = Field(default_factory=list)
    #: The heaviest week's weight, so a bar height is a share of the worst week
    #: rather than of an arbitrary ceiling.
    peak: int = 0
