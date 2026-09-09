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


class Transaction(TransactionBase):
    id: UUID = Field(default_factory=uuid4)
    kind: TransactionKind
    account_id: UUID
    #: Signed as stored: positive into the account, negative out of it.
    signed_amount: float = 0.0
    #: Present on both halves of a transfer, tying them together.
    group_id: UUID | None = None

    class Config:
        from_attributes = True
