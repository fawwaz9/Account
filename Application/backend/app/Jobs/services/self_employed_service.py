"""Self-employed support: clients, invoices, business expenses, and the CRA rules (item 15).

§13.12. The jobs module assumes an employer; self-employment has invoices instead
of paycheques and nothing withheld. This keeps it small, short of an accounting
product:

- **Clients** carry a name; **invoices** carry a client, a number, dates and an
  amount. An invoice's state is read from its dates: paid once paid, overdue
  when unpaid past due, outstanding otherwise.
- **Revenue counts by issue date**, the day the work was billed, for both the
  year's figures and the GST/HST watch; payments are reported beside it.
- **Business expenses** are ledger expenses tagged with a business share
  (`transactions.business_percent`); a phone used half for work is 50.
- **CPP** on net self-employment income at both halves, after the gross pay
  recorded from jobs that year has used the exemption and the ceilings first.
- **Instalments**: the $3,000 rule and the four dates, without estimating
  anyone's income tax, which needs a whole return (D25).
- **GST/HST**: invoiced revenue over the last four calendar quarters, the
  current one to date, against $30,000.

Tax information with its sources, never advice. Money only: nothing here reads
or feeds an academic figure.
"""
import re
import statistics
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app._database.models import ClientModel, InvoiceModel, PaychequeModel, TransactionModel
from app.Finances.schemas.transaction import TransactionKind
from app.Finances.services.deposit_service import active_accounts, split_income
from app.Finances.services.transaction_service import owned_account
from app.Jobs.schemas.self_employed import (
    BusinessExpense, Client, ClientIn, ClientUpdate, CppEstimate, GstWatch, IncomeRange, Instalments, Invoice,
    InvoiceIn, InvoiceUpdate, PaidIn, QuarterTotal, SelfEmployment, Source,
)
from app.Jobs.services.paycheque_service import clear_deposit
from app.shared.dates import user_for, user_today
from app.shared.money import money

#: Days to pay when an invoice names no due date.
DEFAULT_TERMS_DAYS = 30

#: CPP figures by year: (maximum pensionable earnings, second earnings ceiling).
#: From the CRA's "CPP contribution rates, maximums and exemptions" page; a newer
#: year uses the latest row and says so.
CPP_CEILINGS = {2024: (68_500.0, 73_200.0), 2025: (71_300.0, 81_200.0), 2026: (74_600.0, 85_000.0)}
CPP_EXEMPTION = 3_500.0
#: Both halves of the base rate (5.95% each), and of CPP2 (4% each).
CPP_SELF_RATE = 0.119
CPP2_SELF_RATE = 0.08

#: Net tax owing above this, this year and in either of the two before, means
#: quarterly instalments ($1,800 in Quebec).
INSTALMENT_THRESHOLD = 3_000.0
INSTALMENT_DAYS = ((3, 15), (6, 15), (9, 15), (12, 15))

#: The small-supplier line: worldwide taxable revenue over four consecutive
#: calendar quarters, or in any one of them.
GST_THRESHOLD = 30_000.0
#: "Approaching" from this share of the threshold.
GST_APPROACHING = 0.8

#: The typical-month range reads up to this many finished months, and needs at least the minimum.
RANGE_MONTHS = 6
RANGE_MIN_MONTHS = 3

SOURCES = [
    Source(label="CRA: CPP contribution rates, maximums and exemptions",
           url="https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/payroll/"
               "payroll-deductions-contributions/canada-pension-plan-cpp/cpp-contribution-rates-maximums-exemptions.html"),
    Source(label="CRA: Who has to pay instalments",
           url="https://www.canada.ca/en/revenue-agency/services/payments/payments-cra/individual-payments/"
               "income-tax-instalments/who-pays-instalments.html"),
    Source(label="CRA: When to register for and start charging the GST/HST",
           url="https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/"
               "when-register-charge.html"),
]

NOTE = ("Tax information from what you've recorded, not tax advice. Nothing is withheld from an invoice, so "
        "tax and CPP on it come due when you file: the balance by April 30, though a self-employed return "
        "can be filed until June 15.")


