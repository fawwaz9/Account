"""Request and response bodies for the job application tracker and its seasons.

An application's status is its latest dated step; `application_service` reads the
step history to build the list, the reply figures and the Sankey flows.
"""
import re
from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

#: Nobody is offered more than this, and a figure past it is a slipped digit.
MAX_OFFER = 10_000_000.0


class ApplicationStatus(str, Enum):
    """The statuses an application moves through, roughly in order.

    Accepted, rejected, no reply and withdrawn end an application, though a late
    answer can still follow a "no reply".
    """

    APPLIED = "applied"
    SCREENING = "screening"
    #: Each round is its own step (D2).
    INTERVIEW = "interview"
    OFFER = "offer"
    #: An offer you took; turning one down is "withdrawn" after "offer" (D2).
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    #: Suggested after 30 quiet days, never set on its own (D3).
    NO_REPLY = "no_reply"
    WITHDRAWN = "withdrawn"


class OfferPeriod(str, Enum):
    """How often an offer's pay amount is paid: per hour, per month or per year."""

    HOURLY = "hourly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


def _offer_pair(amount, period):
    """Raise ValueError unless an offer's amount and period are set together."""
    if (amount is None) != (period is None):
        raise ValueError("An offer's pay needs both an amount and how often")


class ApplicationIn(BaseModel):
    """Request body for recording a new job application.

    Attributes:
        company: Employer, 1-120 characters and not blank.
        role: Job title applied for, 1-120 characters and not blank.
        applied_on: The day it was sent; dates the first step and decides which
            seasons include it.
        source: Where the posting was found (a job board, a referral), up to 120
            characters.
        link: Address of the posting, up to 500 characters.
        location: Where the job is, up to 120 characters.
        notes: Free text, up to 2000 characters.
        deadline: When applications close.
        follow_up_on: When to chase it.
        offer_amount: Pay offered, in dollars, above 0 and at most 10,000,000;
            private to its owner. Needs `offer_period`.
        offer_period: How often `offer_amount` is paid; needs `offer_amount`.
    """

    company: str = Field(..., min_length=1, max_length=120)
    role: str = Field(..., min_length=1, max_length=120)
    applied_on: date
    source: str | None = Field(default=None, max_length=120)
    link: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    deadline: date | None = None
    follow_up_on: date | None = None
    #: Private to you (D5).
    offer_amount: float | None = Field(default=None, gt=0, le=MAX_OFFER)
    offer_period: OfferPeriod | None = None

    @model_validator(mode="after")
    def validate_application(self):
        """Refuse a blank company or role, or an offer with only half its pay given.

        Returns:
            The validated model.

        Raises:
            ValueError: If `company` or `role` is blank, or exactly one of
                `offer_amount` and `offer_period` is set.
        """
        if not self.company.strip() or not self.role.strip():
            raise ValueError("An application needs a company and a role")
        _offer_pair(self.offer_amount, self.offer_period)
        return self


class ApplicationUpdate(BaseModel):
    """Request body for editing an application; only the fields sent are changed.

    The service re-checks the offer pair against the stored row, since a patch may
    carry only one half of it.

    Attributes:
        company: New employer; blank or null is refused.
        role: New role; blank or null is refused.
        applied_on: New application date, which moves the first step with it;
            refused if a later step is dated before it. Null is ignored.
        source: New source; null or blank clears it.
        link: New link; null or blank clears it.
        location: New location; null or blank clears it.
        notes: New notes; null or blank clears them.
        deadline: New deadline; null clears it.
        follow_up_on: New follow-up date; null clears it.
        offer_amount: New offer amount; null clears it.
        offer_period: New offer period; null clears it.
    """

    company: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    applied_on: date | None = None
    source: str | None = Field(default=None, max_length=120)
    link: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    deadline: date | None = None
    follow_up_on: date | None = None
    offer_amount: float | None = Field(default=None, gt=0, le=MAX_OFFER)
    offer_period: OfferPeriod | None = None


class StepIn(BaseModel):
    """Request body for a status change on an application.

    Attributes:
        status: What happened; any status except applied, which only the
            application's creation writes.
        on_date: The day it happened; not before the application date.
        note: Up to 500 characters; blank becomes None.
    """

    status: ApplicationStatus
    on_date: date
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_step(self):
        """Refuse "applied", which is never a later step.

        Returns:
            The validated model.

        Raises:
            ValueError: If `status` is applied.
        """
        if self.status == ApplicationStatus.APPLIED:
            raise ValueError("Every application starts as applied; pick what happened next")
        return self


class Step(BaseModel):
    """One dated status change in an application's history.

    Attributes:
        id: The step's id.
        status: The status it moved to.
        on_date: The day it happened.
        note: The note recorded with it.
    """

    id: UUID
    status: ApplicationStatus
    on_date: date
    note: str | None = None


