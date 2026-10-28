"""Response bodies for the week's load: free time, hours committed, and term crunch.

Three readings of one window, computed by `load_service` from stored events and
tasks: the gaps between commitments, the hours they add up to, and how exams and
deadlines spread across the weeks of a term.
"""

from datetime import date, time

from pydantic import BaseModel, Field


class FreeBlock(BaseModel):
    """A gap in one day's commitments long enough to be worth offering.

    Attributes:
        on_date: The day of the gap.
        starts_at: Local start of the gap, clipped to the study window and to now.
        ends_at: Local end of the gap.
        minutes: Length of the gap in minutes; at least the user's minimum.
    """

    on_date: date
    starts_at: time
    ends_at: time
    minutes: int


class WeekLoad(BaseModel):
    """What a window costs in hours, with booked and estimated time kept apart.

    Booked time (timed events) happens regardless; estimated time is the student's
    guess against tasks due. They are never combined into one figure.

    Attributes:
        starts_on: First day of the window.
        ends_on: Last day of the window, inclusive.
        booked_minutes: Minutes of every timed event in the window, shifts included.
        work_minutes: The part of `booked_minutes` that is shifts.
        class_minutes: The part that is lectures, labs and discussions.
        estimated_minutes: Estimates on tasks due in the window, scaled by
            `estimate_ratio` when it is applied.
        typed_estimated_minutes: The same estimates as typed, before scaling.
        estimate_ratio: Actual-to-estimated ratio applied to the estimates; None
            when the student has not turned it on or there is too little history.
        task_count: Tasks due in the window.
        unestimated_tasks: Of those, how many have no estimate.
        event_count: Event occurrences in the window, all-day ones included.
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
    """One Monday-to-Sunday week of a term, and how heavily it lands.

    Attributes:
        starts_on: The week's Monday.
        weight: Finals count 5, midterms 3, deadline events and due tasks 1 each.
        exams: Midterms and finals in the week.
        deadlines: Deadline events in the week.
        tasks: Tasks due in the week.
        is_current: True for the week holding the user's today.
    """

    starts_on: date
    #: Weighted by kind: a final outweighs a midterm outweighs a deadline.
    weight: int = 0
    #: The raw tallies, so the strip can be read without trusting the weighting.
    exams: int = 0
    deadlines: int = 0
    tasks: int = 0
    is_current: bool = False


class CrunchStrip(BaseModel):
    """Every week of a window with its crunch, empty weeks included.

    Attributes:
        weeks: One entry per week, earliest first.
        peak: The heaviest week's weight, so bars scale to the worst week; 0 when
            the window is empty.
    """

    weeks: list[CrunchWeek] = Field(default_factory=list)
    #: The heaviest week's weight, so a bar height is a share of the worst week
    #: rather than of an arbitrary ceiling.
    peak: int = 0
