from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class AccountKind(str, Enum):
    SPENDING = "spending"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    EMERGENCY = "emergency"
    OTHER = "other"


#: Seeded for a new account holder. The first four come from the project notes
#: and carry the income split; School and Money Lent start at 0% so adding them
#: does not quietly take a cut from the others.
DEFAULT_ACCOUNTS: list[tuple[str, AccountKind, float]] = [
    ("Spending", AccountKind.SPENDING, 50.0),
    ("Savings", AccountKind.SAVINGS, 20.0),
    ("Investments", AccountKind.INVESTMENT, 20.0),
    ("Emergency Savings", AccountKind.EMERGENCY, 10.0),
    ("School", AccountKind.OTHER, 0.0),
    ("Money Lent", AccountKind.OTHER, 0.0),
]


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    kind: AccountKind = Field(default=AccountKind.SPENDING)
    income_share: float = Field(default=0.0, ge=0, le=100, description="Default share of income, percent")
    archived: bool = Field(default=False)
    position: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_account(self):
        if self.name.strip() == "":
            raise ValueError("Account name cannot be empty")
        return self


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: AccountKind | None = None
    income_share: float | None = Field(default=None, ge=0, le=100)
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)


class Account(AccountBase):
    id: UUID = Field(default_factory=uuid4)
    #: Sum of the account's transactions. Derived rather than stored: a balance
    #: that disagrees with its own ledger is worse than one that costs a query.
    balance: float = 0.0

    class Config:
        from_attributes = True
