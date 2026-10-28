"""Response bodies for the cash-flow forecast: the balance ahead, runway and run-rates.

Every figure is a projection, so each response lists the assumptions it rests
on. `forecast_service` builds it from the counted spending accounts.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    """The projected spending balance at the end of one day.

    Attributes:
        on_date: The day.
        balance: The counted spending accounts' combined balance at the day's end,
            in dollars and signed.
    """

    on_date: date
    #: Spending-account balance at the end of the day.
    balance: float


class ForecastEvent(BaseModel):
    """A dated movement the forecast expects: a standing instruction, or pay.

    Attributes:
        on_date: The day it is expected.
        description: What it is, such as "Pay: Cafe" or the instruction's text.
        amount: Its effect on the spending accounts in dollars, signed like a
            transaction (negative leaves them).
        source: "recurring" for a standing instruction, "pay" for a paycheque.
        split: True when the amount was scaled by the spending accounts' share of
            the income split (pay and split deposits).
    """

    on_date: date
    description: str
    #: Signed like a transaction: negative is money leaving the spending accounts.
    amount: float
    source: Literal["recurring", "pay"]
    #: Divided by the income split on the way in (pay, and split deposits).
    split: bool = False


class Runway(BaseModel):
    """How long liquid money lasts at the recent net pace.

    Attributes:
        liquid: Counted spending, savings and emergency balances, in dollars.
        daily_burn: Average net money out per day over the look-back (income and
            expenses on counted accounts; transfers excluded); 0 when money in
            kept pace.
        lasts_until: The day liquid money runs out at that pace; None when nothing
            is being burned or nothing is held.
    """

    #: Spending, savings and emergency balances. Investments and debt are out.
    liquid: float
    #: Average net money out per day over the look-back, all accounts.
    daily_burn: float
    #: Null when nothing is being burned, or there is nothing to burn.
    lasts_until: date | None = None


class MerchantRunRate(BaseModel):
    """Where one-off spending goes, at the recent pace carried to the horizon.

    Attributes:
        merchant: The merchant, as most recently described.
        spent: What it came to over the look-back, positive.
        occurrences: One-off purchases there in the look-back; at least two.
        projected: The same daily pace carried from today to the horizon.
    """

    merchant: str
    #: What it came to over the look-back.
    spent: float
    occurrences: int
    #: The same pace carried from today to the forecast's end.
    projected: float


class CashFlowForecast(BaseModel):
    """The forecast for the counted spending accounts, from today to the horizon.

    Attributes:
        starts_on: Today, on the user's clock.
        ends_on: The horizon: the current term's end, or 16 weeks out.
        ends_at_term_end: True when the horizon is the term's end; False when the
            term's dates are unknown, or it ends within a week, and 16 weeks stands
            in.
        starting_balance: The counted spending accounts' balances today.
        daily_spending: Average one-off spending per day over the look-back:
            expenses with no standing instruction and no tuition, from spending
            accounts and cards.
        spending_history_days: Days of history that average rests on, up to 56.
        points: One projected balance per day, today to the horizon.
        events: The standing instructions and pay expected, by date.
        negative_on: The first day the balance goes below zero; None if it never
            does.
        lowest_balance: The lowest projected balance.
        lowest_on: The day of the lowest balance.
        ending_balance: The balance on the horizon.
        runway: How long liquid money lasts; None with no history.
        run_rates: Up to five merchants with the most projected one-off spending.
        assumptions: Every assumption the figures rest on, in plain sentences.
    """

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
