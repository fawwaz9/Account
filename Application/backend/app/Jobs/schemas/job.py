from datetime import date, datetime, time
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.schemas.event import Recurrence

#: Nothing anyone is paid is beyond this, and a figure past it is a slipped
#: digit rather than a wage.
MAX_HOURLY_RATE = 1000.0
MAX_PERIOD_AMOUNT = 1_000_000.0


class JobKind(str, Enum):
    """How a job pays, which is what makes the three genuinely different.

    Not styling on one arrangement: each answers "what should this have paid?"
    with a different question, and pretending otherwise is what makes a salaried
    job look underpaid every time you work a long week.
    """

    #: Hours times a rate. The hours are the pay.
    HOURLY = "hourly"
    #: A fixed amount per pay period, however many hours it took.
    SALARIED = "salaried"
    #: You invoice; the amount is whatever you billed.
    CONTRACT = "contract"


class JobBase(BaseModel):
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
    archived: bool = False

    @model_validator(mode="after")
    def validate_job(self):
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

        return self


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    """Every field optional, and the cross-field rules re-checked in the service.

    They cannot run here: changing only `kind` leaves the validator with no way
    to see the rate already stored, so it would reject a legitimate edit.
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
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)


class Job(JobBase):
    id: UUID = Field(default_factory=uuid4)
    position: int = 0
    created_at: datetime | None = None
    #: The next date the pay rule produces, or null when there is no schedule.
    #: Computed per request rather than stored, like every other rule in the app.
    next_pay_on: date | None = None
    #: True while `ended_on` is unset, so a client need not know the convention.
    is_current: bool = True

    class Config:
        from_attributes = True


class ShiftMeeting(BaseModel):
    """One recurring block of a job's schedule, as entered in the form.

    The same shape as a course's `ClassMeeting`, because a work pattern and a
    timetable are the same thing: some days, a start, an end, repeated until the
    job or the term ends.
    """

    days: list[str] = Field(..., min_length=1, description="Weekday codes it runs on")
    start_time: time
    end_time: time
    location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_meeting(self):
        if self.end_time <= self.start_time:
            raise ValueError("A shift cannot end before it starts")
        return self


class ShiftCreate(BaseModel):
    """One shift on one date.

    The ordinary way a student's shifts arrive: named hours on a named day,
    rarely the same twice. A weekly pattern is the exception and has its own
    shape below.
    """

    on_date: date
    start_time: time
    end_time: time
    location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_shift(self):
        if self.end_time <= self.start_time:
            raise ValueError("A shift cannot end before it starts")
        return self


class ShiftScheduleCreate(BaseModel):
    """A job's whole recurring pattern, replacing whatever was there before."""

    meetings: list[ShiftMeeting] = Field(default_factory=list)
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("A schedule cannot end before it starts")
        return self


class ShiftRecordUpsert(BaseModel):
    """What actually happened on one date of a shift."""

    worked_start: time | None = None
    worked_end: time | None = None
    confirmed: bool = True
    tip_amount: float = Field(default=0.0, ge=0, le=MAX_PERIOD_AMOUNT)
    tip_is_cash: bool = True
    rate_override: float | None = Field(default=None, gt=0, le=MAX_HOURLY_RATE)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_record(self):
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
        from_attributes = True


class ShiftOccurrence(BaseModel):
    """One date a job's schedule actually falls on, with what is known about it.

    Materialised per request like every other occurrence, so it has no id of its
    own: `(event_id, on_date)` is what identifies it.
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
    """Where cash tips go. Null clears the choice, and later tips are held."""

    account_id: UUID | None = None


class CashTipAccountResult(BaseModel):
    account_id: UUID | None
    #: How many held tips were filed into the account by this choice.
    filed: int

