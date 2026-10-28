"""Response bodies for the year plan, the hours-to-goal solver and plan against actual.

The year plan is one running balance of liquid money (spending, savings and
emergency accounts) from today to the end of the school year, rolled up by
month. `plan_service` builds it; `plan_review_service` sets saved plans against
the months they forecast.
"""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class PlanMonth(BaseModel):
    """One month of the year plan.

    Attributes:
        month: The first of the month.
        money_in: Pay and standing instructions expected to arrive, in dollars.
        money_out: Standing charges and day-to-day spending expected to leave, as
            a positive figure.
        end_balance: The projected liquid balance on the month's last day inside
            the plan.
    """

    #: The first of the month.
    month: date
    money_in: float
    #: Positive: what leaves, standing charges and day-to-day spending together.
    money_out: float
    #: Liquid balance on the last day of the month inside the plan.
    end_balance: float


class Scenario(BaseModel):
    """One what-if for the solver: extra hours a week, and where the plan then ends.

    Attributes:
        extra_hours_per_week: Extra hours worked each week at the priced job.
        end_balance: The plan's ending balance with those hours, in dollars.
    """

    extra_hours_per_week: float
    end_balance: float


class Goal(BaseModel):
    """What reaching a target balance by a date would take in extra hours of work.

    Attributes:
        target: The balance aimed for, in dollars.
        target_on: The date it is wanted by, which is also the plan's end.
        base_end_balance: Where the plan ends with no extra work.
        shortfall: `target` less `base_end_balance`; zero or negative when already
            met.
        job_name: The job extra hours are priced at: the first current hourly job
            with a rate, in the user's order.
        net_hourly: What one extra hour adds to liquid money: the rate after
            recent deductions, times the liquid accounts' share of the income split.
        weeks: Weeks from today to `target_on`, 1 dp.
        extra_hours_per_week: Extra hours a week needed, rounded up to the half
            hour; None when the target is already met.
        scenarios: Ending balances with 0, 4, 8, 12 and 16 extra hours a week.
    """

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
    """The year plan, from today to the end of the school year or a target date.

    Attributes:
        starts_on: Today, on the user's clock.
        ends_on: The Winter term's last day (April 30 when the school year is not
            known), or the target date.
        starting_balance: Counted, unarchived liquid balances today.
        months: One row per calendar month the plan touches.
        ending_balance: The projected balance on `ends_on`.
        lowest_balance: The lowest projected balance.
        lowest_on: The day of the lowest balance.
        goal: The solver's answer, when a target was asked for and an hourly job
            can price it.
        assumptions: Every assumption the figures rest on, in plain sentences.
    """

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
    """A saved year plan's identity; its monthly rows are compared, not returned.

    Attributes:
        id: The saved plan's id.
        saved_on: The user's date when it was saved.
        starts_on: The plan's first day.
        ends_on: The plan's last day.
    """

    id: UUID
    saved_on: date
    starts_on: date
    ends_on: date

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class MonthReview(BaseModel):
    """One finished month: what the plan said, and what happened.

    Attributes:
        month: The first of the month.
        plan_saved_on: The day the plan used was saved: the newest saved before the
            month began.
        planned_in: That plan's money in for the month.
        planned_out: That plan's money out for the month.
        planned_end: That plan's closing balance for the month.
        actual_in: Money into counted liquid accounts: income, and transfers in
            from accounts that are not liquid.
        actual_out: Money out of counted liquid accounts plus card purchases, as a
            positive figure, tuition included.
        actual_end: The counted liquid accounts' balance at the month's end,
            archived ones included.
        tuition_out: The tuition inside `actual_out`, which the plan leaves out.
    """

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
    """Saved plans set against the finished months they forecast.

    Attributes:
        latest: The newest saved plan; None when none has been saved.
        months: Finished months with a plan saved before they began, oldest first.
    """

    #: The newest saved plan; null when none has been saved.
    latest: SavedPlan | None = None
    #: Finished months with a plan saved before they began, oldest first.
    months: list[MonthReview] = Field(default_factory=list)
