"""CSV import: preview, commit, undo (Phase 1 item 7, account-vision.md §13.1, §13.9)."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

#: A bank's export of a term is a few hundred rows. The cap is about mistakes,
#: not abuse: the wrong file, a whole spreadsheet.
MAX_CSV_CHARS = 1_000_000
MAX_ROWS = 3000


class ImportMapping(BaseModel):
    """Which column means what. Detected from the file, overridable by the person."""

    has_header: bool = True
    date: int = Field(..., ge=0)
    #: One or more columns, joined with spaces: RBC splits it in two.
    description: list[int] = Field(..., min_length=1)
    #: One signed amount column, or a debit/credit pair -- not both.
    amount: int | None = Field(default=None, ge=0)
    debit: int | None = Field(default=None, ge=0)
    credit: int | None = Field(default=None, ge=0)
    #: "mdy" or "dmy" for dates like 03/04/2026. Ignored for unambiguous formats.
    date_order: Literal["mdy", "dmy"] = "mdy"
    #: Flip every amount: a credit-card export lists purchases as positive.
    invert: bool = False


class PreviewRequest(BaseModel):
    account_id: UUID
    csv_text: str = Field(..., max_length=MAX_CSV_CHARS)
    #: Omit to have the columns detected.
    mapping: ImportMapping | None = None


class ImportRow(BaseModel):
    #: 1-based line in the file, which is how a commit names what to take.
    line: int
    on_date: date | None = None
    description: str = ""
    #: Signed: negative is money out of the account.
    amount: float | None = None
    #: new | duplicate | error
    status: str
    #: For a duplicate, the existing row it matches; for an error, why.
    duplicate_of: UUID | None = None
    reason: str | None = None


class ImportPreview(BaseModel):
    account_id: UUID
    mapping: ImportMapping
    #: The header cells, so a person can see what each column index is.
    columns: list[str] = Field(default_factory=list)
    #: True when every date could be read either way (03/04): the person should
    #: confirm which, because the guess decides every date in the file.
    date_order_assumed: bool = False
    rows: list[ImportRow] = Field(default_factory=list)
    new_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    money_in: float = 0.0
    money_out: float = 0.0


class CommitRequest(BaseModel):
    account_id: UUID
    csv_text: str = Field(..., max_length=MAX_CSV_CHARS)
    mapping: ImportMapping
    #: The lines to write. Re-parsed on the server from the same text and
    #: mapping, so what is written is what the preview showed, not what a client
    #: says the rows were.
    lines: list[int] = Field(..., min_length=1, max_length=MAX_ROWS)
    filename: str | None = Field(default=None, max_length=200)


class ImportSummary(BaseModel):
    id: UUID
    account_id: UUID
    account_name: str
    filename: str | None = None
    created_at: datetime
    #: Written at the time.
    row_count: int
    #: Still in the ledger now, which is what undo would remove.
    rows_remaining: int
    first_date: date | None = None
    last_date: date | None = None
    #: Recurring-charge candidates the subscription audit now sees, imported
    #: rows included. Only filled in on the commit's response.
    subscription_candidates: int | None = None
