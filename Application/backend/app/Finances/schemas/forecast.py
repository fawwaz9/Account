"""The money room's foresight: where the balance is heading, and how long it lasts.

Phase 1 item 9 (account-vision.md §13.3). Every figure here is a projection,
so every response carries the assumptions it was made on -- a forecast that
hides them is a guess dressed as an answer (§15, "always show assumptions").
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    on_date: date
    #: Spending-account balance at the end of the day.
    balance: float


class ForecastEvent(BaseModel):
    """A dated movement the forecast expects: a standing instruction, or pay."""

    on_date: date
    description: str
    #: Signed like a transaction: negative is money leaving the spending accounts.
    amount: float
    source: Literal["recurring", "pay"]
    #: Divided by the income split on the way in (pay, and split deposits).
    split: bool = False


class Runway(BaseModel):
    """How long the money you hold lasts at the recent pace."""

    #: Spending, savings and emergency balances. Investments and debt are out.
    liquid: float
    #: Average net money out per day over the look-back, all accounts.
    daily_burn: float
    #: Null when nothing is being burned, or there is nothing to burn.
    lasts_until: date | None = None


class MerchantRunRate(BaseModel):
    """Where one-off spending is going, at the current pace, to the horizon."""

    merchant: str
    #: What it came to over the look-back.
    spent: float
    occurrences: int
    #: The same pace carried from today to the forecast's end.
    projected: float


class CashFlowForecast(BaseModel):
    starts_on: date
    ends_on: date
    #: True when the horizon is the end of the current term, false when the term
    #: is not known and a fixed sixteen weeks stands in for it.
    ends_at_term_end: bool
    starting_balance: float
    #: Average one-off spending per day: expenses with no standing instruction
    #: behind them and no tuition, from spending accounts.
    daily_spending: float
    #: How many days of history that average rests on.
    spending_history_days: int
    points: list[ForecastPoint] = Field(default_factory=list)
    events: list[ForecastEvent] = Field(default_factory=list)
    #: The first day the spending accounts go below zero, if they do.
    negative_on: date | None = None
    lowest_balance: float
    lowest_on: date
    ending_balance: float
    runway: Runway | None = None
    run_rates: list[MerchantRunRate] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
