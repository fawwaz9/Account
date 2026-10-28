"""Response bodies for the jobs page's earnings figures.

Earned (predicted from the shifts in a window) and paid (cheques dated in it)
are reported side by side and never added together. `earnings_service` builds
every figure here in one pass.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class JobEarnings(BaseModel):
    """One job's hours and money over a window.

    Attributes:
        job_id: The job's id.
        job_name: The job's name.
        kind: "hourly", "salaried" or "contract".
        shift_count: Shift occurrences in the window.
        counted_minutes: Minutes those shifts count for: the worked times where
            recorded, otherwise the scheduled ones.
        assumed_count: Past shifts never confirmed, counted at their scheduled
            hours.
        gross_earned: Predicted gross pay in dollars: hours times rate (a shift's
            override first) plus on-cheque tips for an hourly job, the period
            amount for each pay date in the window for a salaried one, 0 for a
            contract.
        cash_tips: Cash tips recorded on those shifts.
        gross_paid: Gross of this job's cheques dated in the window.
        deducted: Those cheques' deductions.
        net_paid: `gross_paid` less `deducted`.
    """

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
    #: From this job's cheques dated inside the window, kept apart from
    #: `gross_earned` for the same reason the window-level pair is: one is what
    #: the hours say, the other is what the bank saw, and a cheque arriving now
    #: usually pays for work done before the window opened.
    gross_paid: float = 0.0
    deducted: float = 0.0
    net_paid: float = 0.0


class EarningsWindow(BaseModel):
    """One window's hours and money across every job.

    Attributes:
        label: "Past week", "This month" or "This term".
        starts_on: First day of the window.
        ends_on: Last day of the window, inclusive and never after today.
        counted_minutes: The jobs' counted minutes, summed.
        gross_earned: The jobs' predicted gross, summed.
        cash_tips: The jobs' cash tips, summed.
        gross_paid: Gross of every cheque dated in the window.
        deducted: Those cheques' deductions.
        net_paid: `gross_paid` less `deducted`.
        per_job: Each job with a shift, a predicted amount or a cheque in the
            window.
    """

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
    """What an hour of work actually paid in the calendar year to date.

    Measured only over pay periods covered by a cheque that states its period, so
    hours not yet paid for do not drag the rate down.

    Attributes:
        net_per_hour: Net pay per hour worked in those periods, in dollars; None
            when nothing qualifies.
        gross_per_hour: Gross pay per such hour; None when nothing qualifies.
        deduction_percent: Deductions as a percentage of gross, 1 dp; None when
            nothing qualifies.
        paid_minutes: Minutes of shifts inside those periods.
    """

    #: Null when nothing has been paid yet, rather than a zero that would read
    #: as working for nothing.
    net_per_hour: float | None = None
    gross_per_hour: float | None = None
    #: What share of gross pay never reached an account, as a percentage.
    deduction_percent: float | None = None
    paid_minutes: int = 0


class UpcomingPay(BaseModel):
    """Work no cheque has covered yet for one current job, and its next payday.

    Attributes:
        job_id: The job's id.
        job_name: The job's name.
        unpaid_minutes: Minutes of shifts from the day after the latest cheque's
            period (or from the job's start) up to today.
        unpaid_estimate: What those shifts should pay, in dollars, for an hourly
            job; None for salaried and contract jobs.
        next_pay_on: The first pay date from today on; None without a pay
            schedule.
    """

    job_id: UUID
    job_name: str
    #: Hours since the last cheque's period ended, or since the job started.
    unpaid_minutes: int = 0
    #: Null for a contract job, which predicts nothing from hours.
    unpaid_estimate: float | None = None
    next_pay_on: date | None = None


class HoursAgainstClasses(BaseModel):
    """Paid work beside class time, for the current Monday-to-Sunday week.

    Attributes:
        starts_on: The week's Monday.
        ends_on: The week's Sunday.
        work_minutes: Booked shift minutes in the week.
        class_minutes: Booked lecture, lab and discussion minutes.
        task_minutes: Estimated minutes on tasks due that week, scaled by the
            estimate ratio when the user applies it.
    """

    starts_on: date
    ends_on: date
    work_minutes: int = 0
    class_minutes: int = 0
    #: Estimated minutes against tasks due that week, so the third call on the
    #: week is visible beside the two that are already booked.
    task_minutes: int = 0


class EarningsSummary(BaseModel):
    """Everything the jobs page reports, from one pass over the user's jobs.

    Attributes:
        week: The last seven days, today included.
        month: The calendar month to date.
        term: The current term to date; None when the term has no dates or has
            not begun.
        effective_rate: The effective hourly rate for the calendar year to date.
        upcoming: Unpaid work and the next payday, one entry per job without an
            end date.
        this_week: Hours against classes for the current week.
    """

    week: EarningsWindow
    month: EarningsWindow
    term: EarningsWindow | None = None
    effective_rate: EffectiveRate
    upcoming: list[UpcomingPay] = Field(default_factory=list)
    this_week: HoursAgainstClasses | None = None