class NoSuchClient(LookupError):
    """The client isn't one of the caller's."""


class NoSuchInvoice(LookupError):
    """The invoice isn't one of the caller's."""


class NoSuchAccount(LookupError):
    """The account isn't one of the caller's."""


# --- clients -----------------------------------------------------------------

def _owned_client(db: Session, user_id: uuid.UUID, client_id: uuid.UUID) -> ClientModel:
    client = db.query(ClientModel).filter(ClientModel.id == client_id, ClientModel.user_id == user_id).first()
    if client is None:
        raise NoSuchClient("Client not found")
    return client


def _client_schema(client: ClientModel, invoices: list[InvoiceModel]) -> Client:
    mine = [i for i in invoices if i.client_id == client.id]
    return Client(id=client.id, name=client.name, archived=client.archived, invoices=len(mine),
                  invoiced=money(sum(i.amount for i in mine)),
                  unpaid=money(sum(i.amount for i in mine if i.paid_on is None)))


def list_clients(db: Session, user_id: uuid.UUID) -> list[Client] | None:
    """Return the caller's clients, unarchived first, then by name; None for no such user."""
    if user_for(db, user_id) is None:
        return None
    clients = db.query(ClientModel).filter(ClientModel.user_id == user_id).all()
    invoices = db.query(InvoiceModel).filter(InvoiceModel.user_id == user_id).all()
    clients.sort(key=lambda c: (c.archived, c.name.lower()))
    return [_client_schema(c, invoices) for c in clients]


def create_client(db: Session, user_id: uuid.UUID, body: ClientIn) -> Client | None:
    """Add a client; None for no such user."""
    if user_for(db, user_id) is None:
        return None
    client = ClientModel(id=uuid.uuid4(), user_id=user_id, name=body.name.strip() or body.name)
    db.add(client)
    db.commit()
    return _client_schema(client, [])


def update_client(db: Session, user_id: uuid.UUID, client_id: uuid.UUID, body: ClientUpdate) -> Client:
    """Rename or archive one of the caller's clients.

    Raises:
        NoSuchClient: If it isn't theirs.
    """
    client = _owned_client(db, user_id, client_id)
    if body.name is not None:
        client.name = body.name.strip() or body.name
    if body.archived is not None:
        client.archived = body.archived
    db.commit()
    invoices = db.query(InvoiceModel).filter(InvoiceModel.user_id == user_id,
                                             InvoiceModel.client_id == client.id).all()
    return _client_schema(client, invoices)


def delete_client(db: Session, user_id: uuid.UUID, client_id: uuid.UUID) -> None:
    """Delete a client with no invoices.

    Raises:
        NoSuchClient: If it isn't theirs.
        ValueError: If it has invoices; archive it instead.
    """
    client = _owned_client(db, user_id, client_id)
    if db.query(InvoiceModel.id).filter(InvoiceModel.user_id == user_id,
                                        InvoiceModel.client_id == client.id).first() is not None:
        raise ValueError("This client has invoices. Archive them instead, so the invoices keep their name.")
    db.delete(client)
    db.commit()


# --- invoices ----------------------------------------------------------------

def invoice_state(invoice: InvoiceModel, today: date) -> tuple[str, int | None]:
    """Return an invoice's state and, when overdue, its days past due.

    Args:
        invoice: The row.
        today: The user's today.

    Returns:
        ("paid", None), ("overdue", days past due) or ("outstanding", None).
    """
    if invoice.paid_on is not None:
        return "paid", None
    if invoice.due_on < today:
        return "overdue", (today - invoice.due_on).days
    return "outstanding", None


def _invoice_schema(invoice: InvoiceModel, names: dict, today: date) -> Invoice:
    state, late = invoice_state(invoice, today)
    return Invoice(id=invoice.id, client_id=invoice.client_id, client=names.get(invoice.client_id, "A client"),
                   number=invoice.number, description=invoice.description, issued_on=invoice.issued_on,
                   due_on=invoice.due_on, amount=invoice.amount, paid_on=invoice.paid_on, state=state,
                   days_overdue=late, deposited=invoice.group_id is not None)


