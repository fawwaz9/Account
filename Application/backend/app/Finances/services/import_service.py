"""Service functions for bank CSV import: preview, commit and undo as one unit.

Nothing is written until the person confirms: the commit parses the same text
with the same mapping and writes only the lines named. A row matching one already
in the account (same amount within three days, and the same merchant or the same
day) is flagged as a duplicate and starts unticked. Every row an import writes
carries its id, so undo removes exactly those rows.
"""

import csv
import io
import re
import uuid
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import AccountModel, ImportModel, SpendCategoryModel, TransactionModel
from app.Finances.schemas.importing import (
    MAX_ROWS,
    CommitRequest,
    ImportMapping,
    ImportPreview,
    ImportRow,
    ImportSummary,
)
from app.Finances.services.categorize_service import Categorizer
from app.Finances.services.forecast_service import merchant_key
from app.Finances.services.subscription_service import find_subscriptions
from app.shared.money import money

#: How far apart a bank's posting date and a hand-entered date can be and still
#: be the same purchase.
DUPLICATE_WINDOW_DAYS = 3

NEW, DUPLICATE, ERROR = "new", "duplicate", "error"

_MONTHS = {
    name: number
    for number, names in enumerate(
        (("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")),
        start=1,
    )
    for name in names
}


# --- reading the file ------------------------------------------------------

def parse_table(text: str) -> list[list[str]]:
    """Parse CSV text into rows of trimmed cells, sniffing the delimiter.

    A leading byte-order mark is dropped, and rows with no content are skipped.

    Args:
        text: The uploaded CSV's contents.

    Returns:
        Non-empty rows, each a list of trimmed cell strings.
    """
    text = text.lstrip("﻿")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]
    return [row for row in rows if any(row)]


def parse_amount(value: str) -> float | None:
    """Parse a bank's amount cell into a signed float.

    Handles "$1,234.56", "(12.50)", "12.50-", "12.50 CR", "12,50" and currency codes.

    Args:
        value: The cell's text.

    Returns:
        The amount, negative for a debit; None when the cell is empty or not a
        number.
    """
    text = (value or "").strip().upper()
    if not text:
        return None
    negative = False
    if text.endswith("CR"):
        text = text[:-2].strip()
    elif text.endswith("DR"):
        text, negative = text[:-2].strip(), True
    if text.startswith("(") and text.endswith(")"):
        text, negative = text[1:-1], not negative
    if text.endswith("-"):
        text, negative = text[:-1], not negative
    text = text.replace("CAD", "").replace("USD", "").replace("$", "").replace(" ", "")
    if text.startswith("-"):
        text, negative = text[1:], not negative
    elif text.startswith("+"):
        text = text[1:]
    if re.fullmatch(r"\d+,\d{2}", text):  # a decimal comma, from a ';' file
        text = text.replace(",", ".")
    text = text.replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", text):
        return None
    amount = float(text)
    return -amount if negative else amount


def _year(value: str) -> int:
    """Return a year, reading a two-digit one as 20xx."""
    year = int(value)
    return year + 2000 if year < 100 else year


def parse_date(value: str, order: str = "mdy") -> date | None:
    """Parse a bank's date cell into a date.

    Reads ISO and compact dates, numeric day/month forms in the given order, and
    forms with a month name; a timestamp keeps only its date.

    Args:
        value: The cell's text.
        order: "mdy" or "dmy", for numeric dates like 03/04/2026.

    Returns:
        The date; None when it cannot be read or is not a real date.
    """
    text = (value or "").strip()
    if not text:
        return None
    if " " in text and re.match(r"\d{4}-\d{2}-\d{2} ", text):
        text = text.split(" ", 1)[0]  # a timestamp: the date part
    try:
        if m := re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", text):
            first, second = int(m[1]), int(m[2])
            month, day = (first, second) if order == "mdy" else (second, first)
            return date(_year(m[3]), month, day)
        words = re.findall(r"[A-Za-z]+|\d+", text)
        names = [w for w in words if w.lower() in _MONTHS]
        numbers = [w for w in words if w.isdigit()]
        if len(names) == 1 and len(numbers) == 2:
            # "Oct 05, 2026", "05-Oct-2026", "2026 Oct 05": the four-digit one
            # is the year; with none, day then year ("05 Oct 26").
            month = _MONTHS[names[0].lower()]
            if len(numbers[0]) == 4:
                year, day = numbers[0], numbers[1]
            else:
                day, year = numbers[0], numbers[1]
            return date(_year(year), month, int(day))
    except ValueError:
        return None
    return None


