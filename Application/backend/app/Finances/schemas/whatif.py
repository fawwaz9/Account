"""Request and response bodies for the money what-if (Phase 4 item 14, §13.5).

The year plan re-run with changed inputs: hours, a stretch with no shifts, the
wage, day-to-day spending, one-off purchases. Baseline and scenario side by
side, every assumption listed, absurd inputs capped and said. It stays on the
money side: no academic figure in either direction (§13.3, §13.5).
"""

from datetime import date

from pydantic import BaseModel, Field, model_validator

#: One-off purchases in one scenario.
MAX_PURCHASES = 10


class Purchase(BaseModel):
    """A one-off spend on a day.

    Attributes:
        label: What it is, such as "laptop".
        amount: Dollars, above 0, at most 100,000.
        on_date: The day it is spent.
    """
    label: str = Field(..., min_length=1, max_length=60)
    amount: float = Field(..., gt=0, le=100_000)
    on_date: date


class WhatIfIn(BaseModel):
    """A scenario. Every field left at its default changes nothing.

    Attributes:
        hours_per_week: Hours a week more (or fewer, negative) at the main hourly
            job, -40 to 40.
        hours_from: First day the change applies; the plan's start when None.
        hours_until: Last day it applies; the plan's end when None.
        no_shifts_from: First day of a stretch with no shifts at all.
        no_shifts_until: Its last day; both or neither.
        hourly_rate: A different hourly rate at the main job, above 0, at most 200.
        monthly_spending_change: Dollars a month more (or less, negative) in
            day-to-day spending, -10,000 to 10,000.
        purchases: One-off purchases, at most `MAX_PURCHASES`.
    """
    hours_per_week: float = Field(default=0.0, ge=-40, le=40)
    hours_from: date | None = None
    hours_until: date | None = None
    no_shifts_from: date | None = None
    no_shifts_until: date | None = None
    hourly_rate: float | None = Field(default=None, gt=0, le=200)
    monthly_spending_change: float = Field(default=0.0, ge=-10_000, le=10_000)
    purchases: list[Purchase] = Field(default_factory=list, max_length=MAX_PURCHASES)

    @model_validator(mode="after")
    def windows_make_sense(self) -> "WhatIfIn":
        """Refuse a window that ends before it starts, or a no-shifts stretch with one end.

        Returns:
            The scenario.

        Raises:
            ValueError: For an inverted window or a half-given stretch.
        """
        if (self.no_shifts_from is None) != (self.no_shifts_until is None):
            raise ValueError("A stretch with no shifts needs both a first and a last day")
        for start, end in ((self.hours_from, self.hours_until), (self.no_shifts_from, self.no_shifts_until)):
            if start and end and end < start:
                raise ValueError("A window can't end before it starts")
        return self


class WhatIfPoint(BaseModel):
    """The liquid balance at the end of a day.

    Attributes:
        on_date: The day.
        balance: Dollars, signed.
    """
    on_date: date
    balance: float


class WhatIfOutcome(BaseModel):
    """One side of the comparison.

    Attributes:
        ending_balance: At the plan's end.
        lowest_balance: The lowest point.
        lowest_on: When it is reached.
        negative_on: The first day below zero, if any.
        points: The balance weekly, plus the last day, for the curve.
    """
    ending_balance: float
    lowest_balance: float
    lowest_on: date
    negative_on: date | None = None
    points: list[WhatIfPoint] = Field(default_factory=list)


class ExamSeason(BaseModel):
    """A suggested stretch with no shifts: the three weeks up to the last final.

    Attributes:
        starts_on: Its first day.
        ends_on: Its last day, the last final on the calendar in the plan.
    """
    starts_on: date
    ends_on: date


class WhatIfResult(BaseModel):
    """Baseline and scenario side by side.

    Attributes:
        starts_on: The plan's first day.
        ends_on: Its last day.
        baseline: The plan as it stands.
        scenario: The plan with the changes.
        difference: Scenario ending less baseline ending.
        exam_season: The suggested no-shifts stretch, when finals are on the calendar.
        assumptions: The plan's assumptions, then the scenario's.
        capped: Inputs that went past what the data allows, and what was used instead.
    """
    starts_on: date
    ends_on: date
    baseline: WhatIfOutcome
    scenario: WhatIfOutcome
    difference: float
    exam_season: ExamSeason | None = None
    assumptions: list[str] = Field(default_factory=list)
    capped: list[str] = Field(default_factory=list)
