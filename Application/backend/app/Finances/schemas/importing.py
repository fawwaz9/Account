"""Request and response bodies for bank CSV import: preview, commit and undo.

Nothing is written until the person confirms: the commit re-parses the same text
with the same mapping and writes only the lines named. `import_service` does the
work, and every row it writes carries the import's id so the import undoes as
one unit.
"""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

#: A bank's export of a term is a few hundred rows. The cap is about mistakes,
#: not abuse: the wrong file, a whole spreadsheet.
MAX_CSV_CHARS = 1_000_000
MAX_ROWS = 3000
"""Most data rows one file may hold, and the most lines one commit may name."""


class ImportMapping(BaseModel):
    """Which column of the file means what; detected from the file, overridable.

    Attributes:
        has_header: Whether the first row is a header.
        date: Index of the date column, from 0.
        description: Indexes of the columns joined with spaces into the
            description; at least one.
        amount: Index of a single signed amount column; None when a debit and
            credit pair is used instead.
        debit: Index of the money-out column of a pair.
        credit: Index of the money-in column of a pair.
        date_order: "mdy" or "dmy", for dates such as 03/04/2026; ignored for
            unambiguous formats.
        invert: Flip every amount's sign, for exports that list purchases as
            positive; the detected default for a debt account.
    """

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
    """Request body for previewing a CSV import.

    Attributes:
        account_id: The account to import into; one of the user's.
        csv_text: The file's text, up to 1,000,000 characters and 3000 data rows.
        mapping: The column mapping to use; omit to have it detected.
    """

    account_id: UUID
    csv_text: str = Field(..., max_length=MAX_CSV_CHARS)
    #: Omit to have the columns detected.
    mapping: ImportMapping | None = None


class ImportRow(BaseModel):
    """One line of the file as the import reads it.

    Attributes:
        line: The 1-based line in the file, which is how a commit names it.
        on_date: The date read; None when it could not be read.
        description: The joined description columns, or "(no description)".
        amount: Signed amount in dollars, negative for money out; None when it
            could not be read.
        status: "new"; "duplicate" when it matches a row already in the account,
            so it starts unticked; or "error" when it cannot be imported.
        duplicate_of: The existing transaction a duplicate matches.
        reason: Why a row is a duplicate or an error.
        category_id: A suggested category for an expense; None to ask.
        category_source: Where the suggestion came from: "learned", "shared", "rule" or
            "bayes".
    """

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
    #: A suggested category for an expense (Phase 1 item 8), or null to ask.
    category_id: UUID | None = None
    #: learned | rule | bayes -- where the suggestion came from.
    category_source: str | None = None


class ImportPreview(BaseModel):
    """Everything a commit would write, worked out without writing anything.

    Attributes:
        account_id: The account being imported into.
        mapping: The mapping used, given or detected.
        columns: The header cells, or "Column N" names when there is no header.
        date_order_assumed: True when every date read both ways and the order was
            guessed, so the person should confirm it.
        rows: Every data line, read.
        new_count: Rows with status "new".
        duplicate_count: Rows with status "duplicate".
        error_count: Rows with status "error".
        money_in: The new rows' positive amounts, summed.
        money_out: The new rows' negative amounts, summed, as a positive figure.
    """

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
    """Request body for writing chosen lines of a CSV file into the ledger.

    The server parses `csv_text` again with `mapping`, so what is written is what
    the preview showed, never rows the client describes.

    Attributes:
        account_id: The account to import into; one of the user's.
        csv_text: The same text the preview read.
        mapping: The mapping the preview used.
        lines: The 1-based lines to write, 1-3000 of them; none may be an error.
        filename: The file's name as the browser gave it, up to 200 characters.
        categories: Line number to category for expense lines, as confirmed in the
            preview (JSON keys are strings); a line left out or mapped to null is
            written uncategorised.
    """

    account_id: UUID
    csv_text: str = Field(..., max_length=MAX_CSV_CHARS)
    mapping: ImportMapping
    #: The lines to write. Re-parsed on the server from the same text and
    #: mapping, so what is written is what the preview showed, not what a client
    #: says the rows were.
    lines: list[int] = Field(..., min_length=1, max_length=MAX_ROWS)
    filename: str | None = Field(default=None, max_length=200)
    #: Line -> category for the expenses, as confirmed in the preview. Keys are
    #: line numbers as strings, since JSON objects key by string. A line left
    #: out is written uncategorised; the server never applies a suggestion the
    #: person did not keep.
    categories: dict[int, UUID | None] = Field(default_factory=dict)


class ImportSummary(BaseModel):
    """One past import, and how much of it is still in the ledger.

    Attributes:
        id: The import's id.
        account_id: The account it went into.
        account_name: That account's name.
        filename: The file's name, if given.
        created_at: When it was imported, naive UTC.
        row_count: Rows written at the time.
        rows_remaining: Its rows still in the ledger, which undo would remove.
        first_date: Date of the earliest remaining row; None when none remain.
        last_date: Date of the latest remaining row; None when none remain.
        subscription_candidates: Repeating charges the subscription audit finds
            after this import; set only on the commit's response.
    """

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