def date_order(values: list[str]) -> tuple[str, bool]:
    """Work out whether a file's numeric dates are month-first or day-first.

    Args:
        values: Date cells from the file.

    Returns:
        ("mdy" or "dmy", whether it was a guess). A first part over 12 settles
        day-first and a second part over 12 month-first; when every date reads
        both ways the answer is "mdy" and a guess.
    """
    day_first = month_first = False
    for value in values:
        if m := re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", (value or "").strip()):
            if int(m[1]) > 12:
                day_first = True
            if int(m[2]) > 12:
                month_first = True
    if day_first and not month_first:
        return "dmy", False
    if month_first:
        return "mdy", False
    ambiguous = any(re.fullmatch(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", (v or "").strip()) for v in values)
    return "mdy", ambiguous


# --- which column is which -------------------------------------------------

_DATE_WORDS = ("date",)
_DESCRIPTION_WORDS = ("description", "details", "payee", "merchant", "memo", "narrative", "name")
_AMOUNT_WORDS = ("amount", "cad$", "cad")
_DEBIT_WORDS = ("debit", "withdraw", "money out", "paid out")
_CREDIT_WORDS = ("credit", "deposit", "money in", "paid in")


def _matching(header: list[str], words: tuple[str, ...], exclude: tuple[str, ...] = ()) -> list[int]:
    """Return the indexes of header cells holding any of the words and none excluded."""
    found = []
    for index, cell in enumerate(header):
        name = cell.lower()
        if any(word in name for word in words) and not any(word in name for word in exclude):
            found.append(index)
    return found


def _mostly(rows: list[list[str]], index: int, test) -> bool:
    """Return whether at least 80% of a column's non-empty cells pass a test."""
    values = [row[index] for row in rows if index < len(row) and row[index]]
    return bool(values) and sum(1 for v in values if test(v)) >= 0.8 * len(values)


def detect_mapping(rows: list[list[str]]) -> tuple[ImportMapping, list[str]]:
    """Guess which column is which, from a header when there is one, else from the data.

    Always returns a mapping; a column it cannot find is a plain guess the preview's
    errors will expose.

    Args:
        rows: The parsed rows, header included if any.

    Returns:
        The mapping, and the column labels (the header cells, or "Column N").
    """
    first = rows[0]
    has_header = not any(parse_date(cell) for cell in first) and any(
        re.search(r"[A-Za-z]", cell) for cell in first
    )
    body = rows[1:] if has_header else rows
    width = max(len(row) for row in rows)
    values = [row for row in body[:200]]
    order, _ = date_order([row[i] for row in values for i in range(len(row))])

    def is_date(v):
        """Return whether a cell reads as a date in the detected order."""
        return parse_date(v, order) is not None

    def is_amount(v):
        """Return whether a cell reads as an amount and not as a date."""
        return parse_amount(v) is not None and not is_date(v)

    columns = first if has_header else [f"Column {i + 1}" for i in range(width)]

    date_col = description_cols = amount_col = debit_col = credit_col = None
    if has_header:
        dates = _matching(first, _DATE_WORDS)
        date_col = dates[0] if dates else None
        description_cols = _matching(first, _DESCRIPTION_WORDS) or None
        amounts = _matching(first, _AMOUNT_WORDS, exclude=("balance",))
        amount_col = amounts[0] if amounts else None
        if amount_col is None:
            debits = _matching(first, _DEBIT_WORDS)
            credits = _matching(first, _CREDIT_WORDS)
            debit_col = debits[0] if debits else None
            credit_col = credits[0] if credits else None

    if date_col is None:
        date_col = next((i for i in range(width) if _mostly(values, i, is_date)), 0)
    numeric = [i for i in range(width) if i != date_col and _mostly(values, i, is_amount)]
    if description_cols is None:
        text_cols = [
            i for i in range(width)
            if i != date_col and i not in numeric and _mostly(values, i, lambda v: bool(re.search(r"[A-Za-z]", v)))
        ]
        description_cols = text_cols[:1] or [1 if width > 1 else 0]
    if amount_col is None and (debit_col is None or credit_col is None):
        # No header to go on. A debit/credit pair shows as two number columns
        # that are rarely both filled on one row (TD: date, payee, debit,
        # credit, balance); otherwise the first number column is the amount.
        pair = numeric[:2]
        if len(pair) == 2 and sum(
            1 for row in values if len(row) > pair[1] and row[pair[0]] and row[pair[1]]
        ) <= 0.1 * len(values):
            debit_col, credit_col = pair
        else:
            amount_col = numeric[0] if numeric else width - 1
            debit_col = credit_col = None

    mapping = ImportMapping(
        has_header=has_header, date=date_col, description=description_cols,
        amount=amount_col, debit=debit_col, credit=credit_col, date_order=order,
    )
    return mapping, columns


# --- rows, duplicates, the preview -----------------------------------------

def _cell(row: list[str], index: int | None) -> str:
    """Return a row's cell at an index, or "" when the index is None or past the row."""
    return row[index] if index is not None and index < len(row) else ""


def read_rows(rows: list[list[str]], mapping: ImportMapping) -> list[ImportRow]:
    """Read every data row through a mapping, marking the ones that cannot be imported.

    Args:
        rows: The parsed rows, header included if `mapping.has_header`.
        mapping: Which column means what.

    Returns:
        One row per data line with its 1-based line number, signed amount and
        status "new", or "error" with a reason for an unreadable date or amount
        or a zero amount.
    """
    out: list[ImportRow] = []
    start = 1 if mapping.has_header else 0
    for offset, row in enumerate(rows[start:]):
        line = offset + start + 1
        on_date = parse_date(_cell(row, mapping.date), mapping.date_order)
        description = " ".join(_cell(row, i) for i in mapping.description if _cell(row, i)).strip()
        if mapping.amount is not None:
            amount = parse_amount(_cell(row, mapping.amount))
        else:
            debit = parse_amount(_cell(row, mapping.debit))
            credit = parse_amount(_cell(row, mapping.credit))
            if debit is None and credit is None:
                amount = None
            else:
                amount = abs(credit or 0.0) - abs(debit or 0.0)
        if amount is not None and mapping.invert:
            amount = -amount

        reason = None
        if on_date is None:
            reason = f"Couldn't read a date from \"{_cell(row, mapping.date)}\""
        elif amount is None:
            reason = "Couldn't read an amount"
        elif money(amount) == 0:
            reason = "The amount is zero"
        out.append(ImportRow(
            line=line, on_date=on_date, description=description or "(no description)",
            amount=money(amount) if amount is not None else None,
            status=ERROR if reason else NEW, reason=reason,
        ))
    return out


def mark_duplicates(db: Session, user_id: uuid.UUID, account_id: uuid.UUID, rows: list[ImportRow]) -> None:
    """Flag new rows that match a transaction already in the account, in place.

    A match has the same amount (to the half cent), is within three days, and has
    the same merchant key or the same date; each existing transaction matches at
    most one row.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        account_id: The account being imported into.
        rows: The read rows; only "new" ones are checked.
    """
    candidates = [row for row in rows if row.status == NEW]
    if not candidates:
        return
    low = min(row.on_date for row in candidates) - timedelta(days=DUPLICATE_WINDOW_DAYS)
    high = max(row.on_date for row in candidates) + timedelta(days=DUPLICATE_WINDOW_DAYS)
    existing = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.account_id == account_id,
            TransactionModel.occurred_on >= low,
            TransactionModel.occurred_on <= high,
        )
        .all()
    )
    used: set[uuid.UUID] = set()
    for row in candidates:
        key = merchant_key(row.description)
        for txn in existing:
            if txn.id in used or abs(txn.amount - row.amount) >= 0.005:
                continue
            gap = abs((txn.occurred_on - row.on_date).days)
            if gap > DUPLICATE_WINDOW_DAYS:
                continue
            same_place = key and merchant_key(txn.description) == key
            if same_place or gap == 0:
                row.status, row.duplicate_of = DUPLICATE, txn.id
                row.reason = "Already in this account"
                used.add(txn.id)
                break


