"""Request and response bodies for standing instructions: payments that repeat.

A standing instruction stores a rule and a template; `recurring_service` writes
each payment into the ledger once it falls due and projects the rest as
upcoming charges.
"""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.schemas.event import Recurrence
from app.Finances.schemas.transaction import Transaction, TransactionKind


DEPOSIT = "deposit"
EXPENSE = TransactionKind.EXPENSE.value
INCOME = TransactionKind.INCOME.value
TRANSFER = TransactionKind.TRANSFER.value

#: The four shapes money moves in, matching the tabs on the money dialog.
KINDS = (INCOME, EXPENSE, TRANSFER, DEPOSIT)


class RecurringBase(BaseModel):
    """Fields shared by a standing instruction's create body and its response.

    Attributes:
        kind: "income", "expense", "transfer" or "deposit" (income split across
            accounts by income share).
        amount: The magnitude in dollars, above 0; the sign is applied when each
            payment is written.
        description: Up to 200 characters.
        account_id: The account it comes from or lands in; required, except for a
            deposit, which must leave it empty.
        to_account_id: Where a transfer goes; required for a transfer, refused
            otherwise, and not the same as `account_id`.
        category_id: What an expense is spent on; refused on any other kind.
        starts_on: The first date of the series, which anchors the rule.
        recurrence: The repeat rule.
        active: False pauses it: nothing is written or projected.
    """

    kind: TransactionKind | str = Field(..., description="income | expense | transfer | deposit")
    #: Always positive, like a one-off. The service applies the sign.
    amount: float = Field(..., gt=0)
    description: str | None = Field(default=None, max_length=200)
    #: The pot it comes from or lands in. Null only for a deposit, which splits
    #: across accounts by income share instead of naming one.
    account_id: UUID | None = None
    #: Transfers only.
    to_account_id: UUID | None = None
    #: Expenses only.
    category_id: UUID | None = None
    starts_on: date
    recurrence: Recurrence
    active: bool = True

    @model_validator(mode="after")
    def validate_rule(self):
        """Check the kind and that each account and category field suits it.

        Returns:
            The model, with `kind` normalised to its string value.

        Raises:
            ValueError: If the kind is unknown, the account fields do not fit the
                kind, a category is set on anything but an expense, or the rule's
                `until` is before `starts_on`.
        """
        kind = self.kind.value if isinstance(self.kind, TransactionKind) else str(self.kind)

        if kind not in KINDS:
            raise ValueError(f"A standing instruction must be one of: {', '.join(KINDS)}")

        # A deposit divides by income share across every account, so naming one
        # would be describing a different thing entirely.
        if kind == DEPOSIT:
            if self.account_id is not None:
                raise ValueError("A recurring deposit splits across accounts, so it takes no account")
        elif self.account_id is None:
            raise ValueError("This needs an account")

        if kind == TRANSFER:
            if self.to_account_id is None:
                raise ValueError("A transfer needs somewhere to go")
            if self.to_account_id == self.account_id:
                raise ValueError("A transfer needs two different accounts")
        elif self.to_account_id is not None:
            raise ValueError("Only a transfer has a destination account")

        # Matching the one-off rule: a category labels what money went on, which
        # only means anything for money going out.
        if kind != EXPENSE and self.category_id is not None:
            raise ValueError("Only an expense carries a spending category")

        if self.recurrence.until is not None and self.recurrence.until < self.starts_on:
            raise ValueError("A repeat cannot end before it starts")

        self.kind = kind
        return self


class RecurringCreate(RecurringBase):
    """Request body for creating a standing instruction: the fields of `RecurringBase`.

    The accounts and category named must be the user's.
    """

    pass


class RecurringUpdate(BaseModel):
    """Request body for editing a standing instruction; only fields sent change.

    The kind and accounts cannot change; payments already written are left alone.

    Attributes:
        amount: New magnitude for future payments, above 0.
        description: New description; null clears it.
        category_id: New category for an expense, one of the user's.
        starts_on: New first date of the series.
        recurrence: New repeat rule; null leaves the rule as it is.
        active: Pause (False) or resume (True).
    """

    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    starts_on: date | None = None
    recurrence: Recurrence | None = None
    #: Pausing rather than deleting keeps last term's spending explicable.
    active: bool | None = None


class RecurringTransaction(RecurringBase):
    """A standing instruction as the API returns it: the base fields plus these.

    Attributes:
        id: The instruction's id.
        skipped_dates: Payments cancelled one at a time, ascending.
        last_run_on: The latest date a payment has been written for; None if
            never.
        next_due_on: The first date from today, within 400 days, with no payment
            written yet; None when the rule has run out.
    """

    id: UUID = Field(default_factory=uuid4)
    skipped_dates: list[date] = Field(default_factory=list)
    #: The most recent date this has already been written for, or null if never.
    #: Lets the client say "last charged 1 September" without fetching the ledger.
    last_run_on: date | None = None
    #: The next date it is due, or null once the rule has run out.
    next_due_on: date | None = None

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class UpcomingCharge(BaseModel):
    """A payment a rule says is coming but has not been written; never a ledger row.

    Attributes:
        recurring_id: The instruction it comes from.
        on_date: The date it falls due.
        kind: The instruction's kind.
        amount: The magnitude, in dollars.
        signed_amount: Negative for an expense or transfer (money leaving
            `account_id`), positive for income and deposits.
        description: The instruction's description.
        account_id: The account it comes from or lands in; None for a deposit.
        account_name: That account's name.
        to_account_id: Where a transfer goes.
        category_id: An expense's category.
    """

    recurring_id: UUID
    on_date: date
    kind: str
    amount: float
    #: Negative for money leaving, matching how a stored transaction signs it, so
    #: a caller can sum projections and balances the same way.
    signed_amount: float
    description: str | None = None
    account_id: UUID | None = None
    account_name: str | None = None
    to_account_id: UUID | None = None
    category_id: UUID | None = None


class RecurringRun(BaseModel):
    """Response body for writing the standing-instruction payments that are due.

    Attributes:
        created: How many ledger rows this run wrote; 0 is the usual answer.
        transactions: The rows written, so the ledger on screen can update.
        skipped: One line per rule that could not run and why; the other rules
            still ran.
    """

    #: How many occurrences were written this time. Zero is the normal answer.
    created: int = 0
    #: The rows themselves, so the ledger on screen can be updated without a refetch.
    transactions: list[Transaction] = Field(default_factory=list)
    #: Rules that could not run, and why -- an account archived out from under a
    #: standing instruction, say. Reported rather than raised, so one broken rule
    #: does not stop the other five from being charged.
    skipped: list[str] = Field(default_factory=list)
