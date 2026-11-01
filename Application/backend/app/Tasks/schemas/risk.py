"""Response bodies for deadline risk (Phase 4 item 3, §4).

Personal velocity against required velocity: division, not machine learning.
Computed on read from tasks already stored.
"""

from datetime import date

from pydantic import BaseModel, Field


class RiskDeadline(BaseModel):
    """One upcoming due date, and the pace finishing everything due by then needs.

    Attributes:
        due_date: The day.
        tasks: Open tasks due that day.
        titles: Up to three of their titles.
        own_minutes: Estimated minutes on the tasks due that day alone, scaled.
        minutes_by_then: Estimated minutes still open on tasks due on or before it,
            overdue ones included, scaled by the estimate ratio when applied.
        days_left: Days from today to the due date, both counted.
        required_minutes_per_day: `minutes_by_then` over `days_left`.
        at_risk: True when the required pace is above your velocity and the day adds
            estimated work of its own; a day that adds none is no new risk.
        shortfall_minutes: How far short your usual pace falls by then; 0 when on pace.
    """
    due_date: date
    tasks: int
    titles: list[str] = Field(default_factory=list)
    own_minutes: int = 0
    minutes_by_then: int
    days_left: int
    required_minutes_per_day: float
    at_risk: bool
    shortfall_minutes: int = 0


class DeadlineRisk(BaseModel):
    """Your velocity, and every due date in the window measured against it.

    Attributes:
        ready: False until there is enough history to mean anything (§4: "needs
            roughly a term of history"); the deadlines are then empty.
        history_days: Days of finished work behind the velocity, at most `window_days`.
        needed_days: Days of history needed before it speaks.
        counted_tasks: Finished tasks in the window with a time to count.
        needed_tasks: Finished tasks needed before it speaks.
        window_days: How far back velocity looks.
        velocity_minutes_per_day: Minutes of finished work a day, over the window.
        estimate_ratio: The actual-to-estimate ratio applied to open estimates;
            None when not applied.
        unestimated_open: Open tasks due in the horizon with no estimate, which no
            figure here can count.
        horizon_days: How far ahead deadlines are read.
        deadlines: Due dates in the horizon, soonest first.
    """
    ready: bool
    history_days: int
    needed_days: int
    counted_tasks: int
    needed_tasks: int
    window_days: int
    velocity_minutes_per_day: float | None = None
    estimate_ratio: float | None = None
    unestimated_open: int = 0
    horizon_days: int
    deadlines: list[RiskDeadline] = Field(default_factory=list)