class Application(BaseModel):
    """An application as the API returns it, with its whole history.

    Attributes:
        id: The application's id.
        company: Employer.
        role: Job title.
        applied_on: The day it was sent.
        source: Where the posting was found.
        link: Address of the posting.
        location: Where the job is.
        notes: Free text.
        status: The latest step's status.
        deadline: When applications close.
        follow_up_on: When to chase it.
        offer_amount: Pay offered, in dollars.
        offer_period: How often `offer_amount` is paid.
        steps: Every step, oldest first, starting with "applied".
        last_step_on: The date of the latest step.
        quiet: True when still waiting on the employer (applied, screening or
            interview) and nothing has happened for 30 days.
        created_at: When it was recorded, naive UTC.
        updated_at: When it last changed, naive UTC.
    """

    id: UUID
    company: str
    role: str
    applied_on: date
    source: str | None = None
    link: str | None = None
    location: str | None = None
    notes: str | None = None
    status: ApplicationStatus
    deadline: date | None = None
    follow_up_on: date | None = None
    offer_amount: float | None = None
    offer_period: OfferPeriod | None = None
    steps: list[Step]
    #: The day of the latest step.
    last_step_on: date
    #: Quiet for 30 days while still waiting on them: "no reply yet?" (D3).
    quiet: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Flow(BaseModel):
    """One band of the applications Sankey: how many moved from one stage to the next.

    Attributes:
        source: The stage the band leaves, a status.
        target: The stage it enters, a status or "waiting" for one still open.
        count: How many applications made that move.
    """

    source: str
    target: str
    count: int


class ApplicationStats(BaseModel):
    """Figures for a set of applications, all read from their step histories.

    Attributes:
        total: Applications in the set.
        open: Still at applied, screening, interview or offer.
        replied: Heard back at all: a screening, interview, offer, acceptance or
            rejection.
        reply_rate: `replied / total` as a fraction to 3 dp; None for an empty set.
        median_days_to_reply: Median days from applying to the first reply, over
            those that replied; None when none did.
        interviews: Applications with at least one interview.
        offers: Applications with an offer; an acceptance counts as one.
        accepted: Applications accepted.
        by_status: How many applications sit at each current status.
        flows: The Sankey bands, largest first.
    """

    total: int
    #: Still at applied, screening, interview or offer.
    open: int
    #: Heard back at all: screening, an interview, an offer, or a rejection.
    replied: int
    #: replied / total, or null with nothing applied for.
    reply_rate: float | None = None
    #: From applying to the first reply, over the ones that replied.
    median_days_to_reply: float | None = None
    interviews: int
    offers: int
    accepted: int
    by_status: dict[str, int]
    flows: list[Flow]


#: A season longer than this is a typo, not a recruiting season.
MAX_SEASON_MONTHS = 24
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class SeasonIn(BaseModel):
    """Request body for creating or replacing a recruiting season.

    Attributes:
        name: 1-60 characters and not blank.
        starts: First month, written YYYY-MM.
        ends: Last month, written YYYY-MM and counted whole; the season spans at
            most 24 months.
    """

    name: str = Field(..., min_length=1, max_length=60)
    starts: str = Field(..., description="First month, YYYY-MM")
    ends: str = Field(..., description="Last month, YYYY-MM, counted whole")

    @field_validator("starts", "ends")
    @classmethod
    def check_month(cls, value: str) -> str:
        """Check that a month is written YYYY-MM.

        Args:
            value: The submitted month.

        Returns:
            The value, unchanged.

        Raises:
            ValueError: If it is not a YYYY-MM month.
        """
        if not MONTH.match(value):
            raise ValueError("A month is written YYYY-MM")
        return value

    @model_validator(mode="after")
    def check_season(self):
        """Check the name, and that the season runs forward for at most 24 months.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank, `ends` is before `starts`, or the season
                spans more than 24 months.
        """
        if not self.name.strip():
            raise ValueError("A season needs a name")
        start_y, start_m = map(int, self.starts.split("-"))
        end_y, end_m = map(int, self.ends.split("-"))
        months = (end_y - start_y) * 12 + (end_m - start_m) + 1
        if months < 1:
            raise ValueError("A season ends on or after the month it starts")
        if months > MAX_SEASON_MONTHS:
            raise ValueError(f"A season is at most {MAX_SEASON_MONTHS} months")
        return self


class Season(BaseModel):
    """A recruiting season as the API returns it.

    Attributes:
        id: The season's id.
        name: The season's name.
        starts: First month, YYYY-MM.
        ends: Last month, YYYY-MM, inclusive.
    """

    id: UUID
    name: str
    starts: str
    ends: str
