"""The job application tracker (Phase 3 item 1, D2-D5)."""
from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

#: Nobody is offered more than this, and a figure past it is a slipped digit.
MAX_OFFER = 10_000_000.0


class ApplicationStatus(str, Enum):
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
    HOURLY = "hourly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


def _offer_pair(amount, period):
    if (amount is None) != (period is None):
        raise ValueError("An offer's pay needs both an amount and how often")


class ApplicationIn(BaseModel):
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
        if not self.company.strip() or not self.role.strip():
            raise ValueError("An application needs a company and a role")
        _offer_pair(self.offer_amount, self.offer_period)
        return self


class ApplicationUpdate(BaseModel):
    """Every field optional. The offer pair is re-checked against the row in the
    service, since a patch may carry only one half of it."""

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
    """A change in status. "Applied" is the first step, written with the
    application, so it is not offered here."""

    status: ApplicationStatus
    on_date: date
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_step(self):
        if self.status == ApplicationStatus.APPLIED:
            raise ValueError("Every application starts as applied; pick what happened next")
        return self


class Step(BaseModel):
    id: UUID
    status: ApplicationStatus
    on_date: date
    note: str | None = None


class Application(BaseModel):
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
    """One band of the Sankey: how many applications went from one stage to the
    next. A stage is a status, plus "waiting" for one still open."""

    source: str
    target: str
    count: int


class ApplicationStats(BaseModel):
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
