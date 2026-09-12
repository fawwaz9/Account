from datetime import date
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TransactionKind(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class TransactionBase(BaseModel):
    #: Always positive here. The service applies the sign from the kind, so a
    #: caller cannot accidentally record an expense that increases a balance.
    amount: float = Field(..., gt=0)
    description: str | None = Field(default=None, max_length=200)
    occurred_on: date


class TransactionCreate(TransactionBase):
    kind: TransactionKind
    account_id: UUID
    #: Only meaningful for expenses; ignored on income.
    category_id: UUID | None = None
    #: What the money was bought for -- a textbook, a lab manual. Expense-only
    #: for the same reason a category is. Tuition never sets this: one payment
    #: covers a whole term, and what it cost each course is answered from the
    #: per-credit rate rather than from the ledger.
    course_id: UUID | None = None


class TransferCreate(TransactionBase):
    from_account_id: UUID
    to_account_id: UUID

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.from_account_id == self.to_account_id:
            raise ValueError("A transfer needs two different accounts")
        return self


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=200)
    occurred_on: date | None = None
    category_id: UUID | None = None
    course_id: UUID | None = None


class Transaction(TransactionBase):
    id: UUID = Field(default_factory=uuid4)
    kind: TransactionKind
    account_id: UUID
    #: Signed as stored: positive into the account, negative out of it.
    signed_amount: float = 0.0
    #: Present on both halves of a transfer, tying them together.
    group_id: UUID | None = None
    #: How many rows share this group, so a caller can tell a split deposit from
    #: a single allocation without fetching the siblings. 1 when ungrouped.
    group_size: int = 1
    category_id: UUID | None = None
    course_id: UUID | None = None
    #: Set when a tuition payment owns this row. The client sends such a
    #: row to the tuition editor instead of the plain one, because editing
    #: the amount directly would leave the rate and the ledger disagreeing.
    tuition_payment_id: UUID | None = None

    class Config:
        from_attributes = True