def _names(db: Session, user_id: uuid.UUID) -> dict:
    return {c.id: c.name for c in db.query(ClientModel).filter(ClientModel.user_id == user_id)}


def _owned_invoice(db: Session, user_id: uuid.UUID, invoice_id: uuid.UUID) -> InvoiceModel:
    invoice = db.query(InvoiceModel).filter(InvoiceModel.id == invoice_id, InvoiceModel.user_id == user_id).first()
    if invoice is None:
        raise NoSuchInvoice("Invoice not found")
    return invoice


def _number_taken(db: Session, user_id: uuid.UUID, number: str, other_than: uuid.UUID | None = None) -> bool:
    query = db.query(InvoiceModel.id).filter(InvoiceModel.user_id == user_id, InvoiceModel.number == number)
    if other_than is not None:
        query = query.filter(InvoiceModel.id != other_than)
    return query.first() is not None


def list_invoices(db: Session, user_id: uuid.UUID, today: date | None = None) -> list[Invoice] | None:
    """Return the caller's invoices, latest issued first; None for no such user."""
    if user_for(db, user_id) is None:
        return None
    today = today or user_today(db, user_id)
    names = _names(db, user_id)
    rows = (db.query(InvoiceModel).filter(InvoiceModel.user_id == user_id)
            .order_by(InvoiceModel.issued_on.desc(), InvoiceModel.number.desc()).all())
    return [_invoice_schema(row, names, today) for row in rows]


def create_invoice(db: Session, user_id: uuid.UUID, body: InvoiceIn, today: date | None = None) -> Invoice | None:
    """Record a new invoice; None for no such user.

    Raises:
        NoSuchClient: If the client isn't the caller's.
        ValueError: If the number is already used.
    """
    if user_for(db, user_id) is None:
        return None
    client = _owned_client(db, user_id, body.client_id)
    number = body.number.strip() or body.number
    if _number_taken(db, user_id, number):
        raise ValueError(f"You've already used invoice number {number}")
    invoice = InvoiceModel(id=uuid.uuid4(), user_id=user_id, client_id=client.id, number=number,
                           description=body.description, issued_on=body.issued_on,
                           due_on=body.due_on or body.issued_on + timedelta(days=DEFAULT_TERMS_DAYS),
                           amount=money(body.amount))
    db.add(invoice)
    _commit(db)
    return _invoice_schema(invoice, {client.id: client.name}, today or user_today(db, user_id))


