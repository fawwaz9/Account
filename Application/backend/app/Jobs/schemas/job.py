"""Request and response bodies for jobs, pay schedules, shifts and shift records.

A job is hourly, salaried or contract, and pays by the shared repeat rule or on
set days of the month. Shifts are calendar events carrying a `job_id`; what
happened on one date of a shift is a shift record. `job_service` and
`pay_schedule` read and write these.
"""

from datetime import date, datetime, time
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.schemas.event import Recurrence, Weekday

#: Nothing anyone is paid is beyond this, and a figure past it is a slipped
#: digit rather than a wage.
MAX_HOURLY_RATE = 1000.0
MAX_PERIOD_AMOUNT = 1_000_000.0
"""Ceiling, in dollars, on a salaried job's amount per pay period and on one tip."""


class JobKind(str, Enum):
    """How a job pays, which decides what "expected pay" means for it.

    Each kind answers "what should this have paid?" differently, so a long week on
    a salaried job never reads as a pay cut.
    """

    #: Hours times a rate. The hours are the pay.
    HOURLY = "hourly"
    #: A fixed amount per pay period, however many hours it took.
    SALARIED = "salaried"
    #: You invoice; the amount is whatever you billed.
    CONTRACT = "contract"


class WeekendRule(str, Enum):
    """Where a set pay date that lands on a Saturday or Sunday moves.

    Attributes:
        PREVIOUS: To the Friday before.
        NEXT: To the Monday after.
        KEEP: It stays on the weekend day.
    """

    PREVIOUS = "previous"
    NEXT = "next"
    KEEP = "keep"


class NthWeekday(BaseModel):
    """One Nth weekday of the month: the last Friday is n=-1, day=FR.

    Attributes:
        n: 1 to 4, or -1 for the last such weekday of the month.
        day: The weekday.
    """

    n: int = Field(..., description="1 to 4, or -1 for the last")
    day: Weekday

    @model_validator(mode="after")
    def validate_n(self):
        """Refuse any n other than 1 to 4 or -1.

        Returns:
            The validated model.

        Raises:
            ValueError: If `n` is out of range.
        """
        if self.n not in (1, 2, 3, 4, -1):
            raise ValueError("Pick the 1st to 4th, or the last, weekday of the month")
        return self


class PayDays(BaseModel):
    """Pay on set days of the month, which the shared repeat rule cannot express.

    Set dates may go with the last day; an Nth weekday stands alone. A date the
    month lacks pays on its last day, and only set dates move off a weekend.

    Attributes:
        dates: Days of the month, 1-31, at most four and each once.
        last_day: Also pay on the last day of every month.
        nth_weekdays: Nth weekdays to pay on, at most four and each once; never
            with `dates` or `last_day`.
        weekend: Where a set date that lands on a weekend moves; defaults to the
            Friday before.
        until: Last scheduled pay date, inclusive; None for no end.
    """

    dates: list[int] = Field(default_factory=list, max_length=4)
    last_day: bool = False
    nth_weekdays: list[NthWeekday] = Field(default_factory=list, max_length=4)
    weekend: WeekendRule = WeekendRule.PREVIOUS
    #: Inclusive last pay date, or none.
    until: date | None = None

    @model_validator(mode="after")
    def validate_pattern(self):
        """Check the chosen days, and that an Nth weekday stands alone.

        Returns:
            The validated model.

        Raises:
            ValueError: If a date is outside 1-31 or repeated, an Nth weekday is
                combined with dates or the last day, nothing is chosen, or an Nth
                weekday is repeated.
        """
        if any(day < 1 or day > 31 for day in self.dates):
            raise ValueError("A pay date is a day of the month, 1 to 31")
        if len(set(self.dates)) != len(self.dates):
            raise ValueError("Each pay date only once")
        if self.nth_weekdays and (self.dates or self.last_day):
            raise ValueError("A weekday of the month stands alone: not with dates or the last day")
        if not (self.dates or self.last_day or self.nth_weekdays):
            raise ValueError("Pick at least one pay day")
        keys = [(item.n, item.day) for item in self.nth_weekdays]
        if len(set(keys)) != len(keys):
            raise ValueError("Each weekday of the month only once")
        return self


