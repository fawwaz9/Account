"""Request and response bodies for ledger transactions: income, expenses, transfers.

A transaction is money that entered or left an account. Amounts arrive as
positive magnitudes and are stored signed by kind; responses carry both forms.
`transaction_service` reads and writes them.
"""

from datetime import date
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TransactionKind(str, Enum):
    """What a ledger row records: income, an expense, or one leg of a transfer."""

    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class TransactionBase(BaseModel):
    """Fields shared by the create bodies and the response.

    Attributes:
        amount: The magnitude in dollars, above 0; the service applies the sign
            from the kind.
        description: Up to 200 characters.
        occurred_on: The day the money moved.
    """

    #: Always positive here. The service applies the sign from the kind, so a
    #: caller cannot accidentally record an expense that increases a balance.
    amount: float = Field(..., gt=0)
    description: str | None = Field(default=None, max_length=200)
    occurred_on: date


class TransactionCreate(TransactionBase):
    """Request body for recording income or an expense on one account.

    Transfers have their own body and endpoint; a transfer kind here is refused.

    Attributes:
        kind: Income or expense.
        account_id: The account; one of the user's.
        category_id: What it was spent on; kept only on an expense and must be one
            of the user's categories.
        course_id: The course it was bought for; kept only on an expense and must
            be one of the user's courses.
    """

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
    """Request body for moving money between two of the user's accounts.

    Written as two rows tied by one `group_id`, in a single commit.

    Attributes:
        from_account_id: The account the money leaves.
        to_account_id: The account it enters; not the same account.
    """

    from_account_id: UUID
    to_account_id: UUID

    @model_validator(mode="after")
    def validate_transfer(self):
        """Refuse a transfer from an account to itself.

        Returns:
            The validated model.

        Raises:
            ValueError: If both accounts are the same.
        """
        if self.from_account_id == self.to_account_id:
            raise ValueError("A transfer needs two different accounts")
        return self


class TransactionUpdate(BaseModel):
    """Request body for editing a transaction; only the fields sent are changed.

    A transfer's other leg follows its amount, date and description; a deposit's
    other rows do not. A tuition payment's row refuses an amount edit here.

    Attributes:
        amount: New magnitude, above 0; the row keeps its direction.
        description: New description; null clears it.
        occurred_on: New date.
        category_id: New category, one of the user's; null clears it.
        course_id: New course, one of the user's; null clears it.
    """

    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=200)
    occurred_on: date | None = None
    category_id: UUID | None = None
    course_id: UUID | None = None


class Transaction(TransactionBase):
    """A ledger row as the API returns it: the base fields plus these.

    Attributes:
        id: The row's id.
        kind: Income, expense or transfer.
        account_id: The account it belongs to.
        signed_amount: As stored: positive into the account, negative out.
        group_id: Shared by a transfer's two legs or a deposit's rows; None
            otherwise.
        group_size: How many rows share the group; 1 when ungrouped. Computed on
            reads; write responses carry 1.
        category_id: What it was spent on.
        course_id: The course it was bought for.
        tuition_payment_id: The tuition payment that owns the row, so the client
            sends it to the tuition editor; set on list reads only.
    """

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
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True