def _commit(db: Session) -> None:
    """Commit, turning a lost race on the invoice number into the same refusal."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("You've already used that invoice number") from exc


def _deposit(db: Session, user_id: uuid.UUID, invoice: InvoiceModel, account_id: uuid.UUID | None,
             split: bool, names: dict) -> None:
    """Write the income row(s) a payment becomes, tied to the invoice by a new group."""
    if split:
        allocations = split_income(invoice.amount, active_accounts(db, user_id))
        if not allocations:
            raise ValueError("No account has an income share yet. Choose an account for this payment.")
        targets = [(a.account_id, a.amount) for a in allocations]
    elif account_id is not None:
        if owned_account(db, user_id, account_id) is None:
            raise NoSuchAccount("Account not found")
        targets = [(account_id, invoice.amount)]
    else:
        invoice.group_id = None
        return
    group_id = uuid.uuid4()
    for target, amount in targets:
        if amount > 0:
            db.add(TransactionModel(id=uuid.uuid4(), user_id=user_id, account_id=target,
                                    kind=TransactionKind.INCOME.value, amount=money(amount),
                                    description=f"Invoice {invoice.number}, {names.get(invoice.client_id, 'client')}",
                                    occurred_on=invoice.paid_on, group_id=group_id))
    invoice.group_id = group_id


def update_invoice(db: Session, user_id: uuid.UUID, invoice_id: uuid.UUID, body: InvoiceUpdate,
                   today: date | None = None) -> Invoice:
    """Correct an invoice. A paid one's single-account deposit follows a new amount.

    Raises:
        NoSuchInvoice: If it isn't the caller's.
        NoSuchClient: If a new client isn't theirs.
        ValueError: If the number is taken, or the dates would put it due before issue.
    """
    invoice = _owned_invoice(db, user_id, invoice_id)
    try:
        _apply_update(db, user_id, invoice, body.model_dump(exclude_unset=True))
    except (ValueError, LookupError):
        db.rollback()
        raise
    _commit(db)
    return _invoice_schema(invoice, _names(db, user_id), today or user_today(db, user_id))


def _apply_update(db: Session, user_id: uuid.UUID, invoice: InvoiceModel, sent: dict) -> None:
    """Apply an invoice patch in the session, uncommitted; raises as `update_invoice` does."""
    if sent.get("client_id") is not None:
        invoice.client_id = _owned_client(db, user_id, sent["client_id"]).id
    if sent.get("number") is not None:
        number = sent["number"].strip() or sent["number"]
        if _number_taken(db, user_id, number, other_than=invoice.id):
            raise ValueError(f"You've already used invoice number {number}")
        invoice.number = number
    if "description" in sent:
        invoice.description = sent["description"]
    if sent.get("issued_on") is not None:
        invoice.issued_on = sent["issued_on"]
    if sent.get("due_on") is not None:
        invoice.due_on = sent["due_on"]
    if invoice.due_on < invoice.issued_on:
        raise ValueError("An invoice can't be due before it was issued")
    if invoice.paid_on is not None and invoice.paid_on < invoice.issued_on:
        raise ValueError("An invoice can't be paid before it was issued")
    if sent.get("amount") is not None:
        invoice.amount = money(sent["amount"])
        if invoice.group_id is not None:
            rows = db.query(TransactionModel).filter(TransactionModel.user_id == user_id,
                                                     TransactionModel.group_id == invoice.group_id).all()
            # One row moves with the amount; a split is written again by income share;
            # rows already deleted from the ledger leave nothing to follow.
            if not rows:
                invoice.group_id = None
            elif len(rows) == 1:
                rows[0].amount = invoice.amount
            else:
                clear_deposit(db, user_id, invoice.group_id)
                _deposit(db, user_id, invoice, None, True, _names(db, user_id))


def mark_paid(db: Session, user_id: uuid.UUID, invoice_id: uuid.UUID, body: PaidIn,
              today: date | None = None) -> Invoice:
    """Mark an invoice paid, optionally recording the payment in the ledger.

    Marking an already-paid invoice again replaces its payment and its deposit.

    Raises:
        NoSuchInvoice: If it isn't the caller's.
        NoSuchAccount: If the account isn't theirs.
        ValueError: If paid before it was issued, or a split has no income shares.
    """
    invoice = _owned_invoice(db, user_id, invoice_id)
    if body.paid_on < invoice.issued_on:
        raise ValueError("An invoice can't be paid before it was issued")
    names = _names(db, user_id)
    clear_deposit(db, user_id, invoice.group_id)
    invoice.paid_on = body.paid_on
    try:
        _deposit(db, user_id, invoice, body.account_id, body.split, names)
    except (ValueError, LookupError):
        db.rollback()
        raise
    db.commit()
    return _invoice_schema(invoice, names, today or user_today(db, user_id))


def mark_unpaid(db: Session, user_id: uuid.UUID, invoice_id: uuid.UUID, today: date | None = None) -> Invoice:
    """Undo a payment: the invoice is unpaid again and its deposit is deleted.

    Raises:
        NoSuchInvoice: If it isn't the caller's.
    """
    invoice = _owned_invoice(db, user_id, invoice_id)
    clear_deposit(db, user_id, invoice.group_id)
    invoice.paid_on, invoice.group_id = None, None
    db.commit()
    return _invoice_schema(invoice, _names(db, user_id), today or user_today(db, user_id))


def delete_invoice(db: Session, user_id: uuid.UUID, invoice_id: uuid.UUID) -> None:
    """Delete an invoice and any deposit its payment wrote.

    Raises:
        NoSuchInvoice: If it isn't the caller's.
    """
    invoice = _owned_invoice(db, user_id, invoice_id)
    clear_deposit(db, user_id, invoice.group_id)
    db.delete(invoice)
    db.commit()


# --- the year's figures --------------------------------------------------------

def cpp_estimate(net: float, employment_gross: float, year: int) -> CppEstimate:
    """Return CPP on net self-employment income, both halves, after a job's pay.

    Employment earnings use the basic exemption and the ceilings first; the
    self-employment income is then charged 11.9% up to the first ceiling and 8%
    between the two. Proration for a part year is left out.

    Args:
        net: Net self-employment income for the year (a loss counts as 0).
        employment_gross: Gross pay recorded from jobs that year.
        year: The calendar year.

    Returns:
        The estimate and the figures it used.
    """
    known = sorted(CPP_CEILINGS)
    figures_year = max((y for y in known if y <= year), default=known[0])
    ceiling, second_ceiling = CPP_CEILINGS[figures_year]
    net = max(0.0, net)
    employment = max(0.0, employment_gross)
    exemption_left = max(0.0, CPP_EXEMPTION - employment)
    in_first = min(net, max(0.0, ceiling - employment))
    base_earnings = max(0.0, in_first - exemption_left)
    top = min(employment + net, second_ceiling)
    second_earnings = max(0.0, top - max(employment, ceiling))
    base = money(base_earnings * CPP_SELF_RATE)
    second = money(second_earnings * CPP2_SELF_RATE)
    return CppEstimate(figures_year=figures_year, rate=round(CPP_SELF_RATE * 100, 2), exemption=CPP_EXEMPTION,
                       ceiling=ceiling, second_rate=round(CPP2_SELF_RATE * 100, 2), second_ceiling=second_ceiling,
                       employment_gross=money(employment), base=base, second=second, total=money(base + second))


def instalments(year: int, today: date) -> Instalments:
    """Return the instalment rule's threshold, the year's four dates and the next one."""
    dates = [date(year, month, day) for month, day in INSTALMENT_DAYS]
    upcoming = [d for d in dates if d >= today]
    return Instalments(threshold=INSTALMENT_THRESHOLD, dates=dates, next_due=upcoming[0] if upcoming else None)


def _quarter_start(day: date) -> date:
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _previous_quarter(start: date) -> date:
    return date(start.year - 1, 10, 1) if start.month == 1 else date(start.year, start.month - 3, 1)


QUARTER_LABELS = {1: "Jan-Mar", 4: "Apr-Jun", 7: "Jul-Sep", 10: "Oct-Dec"}


def gst_watch(invoices: list[InvoiceModel], today: date) -> GstWatch:
    """Return invoiced revenue over the last four calendar quarters against $30,000.

    Args:
        invoices: The user's invoices.
        today: The user's today; its quarter counts to date.

    Returns:
        The four quarters, oldest first, their sum and the level.
    """
    starts = [_quarter_start(today)]
    for _ in range(3):
        starts.append(_previous_quarter(starts[-1]))
    starts.reverse()
    totals = defaultdict(float)
    for invoice in invoices:
        if starts[0] <= invoice.issued_on <= today:
            totals[_quarter_start(invoice.issued_on)] += invoice.amount
    quarters = [QuarterTotal(label=f"{QUARTER_LABELS[s.month]} {s.year}", starts_on=s, total=money(totals[s]))
                for s in starts]
    four = money(sum(q.total for q in quarters))
    # One quarter over the line is the four quarters over it too (amounts are
    # positive), so one test covers both of CRA's; they differ only in when
    # registration takes effect.
    if four > GST_THRESHOLD:
        level = "over"
    elif four >= GST_THRESHOLD * GST_APPROACHING:
        level = "approaching"
    else:
        level = "under"
    return GstWatch(threshold=GST_THRESHOLD, quarters=quarters, four_quarter_total=four, level=level)


def typical_month(invoices: list[InvoiceModel], today: date) -> IncomeRange | None:
    """Return recent monthly revenue as a quartile range; None under three finished months.

    Reads the finished months since the first invoice, up to the last six, each by
    issue date; a month with no invoice counts as $0.
    """
    if not invoices:
        return None
    first = min(i.issued_on for i in invoices).replace(day=1)
    this_month = today.replace(day=1)
    months = []
    cursor = this_month
    while len(months) < RANGE_MONTHS:
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        if cursor < first:
            break
        months.append(cursor)
    if len(months) < RANGE_MIN_MONTHS:
        return None
    totals = defaultdict(float)
    for invoice in invoices:
        totals[invoice.issued_on.replace(day=1)] += invoice.amount
    values = sorted(totals[m] for m in months)
    low, _, high = statistics.quantiles(values, n=4, method="inclusive")
    return IncomeRange(low=money(low), high=money(high), months=len(months))


def next_number(invoices: list[InvoiceModel]) -> str:
    """Suggest the next invoice number: the highest number's digits plus one, padded alike."""
    best = None
    for invoice in invoices:
        found = re.search(r"(\d+)(?!.*\d)", invoice.number)
        if found and (best is None or int(found.group(1)) > best[0]):
            best = (int(found.group(1)), invoice.number, found)
    if best is None:
        return "INV-001"
    value, number, found = best
    digits = str(value + 1).zfill(len(found.group(1)))
    return number[:found.start(1)] + digits + number[found.end(1):]