class JobBase(BaseModel):
    """Fields shared by a job's create body and its response.

    Attributes:
        name: 1-120 characters and not blank.
        employer: Who it is for, up to 120 characters.
        kind: Hourly, salaried or contract; defaults to hourly.
        hourly_rate: Dollars per hour, above 0 and at most 1000; required for an
            hourly job and refused on any other.
        period_amount: Dollars per pay period, above 0 and at most 1,000,000;
            required for a salaried job and refused on any other.
        started_on: First day of the job.
        ended_on: Last day of the job; None while it is current.
        pay_starts_on: First pay date; required with either kind of schedule.
        pay_schedule: Pay by the shared repeat rule; None for no repeat.
        pay_days: Pay on set days of the month; never with `pay_schedule`.
        archived: Hidden from the default job list.
    """

    name: str = Field(..., min_length=1, max_length=120)
    employer: str | None = Field(default=None, max_length=120)
    kind: JobKind = Field(default=JobKind.HOURLY)
    hourly_rate: float | None = Field(default=None, gt=0, le=MAX_HOURLY_RATE)
    period_amount: float | None = Field(default=None, gt=0, le=MAX_PERIOD_AMOUNT)
    started_on: date | None = None
    #: Null while the job is current.
    ended_on: date | None = None
    #: When cheques arrive, as a rule rather than a list of dates. Null means
    #: the job has no schedule set and nothing is predicted.
    pay_starts_on: date | None = None
    pay_schedule: Recurrence | None = None
    #: Pay on set days of the month instead of by `pay_schedule`. Never both.
    pay_days: PayDays | None = None
    archived: bool = False

    @model_validator(mode="after")
    def validate_job(self):
        """Check the name, the dates, the pay field for the kind, and the schedule.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank, the job ends before it starts, the pay
                field does not match the kind, a schedule has no `pay_starts_on`, or
                both kinds of schedule are given.

        Note:
            This also runs whenever a stored job is serialised as `Job`, so a row
            that breaks these rules makes its response fail.
        """
        if self.name.strip() == "":
            raise ValueError("A job needs a name")

        if self.ended_on and self.started_on and self.ended_on < self.started_on:
            raise ValueError("A job cannot end before it starts")

        # Each kind carries the field its own pay rule needs, and only that one.
        # Letting an hourly job hold a period amount would leave two answers to
        # "what should this have paid" with nothing to choose between them.
        if self.kind == JobKind.HOURLY and self.hourly_rate is None:
            raise ValueError("An hourly job needs an hourly rate")
        if self.kind == JobKind.SALARIED and self.period_amount is None:
            raise ValueError("A salaried job needs an amount per pay period")
        if self.kind != JobKind.HOURLY and self.hourly_rate is not None:
            raise ValueError("Only an hourly job has an hourly rate")
        if self.kind != JobKind.SALARIED and self.period_amount is not None:
            raise ValueError("Only a salaried job has an amount per pay period")

        if self.pay_schedule is not None and self.pay_starts_on is None:
            raise ValueError("A pay schedule needs a first pay date")
        if self.pay_days is not None and self.pay_starts_on is None:
            raise ValueError("A pay schedule needs a first pay date")
        if self.pay_schedule is not None and self.pay_days is not None:
            raise ValueError("Pay by a repeat or by days of the month, not both")

        return self


class JobCreate(JobBase):
    """Request body for creating a job: the fields of `JobBase`."""

    pass


