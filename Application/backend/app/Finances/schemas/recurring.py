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
    """A standing instruction, in any of the four shapes money moves in."""

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
    pass


class RecurringUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    starts_on: date | None = None
    recurrence: Recurrence | None = None
    #: Pausing rather than deleting keeps last term's spending explicable.
    active: bool | None = None


class RecurringTransaction(RecurringBase):
    id: UUID = Field(default_factory=uuid4)
    skipped_dates: list[date] = Field(default_factory=list)
    #: The most recent date this has already been written for, or null if never.
    #: Lets the client say "last charged 1 September" without fetching the ledger.
    last_run_on: date | None = None
    #: The next date it is due, or null once the rule has run out.
    next_due_on: date | None = None

    class Config:
        from_attributes = True


class UpcomingCharge(BaseModel):
    """A payment the rule says is coming but that has not happened yet.

    Never a transaction row: it has not moved any money, and writing it as one
    would make a balance report money that is still in the account as gone.
    This is what "what am I already committed to" reads.
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
    """What materialising due payments actually did."""

    #: How many occurrences were written this time. Zero is the normal answer.
    created: int = 0
    #: The rows themselves, so the ledger on screen can be updated without a refetch.
    transactions: list[Transaction] = Field(default_factory=list)
    #: Rules that could not run, and why -- an account archived out from under a
    #: standing instruction, say. Reported rather than raised, so one broken rule
    #: does not stop the other five from being charged.
    skipped: list[str] = Field(default_factory=list)
