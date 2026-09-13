from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class JobEarnings(BaseModel):
    """What one job came to over a window, in hours and money."""

    job_id: UUID
    job_name: str
    kind: str
    shift_count: int = 0
    counted_minutes: int = 0
    #: How many of those shifts are assumed rather than confirmed, so a figure
    #: built partly on guesses can say so instead of reading as fact.
    assumed_count: int = 0
    #: Earned from hours, before anything is taken off. For a salaried job this
    #: is the periods that fell in the window, not the hours -- the hours are
    #: what the job costs you, never what it pays.
    gross_earned: float = 0.0
    #: Cash tips, which reach you without passing through a cheque.
    cash_tips: float = 0.0


class EarningsWindow(BaseModel):
    """One stretch of time, across every job."""

    label: str
    starts_on: date
    ends_on: date
    counted_minutes: int = 0
    #: From the shifts worked. A prediction of what should be paid.
    gross_earned: float = 0.0
    cash_tips: float = 0.0
    #: From cheques that actually arrived in the window. Kept apart from
    #: `gross_earned` because one is what the hours say and the other is what
    #: the bank saw, and they answer different questions.
    gross_paid: float = 0.0
    deducted: float = 0.0
    net_paid: float = 0.0
    per_job: list[JobEarnings] = Field(default_factory=list)


class EffectiveRate(BaseModel):
    """What an hour of your time actually puts in your account.

    Computable only because gross and deductions are both recorded. The
    advertised rate is what you were hired at; this is what survives tax.
    """

    #: Null when nothing has been paid yet, rather than a zero that would read
    #: as working for nothing.
    net_per_hour: float | None = None
    gross_per_hour: float | None = None
    #: What share of gross pay never reached an account, as a percentage.
    deduction_percent: float | None = None
    paid_minutes: int = 0


class UpcomingPay(BaseModel):
    """Work done that no cheque has covered yet, and when one is due."""

    job_id: UUID
    job_name: str
    #: Hours since the last cheque's period ended, or since the job started.
    unpaid_minutes: int = 0
    #: Null for a contract job, which predicts nothing from hours.
    unpaid_estimate: float | None = None
    next_pay_on: date | None = None


class HoursAgainstClasses(BaseModel):
    """Paid work beside timetabled hours, for the current week."""

    starts_on: date
    ends_on: date
    work_minutes: int = 0
    class_minutes: int = 0
    #: Estimated minutes against tasks due that week, so the third call on the
    #: week is visible beside the two that are already booked.
    task_minutes: int = 0


class EarningsSummary(BaseModel):
    """Everything the jobs page reports, from one pass over one window."""

    week: EarningsWindow
    month: EarningsWindow
    term: EarningsWindow | None = None
    effective_rate: EffectiveRate
    upcoming: list[UpcomingPay] = Field(default_factory=list)
    this_week: HoursAgainstClasses | None = None