class JobUpdate(BaseModel):
    """Request body for editing a job; only the fields sent are changed.

    The cross-field rules are checked by the service against the stored row, which
    also clears the pay field the job's kind does not use.

    Attributes:
        name: New name, 1-120 characters.
        employer: New employer; null clears it.
        kind: New kind.
        hourly_rate: New hourly rate; null clears it, refused if the job is hourly.
        period_amount: New amount per period; null clears it, refused if the job
            is salaried.
        started_on: New start date; null clears it.
        ended_on: New end date; null makes the job current again.
        pay_starts_on: New first pay date.
        pay_schedule: Pay by this repeat rule; null clears it. Refused while
            `pay_days` is stored unless the patch clears that too.
        pay_days: Pay on these days of the month; null clears them. Refused
            alongside a repeat rule in the same way.
        archived: Archive or unarchive.
        position: Place in the job list, 0 or more.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    employer: str | None = Field(default=None, max_length=120)
    kind: JobKind | None = None
    hourly_rate: float | None = Field(default=None, gt=0, le=MAX_HOURLY_RATE)
    period_amount: float | None = Field(default=None, gt=0, le=MAX_PERIOD_AMOUNT)
    started_on: date | None = None
    ended_on: date | None = None
    pay_starts_on: date | None = None
    pay_schedule: Recurrence | None = None
    pay_days: PayDays | None = None
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)


class Job(JobBase):
    """A job as the API returns it: the `JobBase` fields plus these.

    Attributes:
        id: The job's id.
        position: Place in the job list.
        created_at: When it was made, naive UTC.
        next_pay_on: The first pay date from the user's today, within a year;
            None without a schedule.
        is_current: True while `ended_on` is unset.
    """

    id: UUID = Field(default_factory=uuid4)
    position: int = 0
    created_at: datetime | None = None
    #: The next date the pay rule produces, or null when there is no schedule.
    #: Computed per request rather than stored, like every other rule in the app.
    next_pay_on: date | None = None
    #: True while `ended_on` is unset, so a client need not know the convention.
    is_current: bool = True

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class ShiftMeeting(BaseModel):
    """One weekly block of a job's recurring shift pattern, as entered in the form.

    Attributes:
        days: Weekday codes it runs on, at least one; unrecognised codes are
            dropped.
        start_time: Local start time.
        end_time: Local end time, after `start_time` on the same day.
        location: Where it is, up to 120 characters.
    """

    days: list[str] = Field(..., min_length=1, description="Weekday codes it runs on")
    start_time: time
    end_time: time
    location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_meeting(self):
        """Refuse a block that ends at or before its start.

        Returns:
            The validated model.

        Raises:
            ValueError: If `end_time` is not after `start_time`.
        """
        if self.end_time <= self.start_time:
            raise ValueError("A shift cannot end before it starts")
        return self


class ShiftCreate(BaseModel):
    """Request body for one shift on one date, the usual way shifts are entered.

    Attributes:
        on_date: The date of the shift.
        start_time: Local start time.
        end_time: Local end time, after `start_time` on the same day.
        location: Where it is, up to 120 characters.
    """

    on_date: date
    start_time: time
    end_time: time
    location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_shift(self):
        """Refuse a shift that ends at or before its start.

        Returns:
            The validated model.

        Raises:
            ValueError: If `end_time` is not after `start_time`.
        """
        if self.end_time <= self.start_time:
            raise ValueError("A shift cannot end before it starts")
        return self


class ShiftScheduleCreate(BaseModel):
    """Request body that replaces a job's recurring shift pattern.

    Only the job's repeating shift events are replaced; one-off shifts stay. An
    empty `meetings` list removes the pattern.

    Attributes:
        meetings: The weekly blocks.
        starts_on: First date of the pattern; None uses the job's start date, and
            one of the two is required.
        ends_on: Last date, inclusive; None uses the job's end date, or leaves the
            pattern open-ended.
    """

    meetings: list[ShiftMeeting] = Field(default_factory=list)
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        """Reject a pattern that ends before it starts, when both dates are given.

        Returns:
            The validated model.

        Raises:
            ValueError: If `ends_on` is before `starts_on`.
        """
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("A schedule cannot end before it starts")
        return self


class ShiftRecordUpsert(BaseModel):
    """Request body recording what happened on one date of a shift.

    Replaces whatever was recorded for that date before.

    Attributes:
        worked_start: Actual local start; give both times or neither, where
            neither means as scheduled.
        worked_end: Actual local end, after `worked_start`.
        confirmed: Whether the shift is confirmed as worked; defaults to True.
        tip_amount: Tips for the shift, in dollars, 0 to 1,000,000.
        tip_is_cash: True for cash in hand, which is filed to the cash-tip account;
            False for a tip paid on the cheque.
        rate_override: Hourly rate for this date alone, above 0 and at most 1000;
            None uses the job's rate.
        notes: Up to 2000 characters.
    """

    worked_start: time | None = None
    worked_end: time | None = None
    confirmed: bool = True
    tip_amount: float = Field(default=0.0, ge=0, le=MAX_PERIOD_AMOUNT)
    tip_is_cash: bool = True
    rate_override: float | None = Field(default=None, gt=0, le=MAX_HOURLY_RATE)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_record(self):
        """Require both worked times or neither, in order.

        Returns:
            The validated model.

        Raises:
            ValueError: If only one worked time is given, or the end is not after the
                start.
        """
        if (self.worked_start is None) != (self.worked_end is None):
            raise ValueError("Give both a start and an end, or neither")
        if (
            self.worked_start is not None
            and self.worked_end is not None
            and self.worked_end <= self.worked_start
        ):
            raise ValueError("A shift cannot end before it starts")
        return self


class ShiftRecord(BaseModel):
    """What was recorded about one date of a shift.

    Attributes:
        id: The record's id.
        event_id: The shift event the date belongs to.
        job_id: The shift's job.
        on_date: The date recorded.
        worked_start: Actual local start; None means as scheduled.
        worked_end: Actual local end; None means as scheduled.
        confirmed: Whether it is confirmed as worked.
        tip_amount: Tips, in dollars.
        tip_is_cash: Whether the tip was cash.
        rate_override: Hourly rate for this date alone; None uses the job's.
        notes: Free text.
    """

    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    job_id: UUID
    on_date: date
    worked_start: time | None = None
    worked_end: time | None = None
    confirmed: bool = False
    tip_amount: float = 0.0
    tip_is_cash: bool = True
    rate_override: float | None = None
    notes: str | None = None

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class ShiftOccurrence(BaseModel):
    """One date a job's shifts fall on, with what is known about it.

    Expanded per request like every occurrence, so it has no id of its own;
    `(event_id, on_date)` identifies it.

    Attributes:
        event_id: The shift event (one-off or pattern) it comes from.
        job_id: The job.
        job_name: The job's name.
        on_date: The date.
        title: The event's title.
        scheduled_start: Scheduled local start.
        scheduled_end: Scheduled local end.
        location: Where it is.
        scheduled_minutes: Scheduled length; 0 for an untimed shift.
        worked_start: Recorded actual start; None when nothing was entered.
        worked_end: Recorded actual end; None when nothing was entered.
        counted_minutes: The worked length when both worked times are recorded,
            otherwise the scheduled length.
        confirmed: Whether it is confirmed as worked.
        repeats: True for a date from a weekly pattern, which can only be skipped;
            False for a one-off, which can be deleted.
        assumed: True for a shift on or before today that is unconfirmed, so its
            scheduled hours are an assumption.
        tip_amount: Tips recorded, in dollars.
        tip_is_cash: Whether the tip was cash.
        tip_in_ledger: True when a ledger row records the tip; False for an
            on-cheque tip and for a cash tip held because no cash-tip account is
            chosen.
        rate_override: Hourly rate for this date alone, if set.
        notes: Notes recorded for the date.
    """

    event_id: UUID
    job_id: UUID
    job_name: str
    on_date: date
    title: str
    scheduled_start: time | None = None
    scheduled_end: time | None = None
    location: str | None = None
    scheduled_minutes: int = 0
    #: What was actually recorded, when it differs from the schedule. Null means
    #: nothing has been entered, so re-opening a confirmed shift shows what was
    #: entered rather than silently offering the schedule again.
    worked_start: time | None = None
    worked_end: time | None = None
    #: What is counted. Equal to the scheduled minutes until the shift is
    #: confirmed with different times.
    counted_minutes: int = 0
    confirmed: bool = False
    #: False for a shift entered on its own, true for one a weekly pattern
    #: produced. Only a one-off can be deleted outright; a pattern date is
    #: cancelled through the calendar's existing skip, since it has no row of
    #: its own to remove.
    repeats: bool = False
    #: True for a past shift nobody has confirmed: its hours are being assumed
    #: from the schedule rather than known. Kept visible so a total can say how
    #: much of itself is a guess.
    assumed: bool = False
    tip_amount: float = 0.0
    tip_is_cash: bool = True
    #: Whether this tip has actually reached the budget. False for a tip paid on
    #: the cheque, which arrives inside its gross instead, and false for a cash
    #: tip that had nowhere to go because no account takes an income share.
    tip_in_ledger: bool = False
    rate_override: float | None = None
    notes: str | None = None


class CashTipAccountChoice(BaseModel):
    """Request body choosing the account cash tips are filed into.

    Attributes:
        account_id: One of the user's active accounts; null clears the choice,
            and later cash tips are held.
    """

    account_id: UUID | None = None


class CashTipAccountResult(BaseModel):
    """Response body for choosing the cash-tip account.

    Attributes:
        account_id: The account now chosen; None when the choice was cleared.
        filed: How many held cash tips this choice filed into the account.
    """

    account_id: UUID | None
    #: How many held tips were filed into the account by this choice.
    filed: int