def owned_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> AccountModel | None:
    """Return the user's account with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        account_id: The account to fetch.

    Returns:
        The account, or None when it is missing or another user's.
    """
    return (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )


def preview(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID, csv_text: str, mapping: ImportMapping | None,
) -> ImportPreview | None:
    """Return everything a commit would write, without writing anything.

    Detects the mapping unless one is given (a debt account's amounts are inverted
    by default), flags duplicates and suggests categories for expenses.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        account_id: The account to import into.
        csv_text: The file's text.
        mapping: The mapping to use; None to detect it.

    Returns:
        The preview; None when the account is not the user's.

    Raises:
        ValueError: If the file has no rows or more than `MAX_ROWS` data rows.
    """
    account = owned_account(db, user_id, account_id)
    if account is None:
        return None
    rows = parse_table(csv_text)
    if not rows:
        raise ValueError("The file has no rows")
    if len(rows) > MAX_ROWS + 1:
        raise ValueError(f"The file has more than {MAX_ROWS} rows; split it and import each part")

    detected, columns = detect_mapping(rows)
    if account.kind == "debt":
        # A card's export lists purchases as positive and payments as negative;
        # here a purchase is an expense. Overridable like every other guess.
        detected.invert = True
    used = mapping or detected
    _, assumed = date_order([_cell(r, used.date) for r in rows[(1 if used.has_header else 0):]])
    if mapping is not None:
        columns = rows[0] if mapping.has_header else [f"Column {i + 1}" for i in range(max(map(len, rows)))]

    parsed = read_rows(rows, used)
    mark_duplicates(db, user_id, account_id, parsed)
    categorizer = Categorizer(db, user_id)
    for row in parsed:
        if row.status != ERROR and row.amount is not None and row.amount < 0:
            suggestion = categorizer.suggest(row.description)
            row.category_id, row.category_source = suggestion.category_id, suggestion.source
    fresh = [row for row in parsed if row.status == NEW]
    return ImportPreview(
        account_id=account_id,
        mapping=used,
        columns=columns,
        date_order_assumed=assumed and mapping is None,
        rows=parsed,
        new_count=len(fresh),
        duplicate_count=sum(1 for row in parsed if row.status == DUPLICATE),
        error_count=sum(1 for row in parsed if row.status == ERROR),
        money_in=money(sum(row.amount for row in fresh if row.amount > 0)),
        money_out=money(-sum(row.amount for row in fresh if row.amount < 0)),
    )


