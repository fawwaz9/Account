"""The year plan and the hours-to-goal solver (Phase 1 item 10, §13.4).

The owner's September-April spreadsheet, generated: every inflow and outflow
the app already knows, laid out month by month as a running balance -- then
solved backwards into the weekly hours a target needs.
"""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class PlanMonth(BaseModel):
    #: The first of the month.
    month: date
    money_in: float
    #: Positive: what leaves, standing charges and day-to-day spending together.
    money_out: float
    #: Liquid balance on the last day of the month inside the plan.
    end_balance: float


class Scenario(BaseModel):
    extra_hours_per_week: float
    end_balance: float


class Goal(BaseModel):
    target: float
    target_on: date
    #: What the plan ends at with no extra work. Negative shortfall: already met.
    base_end_balance: float
    shortfall: float
    #: The hourly job extra hours are priced at.
    job_name: str
    #: What one extra hour adds to liquid money: rate, after deductions, at the
    #: liquid accounts' income share.
    net_hourly: float
    weeks: float
    #: Null when the target is already met.
    extra_hours_per_week: float | None = None
    scenarios: list[Scenario] = Field(default_factory=list)


class AnnualPlan(BaseModel):
    starts_on: date
    ends_on: date
    starting_balance: float
    months: list[PlanMonth] = Field(default_factory=list)
    ending_balance: float
    lowest_balance: float
    lowest_on: date
    #: Present when a target was asked for and an hourly job can price it.
    goal: Goal | None = None
    assumptions: list[str] = Field(default_factory=list)


# --- plan against actual (Phase 1 D37) ---------------------------------------

class SavedPlan(BaseModel):
    """A saved plan's identity; its rows are compared, not shown again."""

    id: UUID
    saved_on: date
    starts_on: date
    ends_on: date

    class Config:
        from_attributes = True


class MonthReview(BaseModel):
    """One finished month: what the plan said, and what happened."""

    month: date
    #: The day the plan this month is compared with was saved.
    plan_saved_on: date
    planned_in: float
    planned_out: float
    planned_end: float
    actual_in: float
    actual_out: float
    actual_end: float
    #: Tuition paid this month. Part of `actual_out`; the plan leaves tuition
    #: out, so this much of any overspend is that and not the pace.
    tuition_out: float = 0.0


class PlanReview(BaseModel):
    #: The newest saved plan; null when none has been saved.
    latest: SavedPlan | None = None
    #: Finished months with a plan saved before they began, oldest first.
    months: list[MonthReview] = Field(default_factory=list)
