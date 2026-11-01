"""Request and response bodies for self-employed support (Phase 4 item 15, §13.12).

Clients and invoices, the year's self-employment figures, and the CRA rules they
are read against: CPP at both halves, the instalment dates and the $3,000 rule,
and the $30,000 GST/HST small-supplier watch. Tax information with its sources,
never advice; `self_employed_service` builds every figure from what the user
recorded.
"""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

InvoiceState = Literal["outstanding", "overdue", "paid"]


class ClientIn(BaseModel):
    """Request body for adding a client.

    Attributes:
        name: What you call them, 1 to 80 characters.
    """

    name: str = Field(..., min_length=1, max_length=80)


class ClientUpdate(BaseModel):
    """Request body for renaming or archiving a client; only fields sent change.

    Attributes:
        name: New name.
        archived: True to stop offering them for new invoices.
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    archived: bool | None = None


class Client(BaseModel):
    """A client as the API returns it, with their invoice totals.

    Attributes:
        id: The client's id.
        name: Their name.
        archived: No longer offered for new invoices.
        invoices: How many invoices they have.
        invoiced: Dollars invoiced to them, ever.
        unpaid: Dollars invoiced and not yet paid.
    """

    id: UUID
    name: str
    archived: bool
    invoices: int = 0
    invoiced: float = 0.0
    unpaid: float = 0.0


class InvoiceIn(BaseModel):
    """Request body for a new invoice.

    Attributes:
        client_id: One of your clients.
        number: Your invoice number, unique among your invoices.
        description: What it was for; optional.
        issued_on: The day it was issued; the day it counts as revenue.
        due_on: When payment is due; omitted, 30 days after issue.
        amount: Dollars, above 0 and at most $1,000,000.
    """

    client_id: UUID
    number: str = Field(..., min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=200)
    issued_on: date
    due_on: date | None = None
    amount: float = Field(..., gt=0, le=1_000_000)

    @model_validator(mode="after")
    def _due_after_issue(self):
        if self.due_on is not None and self.due_on < self.issued_on:
            raise ValueError("An invoice can't be due before it was issued")
        return self


class InvoiceUpdate(BaseModel):
    """Request body for correcting an invoice; only fields sent change.

    Attributes:
        client_id: Another of your clients.
        number: New number, still unique.
        description: New description; null clears it.
        issued_on: New issue date.
        due_on: New due date, not before the issue date.
        amount: New amount; a paid invoice's deposit is rewritten to match.
    """

    client_id: UUID | None = None
    number: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=200)
    issued_on: date | None = None
    due_on: date | None = None
    amount: float | None = Field(default=None, gt=0, le=1_000_000)


class PaidIn(BaseModel):
    """Request body for marking an invoice paid.

    With neither `account_id` nor `split`, nothing is written to the ledger: the
    payment is already there (imported from a bank file, say).

    Attributes:
        paid_on: The day the money arrived.
        account_id: One of your accounts to record the payment in.
        split: True to split it across your accounts by income share, as a
            paycheque is.
    """

    paid_on: date
    account_id: UUID | None = None
    split: bool = False


class Invoice(BaseModel):
    """An invoice as the API returns it.

    Attributes:
        id: The invoice's id.
        client_id: Who it is to.
        client: Their name.
        number: The invoice number.
        description: What it was for.
        issued_on: Issue date.
        due_on: Due date.
        amount: Dollars invoiced.
        paid_on: Payment date; null while unpaid.
        state: "paid", "overdue" (unpaid past its due date) or "outstanding".
        days_overdue: Days past due while overdue; null otherwise.
        deposited: True when marking it paid wrote a row to the ledger.
    """

    id: UUID
    client_id: UUID
    client: str
    number: str
    description: str | None = None
    issued_on: date
    due_on: date
    amount: float
    paid_on: date | None = None
    state: InvoiceState
    days_overdue: int | None = None
    deposited: bool = False


class BusinessExpense(BaseModel):
    """One expense tagged as partly or wholly for your self-employment.

    Attributes:
        transaction_id: The ledger row.
        occurred_on: When.
        description: Its description.
        amount: The whole expense, in dollars.
        percent: The business share, 1 to 100.
        business_amount: `amount` times `percent`, to the cent.
    """

    transaction_id: UUID
    occurred_on: date
    description: str | None = None
    amount: float
    percent: int
    business_amount: float


class Source(BaseModel):
    """Where a rule or figure comes from.

    Attributes:
        label: The page's title.
        url: Its address.
    """

    label: str
    url: str


class CppEstimate(BaseModel):
    """CPP on the year's net self-employment income, both halves.

    Attributes:
        figures_year: Whose CPP figures were used; the latest the app knows when
            the year is newer.
        rate: The self-employed base rate, as a percent (11.9: both halves).
        exemption: The yearly basic exemption, in dollars.
        ceiling: That year's maximum pensionable earnings.
        second_rate: The self-employed CPP2 rate, as a percent.
        second_ceiling: The second earnings ceiling.
        employment_gross: Gross pay recorded from your jobs that year, which uses
            the exemption and the ceilings first.
        base: Base CPP on the self-employment income, in dollars.
        second: CPP2 on it, in dollars.
        total: `base` plus `second`.
    """

    figures_year: int
    rate: float
    exemption: float
    ceiling: float
    second_rate: float
    second_ceiling: float
    employment_gross: float
    base: float
    second: float
    total: float


class Instalments(BaseModel):
    """The CRA instalment rule and dates, without estimating anyone's tax.

    Attributes:
        threshold: The net-tax-owing line, in dollars ($3,000; $1,800 in Quebec).
        dates: The year's four due dates.
        next_due: The next of them from today; null when none is left this year.
    """

    threshold: float
    dates: list[date]
    next_due: date | None = None


class QuarterTotal(BaseModel):
    """Revenue invoiced in one calendar quarter.

    Attributes:
        label: Such as "Oct-Dec 2026".
        starts_on: The quarter's first day.
        total: Dollars invoiced in it (to date, for the current quarter).
    """

    label: str
    starts_on: date
    total: float


class GstWatch(BaseModel):
    """Revenue against the GST/HST small-supplier threshold.

    Attributes:
        threshold: $30,000.
        quarters: The last four calendar quarters, oldest first, the current one
            to date.
        four_quarter_total: Their sum.
        level: "over" past the threshold over the four quarters (which any one
            quarter past it is too), "approaching" from 80% of it, "under"
            otherwise.
    """

    threshold: float
    quarters: list[QuarterTotal]
    four_quarter_total: float
    level: Literal["under", "approaching", "over"]


class IncomeRange(BaseModel):
    """What a month of self-employment typically brought in, as a range.

    Attributes:
        low: The lower quartile of recent months, in dollars.
        high: The upper quartile.
        months: How many finished months it reads (3 to 6).
    """

    low: float
    high: float
    months: int


class SelfEmployment(BaseModel):
    """A year of self-employment: revenue, expenses, and the CRA rules read against them.

    Attributes:
        year: The calendar year.
        revenue: Dollars invoiced that year, by issue date.
        received: Dollars paid that year, by payment date.
        business_expenses: The business share of tagged expenses that year.
        net: `revenue` less `business_expenses`.
        unpaid: Dollars invoiced and not yet paid, any year.
        overdue: Unpaid invoices past their due date, most overdue first.
        expenses: That year's tagged expenses, newest first.
        cpp: CPP on `net`, both halves.
        instalments: The instalment rule and dates.
        gst: The GST/HST watch, over the four quarters to today.
        typical_month: Recent monthly revenue as a range; null under 3 months.
        next_number: A suggestion for the next invoice number.
        sources: The CRA pages the rules come from.
        note: The standing caveat.
    """

    year: int
    revenue: float
    received: float
    business_expenses: float
    net: float
    unpaid: float
    overdue: list[Invoice]
    expenses: list[BusinessExpense]
    cpp: CppEstimate
    instalments: Instalments
    gst: GstWatch
    typical_month: IncomeRange | None = None
    next_number: str
    sources: list[Source]
    note: str