# --- commit, list, undo ----------------------------------------------------

def commit(db: Session, user_id: uuid.UUID, data: CommitRequest) -> ImportSummary | None:
    """Write the chosen lines of a CSV file into the ledger as one import.

    The file is previewed again with the same mapping, and only the lines named are
    written: negative amounts as expenses (with any confirmed category), positive as
    income. One commit.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        data: The text, mapping, lines, filename and confirmed categories.

    Returns:
        The import's summary, with how many subscription candidates the audit now
        sees; None when the account is not the user's.

    Raises:
        ValueError: If a line is not in the file or could not be read, or a
            category is not one of the user's unarchived categories.
    """
    shown = preview(db, user_id, data.account_id, data.csv_text, data.mapping)
    if shown is None:
        return None
    by_line = {row.line: row for row in shown.rows}
    wanted = sorted(set(data.lines))
    missing = [line for line in wanted if line not in by_line]
    if missing:
        raise ValueError(f"Line {missing[0]} is not in the file")
    unreadable = [line for line in wanted if by_line[line].status == ERROR]
    if unreadable:
        raise ValueError(f"Line {unreadable[0]} couldn't be read: {by_line[unreadable[0]].reason}")

    chosen = {line: category for line, category in data.categories.items() if category is not None}
    if chosen:
        allowed = {
            row.id for row in db.query(SpendCategoryModel.id).filter(
                SpendCategoryModel.user_id == user_id, SpendCategoryModel.archived.is_(False),
            )
        }
        foreign = [line for line, category in chosen.items() if category not in allowed]
        if foreign:
            raise ValueError(f"Line {foreign[0]}: that category does not exist")

    record = ImportModel(
        id=uuid.uuid4(), user_id=user_id, account_id=data.account_id,
        filename=data.filename, row_count=len(wanted),
    )
    db.add(record)
    for line in wanted:
        row = by_line[line]
        expense = row.amount < 0
        db.add(TransactionModel(
            id=uuid.uuid4(), user_id=user_id, account_id=data.account_id,
            kind="expense" if expense else "income",
            amount=row.amount, description=row.description[:200], occurred_on=row.on_date,
            # A category only labels money going out, as everywhere else.
            category_id=chosen.get(line) if expense else None,
            import_id=record.id,
        ))
    db.commit()

    [summary] = summaries(db, user_id, only=record.id)
    summary.subscription_candidates = len(find_subscriptions(db, user_id) or [])
    return summary