def business_expenses(db: Session, user_id: uuid.UUID, first: date, last: date) -> list[BusinessExpense]:
    """Return the tagged expenses between two dates, newest first."""
    rows = (db.query(TransactionModel)
            .filter(TransactionModel.user_id == user_id, TransactionModel.kind == TransactionKind.EXPENSE.value,
                    TransactionModel.business_percent.isnot(None), TransactionModel.occurred_on >= first,
                    TransactionModel.occurred_on <= last)
            .order_by(TransactionModel.occurred_on.desc()).all())
    return [BusinessExpense(transaction_id=row.id, occurred_on=row.occurred_on, description=row.description,
                            amount=money(abs(row.amount)), percent=row.business_percent,
                            business_amount=money(abs(row.amount) * row.business_percent / 100))
            for row in rows]


def year_totals(db: Session, user_id: uuid.UUID, year: int) -> tuple[float, float, list[BusinessExpense]]:
    """Return a year's invoiced revenue, business expenses and the tagged expenses."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    revenue = sum(amount for (amount,) in db.query(InvoiceModel.amount).filter(
        InvoiceModel.user_id == user_id, InvoiceModel.issued_on >= first, InvoiceModel.issued_on <= last))
    expenses = business_expenses(db, user_id, first, last)
    return money(revenue), money(sum(e.business_amount for e in expenses)), expenses


def self_employment(db: Session, user_id: uuid.UUID, year: int | None = None,
                    today: date | None = None) -> SelfEmployment | None:
    """Return a year of self-employment and the CRA rules read against it.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        year: The calendar year; omitted, this one.
        today: The user's today, for tests.

    Returns:
        The reading; None for no such user.
    """
    if user_for(db, user_id) is None:
        return None
    today = today or user_today(db, user_id)
    year = year or today.year
    first, last = date(year, 1, 1), date(year, 12, 31)
    invoices = db.query(InvoiceModel).filter(InvoiceModel.user_id == user_id).all()
    names = _names(db, user_id)
    revenue, expense_total, expenses = year_totals(db, user_id, year)
    received = money(sum(i.amount for i in invoices if i.paid_on is not None and first <= i.paid_on <= last))
    employment = sum(gross or 0.0 for (gross,) in db.query(PaychequeModel.gross_amount).filter(
        PaychequeModel.user_id == user_id, PaychequeModel.occurred_on >= first, PaychequeModel.occurred_on <= last))
    net = money(revenue - expense_total)
    overdue = sorted((_invoice_schema(i, names, today) for i in invoices
                      if i.paid_on is None and i.due_on < today), key=lambda i: (-(i.days_overdue or 0), i.number))
    return SelfEmployment(
        year=year, revenue=revenue, received=received, business_expenses=expense_total, net=net,
        unpaid=money(sum(i.amount for i in invoices if i.paid_on is None)), overdue=overdue, expenses=expenses,
        cpp=cpp_estimate(net, employment, year), instalments=instalments(year, today),
        gst=gst_watch(invoices, today), typical_month=typical_month(invoices, today),
        next_number=next_number(invoices), sources=SOURCES, note=NOTE,
    )