def summaries(db: Session, user_id: uuid.UUID, only: uuid.UUID | None = None) -> list[ImportSummary]:
    """Return the user's imports, newest first, with what is left of each.

    Args:
        db: Open database session.
        user_id: Whose imports.
        only: Just this import; None for all.

    Returns:
        Each import with its remaining row count and date span; empty when there
        are none.
    """
    query = (
        db.query(ImportModel, AccountModel.name)
        .join(AccountModel, AccountModel.id == ImportModel.account_id)
        .filter(ImportModel.user_id == user_id)
    )
    if only is not None:
        query = query.filter(ImportModel.id == only)
    records = query.order_by(ImportModel.created_at.desc()).all()
    if not records:
        return []

    spans = {
        row.import_id: row
        for row in db.query(
            TransactionModel.import_id,
            func.count(TransactionModel.id).label("remaining"),
            func.min(TransactionModel.occurred_on).label("first"),
            func.max(TransactionModel.occurred_on).label("last"),
        )
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.import_id.in_([record.id for record, _ in records]),
        )
        .group_by(TransactionModel.import_id)
        .all()
    }
    out = []
    for record, account_name in records:
        span = spans.get(record.id)
        out.append(ImportSummary(
            id=record.id, account_id=record.account_id, account_name=account_name,
            filename=record.filename, created_at=record.created_at, row_count=record.row_count,
            rows_remaining=span.remaining if span else 0,
            first_date=span.first if span else None, last_date=span.last if span else None,
        ))
    return out


def undo(db: Session, user_id: uuid.UUID, import_id: uuid.UUID) -> int | None:
    """Delete every row an import wrote, and the import itself.

    The rows are counted before and after one literal delete; a mismatch rolls back.
    Commits.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        import_id: The import.

    Returns:
        How many rows were removed; None when the import is not the user's.

    Raises:
        RuntimeError: If the delete removed a different number of rows than
            expected; nothing is changed.
    """
    record = (
        db.query(ImportModel)
        .filter(ImportModel.id == import_id, ImportModel.user_id == user_id)
        .first()
    )
    if record is None:
        return None

    expected = (
        db.query(func.count(TransactionModel.id))
        .filter(TransactionModel.user_id == user_id, TransactionModel.import_id == import_id)
        .scalar()
    )
    removed = (
        db.query(TransactionModel)
        .filter(TransactionModel.user_id == user_id, TransactionModel.import_id == import_id)
        .delete(synchronize_session=False)
    )
    if removed != expected:
        db.rollback()
        raise RuntimeError(f"Undo would have removed {removed} rows, expected {expected}; nothing was changed")
    db.query(ImportModel).filter(
        ImportModel.id == import_id, ImportModel.user_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return removed
