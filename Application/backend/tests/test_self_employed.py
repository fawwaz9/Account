"""Self-employed support (Phase 4 item 15, §13.12): clients, invoices, and the CRA rules.

Pinned: an invoice's state from its dates; a payment's deposit written, moved and
removed with it; only your own clients, invoices and accounts; business shares of
expenses; revenue by issue date; CPP at both halves after a job's pay has used the
exemption and the ceilings; the instalment dates; the GST/HST watch over four
quarters and in one; the typical-month range; the tax packet's section; and no
academic table read.
"""
import re
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.main
from app._database.db import get_db
from app._database.models import InvoiceModel, PaychequeModel, TransactionModel
from app.Auth.dependencies import get_current_user
from app.Jobs.schemas.self_employed import ClientIn, ClientUpdate, InvoiceIn, InvoiceUpdate, PaidIn
from app.Jobs.services import self_employed_service as se
from app.Jobs.services.tax_packet_service import tax_packet
from conftest import make_account, make_user

TODAY = date(2026, 11, 1)
ACADEMIC_TABLES = {"courses", "grades", "course_category_weights", "grading_schemes", "tasks", "term_reviews",
                   "grade_distributions", "course_intel", "syllabus_parses", "degree_requirements", "events"}


@pytest.fixture
def acme(db, user):
    return se.create_client(db, user.id, ClientIn(name="Acme Tutoring"))


@pytest.fixture
def chequing(db, user):
    return make_account(db, user.id, "Chequing", share=1.0)


def invoice(db, user, client, number="INV-001", amount=100.0, issued=TODAY - timedelta(days=10), due=None):
    return se.create_invoice(db, user.id, InvoiceIn(client_id=client.id, number=number, amount=amount,
                                                    issued_on=issued, due_on=due), today=TODAY)


def ledger(db, user):
    return db.query(TransactionModel).filter(TransactionModel.user_id == user.id).all()


def expense(db, user, account, amount, percent, on=TODAY, description="Laptop"):
    row = TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
                           amount=-amount, occurred_on=on, description=description, business_percent=percent)
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------ clients --

def test_clients_with_their_totals(db, user, acme):
    invoice(db, user, acme, amount=100.0)
    paid = invoice(db, user, acme, number="INV-002", amount=50.0)
    se.mark_paid(db, user.id, paid.id, PaidIn(paid_on=TODAY), today=TODAY)
    se.create_client(db, user.id, ClientIn(name="Beta"))

    listed = se.list_clients(db, user.id)

    assert [(c.name, c.invoices, c.invoiced, c.unpaid) for c in listed] == [
        ("Acme Tutoring", 2, 150.0, 100.0), ("Beta", 0, 0.0, 0.0)]


def test_archived_clients_list_last(db, user, acme):
    beta = se.create_client(db, user.id, ClientIn(name="Beta"))
    se.update_client(db, user.id, acme.id, ClientUpdate(archived=True))

    assert [c.name for c in se.list_clients(db, user.id)] == ["Beta", "Acme Tutoring"]
    assert beta.archived is False


def test_a_client_with_invoices_is_archived_not_deleted(db, user, acme):
    invoice(db, user, acme)

    with pytest.raises(ValueError):
        se.delete_client(db, user.id, acme.id)

    empty = se.create_client(db, user.id, ClientIn(name="Empty"))
    se.delete_client(db, user.id, empty.id)
    assert [c.name for c in se.list_clients(db, user.id)] == ["Acme Tutoring"]


def test_another_users_client_is_not_found(db, user, acme):
    stranger = make_user(db, "stranger@example.com")

    for call in (lambda: se.update_client(db, stranger.id, acme.id, ClientUpdate(name="x")),
                 lambda: se.delete_client(db, stranger.id, acme.id),
                 lambda: se.create_invoice(db, stranger.id, InvoiceIn(client_id=acme.id, number="1", amount=5,
                                                                      issued_on=TODAY))):
        with pytest.raises(LookupError):
            call()
    assert se.list_clients(db, stranger.id) == []


# ----------------------------------------------------------------- invoices --

def test_due_in_thirty_days_unless_named(db, user, acme):
    made = invoice(db, user, acme, issued=date(2026, 10, 1))

    assert made.due_on == date(2026, 10, 31)


def test_states_from_dates(db, user, acme):
    outstanding = invoice(db, user, acme, number="A", issued=TODAY, due=TODAY)
    overdue = invoice(db, user, acme, number="B", issued=date(2026, 9, 1), due=date(2026, 10, 1))
    paid = invoice(db, user, acme, number="C", issued=date(2026, 9, 1), due=date(2026, 10, 1))
    se.mark_paid(db, user.id, paid.id, PaidIn(paid_on=date(2026, 10, 20)), today=TODAY)

    states = {i.number: (i.state, i.days_overdue) for i in se.list_invoices(db, user.id, today=TODAY)}

    assert states == {"A": ("outstanding", None), "B": ("overdue", 31), "C": ("paid", None)}
    assert outstanding.state == "outstanding" and overdue.state == "overdue"


def test_numbers_are_unique_per_user(db, user, acme):
    invoice(db, user, acme, number="INV-001")
    with pytest.raises(ValueError):
        invoice(db, user, acme, number="INV-001")

    stranger = make_user(db, "stranger@example.com")
    theirs = se.create_client(db, stranger.id, ClientIn(name="Theirs"))
    assert invoice(db, stranger, theirs, number="INV-001").number == "INV-001"


def test_renumbering_onto_a_used_number_is_refused(db, user, acme):
    invoice(db, user, acme, number="INV-001")
    second = invoice(db, user, acme, number="INV-002")

    with pytest.raises(ValueError):
        se.update_invoice(db, user.id, second.id, InvoiceUpdate(number="INV-001"), today=TODAY)
    assert db.get(InvoiceModel, second.id).number == "INV-002"


def test_due_before_issue_is_refused(db, user, acme):
    with pytest.raises(ValueError):
        InvoiceIn(client_id=acme.id, number="X", amount=5, issued_on=TODAY, due_on=TODAY - timedelta(days=1))
    made = invoice(db, user, acme, issued=TODAY, due=TODAY + timedelta(days=5))
    with pytest.raises(ValueError):
        se.update_invoice(db, user.id, made.id, InvoiceUpdate(due_on=TODAY - timedelta(days=1)), today=TODAY)
    assert db.get(InvoiceModel, made.id).due_on == TODAY + timedelta(days=5)


# ----------------------------------------------------------------- payments --

def test_paid_into_an_account_writes_one_income_row(db, user, acme, chequing):
    made = invoice(db, user, acme, amount=240.0)

    paid = se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)

    rows = ledger(db, user)
    assert paid.deposited and paid.state == "paid"
    assert [(r.kind, r.amount, r.account_id, r.occurred_on) for r in rows] == [("income", 240.0, chequing.id, TODAY)]
    assert rows[0].description == "Invoice INV-001, Acme Tutoring"


def test_paid_with_no_account_writes_nothing(db, user, acme, chequing):
    made = invoice(db, user, acme)

    paid = se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY), today=TODAY)

    assert paid.state == "paid" and not paid.deposited and ledger(db, user) == []


def test_split_by_income_share(db, user, acme, chequing):
    savings = make_account(db, user.id, "Savings", share=3.0)
    made = invoice(db, user, acme, amount=100.0)

    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, split=True), today=TODAY)

    assert sorted((r.account_id == savings.id, r.amount) for r in ledger(db, user)) == [(False, 25.0), (True, 75.0)]


def test_a_split_with_no_shares_changes_nothing(db, user, acme):
    make_account(db, user.id, "No share", share=0.0)
    made = invoice(db, user, acme)

    with pytest.raises(ValueError):
        se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, split=True), today=TODAY)

    assert db.get(InvoiceModel, made.id).paid_on is None and ledger(db, user) == []


def test_another_users_account_is_not_found_and_nothing_changes(db, user, acme):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_account(db, stranger.id, "Theirs", share=1.0)
    made = invoice(db, user, acme)

    with pytest.raises(LookupError):
        se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=theirs.id), today=TODAY)

    assert db.get(InvoiceModel, made.id).paid_on is None
    assert db.query(TransactionModel).count() == 0


def test_paid_before_issue_is_refused(db, user, acme, chequing):
    made = invoice(db, user, acme, issued=TODAY)

    with pytest.raises(ValueError):
        se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY - timedelta(days=1), account_id=chequing.id),
                     today=TODAY)
    assert ledger(db, user) == []


def test_paying_again_replaces_the_deposit(db, user, acme, chequing):
    other = make_account(db, user.id, "Other")
    made = invoice(db, user, acme, amount=80.0)
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)

    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=other.id), today=TODAY)

    assert [(r.account_id, r.amount) for r in ledger(db, user)] == [(other.id, 80.0)]


def test_unpaid_again_removes_the_deposit_only(db, user, acme, chequing):
    made = invoice(db, user, acme)
    keep = expense(db, user, chequing, 5.0, None, description="Coffee")
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)

    undone = se.mark_unpaid(db, user.id, made.id, today=TODAY)

    assert undone.state == "outstanding" and not undone.deposited
    assert [r.id for r in ledger(db, user)] == [keep.id]


def test_a_new_amount_moves_the_deposit(db, user, acme, chequing):
    made = invoice(db, user, acme, amount=100.0)
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)

    se.update_invoice(db, user.id, made.id, InvoiceUpdate(amount=130.0), today=TODAY)

    assert [r.amount for r in ledger(db, user)] == [130.0]


def test_a_new_amount_resplits_a_split(db, user, acme, chequing):
    make_account(db, user.id, "Savings", share=1.0)
    made = invoice(db, user, acme, amount=100.0)
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, split=True), today=TODAY)

    se.update_invoice(db, user.id, made.id, InvoiceUpdate(amount=60.0), today=TODAY)

    assert sorted(r.amount for r in ledger(db, user)) == [30.0, 30.0]


def test_a_deposit_deleted_from_the_ledger_is_let_go(db, user, acme, chequing):
    made = invoice(db, user, acme, amount=100.0)
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)
    db.query(TransactionModel).delete()
    db.commit()

    updated = se.update_invoice(db, user.id, made.id, InvoiceUpdate(amount=60.0), today=TODAY)

    assert not updated.deposited and ledger(db, user) == []


def test_deleting_an_invoice_deletes_its_deposit(db, user, acme, chequing):
    made = invoice(db, user, acme)
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)

    se.delete_invoice(db, user.id, made.id)

    assert se.list_invoices(db, user.id, today=TODAY) == [] and ledger(db, user) == []


def test_another_users_invoice_is_not_found(db, user, acme, chequing):
    stranger = make_user(db, "stranger@example.com")
    made = invoice(db, user, acme)
    se.mark_paid(db, user.id, made.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)

    for call in (lambda: se.update_invoice(db, stranger.id, made.id, InvoiceUpdate(amount=1.0)),
                 lambda: se.mark_paid(db, stranger.id, made.id, PaidIn(paid_on=TODAY)),
                 lambda: se.mark_unpaid(db, stranger.id, made.id),
                 lambda: se.delete_invoice(db, stranger.id, made.id)):
        with pytest.raises(LookupError):
            call()
    assert db.get(InvoiceModel, made.id).amount == 100.0 and len(ledger(db, user)) == 1


# ------------------------------------------------------------ the year ------

def test_revenue_by_issue_date_and_payments_beside_it(db, user, acme, chequing):
    last_year = invoice(db, user, acme, number="1", amount=300.0, issued=date(2025, 12, 20))
    se.mark_paid(db, user.id, last_year.id, PaidIn(paid_on=date(2026, 1, 5)), today=TODAY)
    long_paid = invoice(db, user, acme, number="0", amount=70.0, issued=date(2025, 10, 1))
    se.mark_paid(db, user.id, long_paid.id, PaidIn(paid_on=date(2025, 11, 1)), today=TODAY)
    invoice(db, user, acme, number="2", amount=500.0, issued=date(2026, 3, 1))
    expense(db, user, chequing, 200.0, 50)
    expense(db, user, chequing, 90.0, None, description="Groceries")
    expense(db, user, chequing, 40.0, 100, on=date(2025, 12, 1), description="Last year's")

    year = se.self_employment(db, user.id, today=TODAY)

    assert (year.revenue, year.received, year.business_expenses, year.net) == (500.0, 300.0, 100.0, 400.0)
    assert [(e.description, e.percent, e.business_amount) for e in year.expenses] == [("Laptop", 50, 100.0)]
    assert year.unpaid == 500.0


def test_overdue_most_late_first(db, user, acme):
    invoice(db, user, acme, number="A", issued=date(2026, 9, 1), due=date(2026, 10, 20))
    invoice(db, user, acme, number="B", issued=date(2026, 8, 1), due=date(2026, 9, 1))
    invoice(db, user, acme, number="C", issued=TODAY, due=TODAY)

    assert [i.number for i in se.self_employment(db, user.id, today=TODAY).overdue] == ["B", "A"]


def test_another_users_records_never_count(db, user, acme, chequing):
    stranger = make_user(db, "stranger@example.com")
    theirs = se.create_client(db, stranger.id, ClientIn(name="Theirs"))
    invoice(db, stranger, theirs, amount=29_000.0)
    expense(db, stranger, make_account(db, stranger.id, "Theirs"), 500.0, 100)
    from app._database.models import JobModel
    job = JobModel(id=uuid.uuid4(), user_id=stranger.id, name="Their job", hourly_rate=20.0)
    db.add(job)
    db.add(PaychequeModel(id=uuid.uuid4(), user_id=stranger.id, job_id=job.id, occurred_on=date(2026, 5, 1),
                          gross_amount=40_000.0))
    db.commit()

    year = se.self_employment(db, user.id, today=TODAY)

    assert (year.revenue, year.business_expenses, year.gst.four_quarter_total, year.expenses) == (0.0, 0.0, 0.0, [])
    assert year.cpp.employment_gross == 0.0
    assert se.list_invoices(db, user.id, today=TODAY) == []


def test_rows_written_past_the_routes_stay_their_owners(db, user, acme, chequing):
    """Rows no route would write, crossing users: another's invoice on my client, my
    invoice on another's client, another's ledger row in my deposit's group. The
    user filters keep each to its owner."""
    stranger = make_user(db, "stranger@example.com")
    theirs = se.create_client(db, stranger.id, ClientIn(name="Their secret client"))
    mine = invoice(db, user, acme, amount=100.0)
    se.mark_paid(db, user.id, mine.id, PaidIn(paid_on=TODAY, account_id=chequing.id), today=TODAY)
    group = db.get(InvoiceModel, mine.id).group_id
    db.add(InvoiceModel(id=uuid.uuid4(), user_id=stranger.id, client_id=acme.id, number="X1", issued_on=TODAY,
                        due_on=TODAY, amount=9_999.0))
    db.add(InvoiceModel(id=uuid.uuid4(), user_id=user.id, client_id=theirs.id, number="X2", issued_on=TODAY,
                        due_on=TODAY, amount=1.0))
    stray = TransactionModel(id=uuid.uuid4(), user_id=stranger.id,
                             account_id=make_account(db, stranger.id, "Theirs").id, kind="income", amount=5.0,
                             occurred_on=TODAY, group_id=group)
    db.add(stray)
    db.commit()
    before = [r.id for r in ledger(db, user)]

    assert [(c.name, c.invoiced) for c in se.list_clients(db, user.id)] == [("Acme Tutoring", 100.0)]
    assert {i.number: i.client for i in se.list_invoices(db, user.id, today=TODAY)} == {
        "INV-001": "Acme Tutoring", "X2": "A client"}
    se.update_invoice(db, user.id, mine.id, InvoiceUpdate(amount=130.0), today=TODAY)
    assert [(r.id, r.amount) for r in ledger(db, user)] == [(before[0], 130.0)]
    assert db.get(TransactionModel, stray.id).amount == 5.0


@pytest.mark.parametrize(("net", "employment", "base", "second"), [
    (15_000, 0, 1_368.50, 0.0),           # (15,000 - 3,500) x 11.9%
    (15_000, 10_000, 1_785.00, 0.0),      # the job used the exemption: 15,000 x 11.9%
    (2_000, 1_000, 0.0, 0.0),             # under what's left of the exemption
    (80_000, 0, 8_460.90, 432.00),        # the base maximum, then 5,400 x 8%
    (10_000, 80_000, 0.0, 400.00),        # the job filled the first ceiling: 5,000 x 8%
    (-500, 0, 0.0, 0.0),                  # a loss owes none
])
def test_cpp_at_both_halves(net, employment, base, second):
    estimate = se.cpp_estimate(net, employment, 2026)

    assert (estimate.base, estimate.second, estimate.total) == (base, second, round(base + second, 2))
    assert (estimate.ceiling, estimate.second_ceiling, estimate.rate) == (74_600.0, 85_000.0, 11.9)


def test_cpp_uses_the_latest_figures_it_knows():
    assert se.cpp_estimate(10_000, 0, 2027).figures_year == 2026
    assert se.cpp_estimate(10_000, 0, 2025).ceiling == 71_300.0


def test_cpp_counts_the_years_recorded_pay(db, user, acme):
    from app._database.models import JobModel
    job = JobModel(id=uuid.uuid4(), user_id=user.id, name="Barista", hourly_rate=18.0)
    db.add(job)
    db.add(PaychequeModel(id=uuid.uuid4(), user_id=user.id, job_id=job.id, occurred_on=date(2026, 5, 1),
                          gross_amount=10_000.0))
    db.add(PaychequeModel(id=uuid.uuid4(), user_id=user.id, job_id=job.id, occurred_on=date(2025, 5, 1),
                          gross_amount=50_000.0))
    db.commit()
    invoice(db, user, acme, amount=15_000.0, issued=date(2026, 6, 1))

    cpp = se.self_employment(db, user.id, today=TODAY).cpp

    assert (cpp.employment_gross, cpp.total) == (10_000.0, 1_785.00)


def test_instalment_dates_and_the_next():
    assert se.instalments(2026, TODAY).dates == [date(2026, 3, 15), date(2026, 6, 15), date(2026, 9, 15),
                                                 date(2026, 12, 15)]
    assert se.instalments(2026, TODAY).next_due == date(2026, 12, 15)
    assert se.instalments(2026, date(2026, 12, 15)).next_due == date(2026, 12, 15)
    assert se.instalments(2026, date(2026, 12, 16)).next_due is None
    assert se.instalments(2026, TODAY).threshold == 3_000.0


def rows(*pairs):
    return [InvoiceModel(issued_on=day, amount=amount) for day, amount in pairs]


def test_gst_four_quarters_to_date():
    watch = se.gst_watch(rows((date(2025, 12, 31), 1_000), (date(2026, 1, 1), 2_000), (date(2026, 11, 1), 500),
                              (date(2026, 11, 2), 9_999), (date(2025, 9, 30), 7_777)), TODAY)

    assert [(q.label, q.total) for q in watch.quarters] == [
        ("Jan-Mar 2026", 2_000.0), ("Apr-Jun 2026", 0.0), ("Jul-Sep 2026", 0.0), ("Oct-Dec 2026", 500.0)]
    assert (watch.four_quarter_total, watch.level, watch.threshold) == (2_500.0, "under", 30_000.0)


def test_gst_quarters_cross_the_year():
    watch = se.gst_watch([], date(2026, 2, 10))

    assert [q.starts_on for q in watch.quarters] == [date(2025, 4, 1), date(2025, 7, 1), date(2025, 10, 1),
                                                     date(2026, 1, 1)]


@pytest.mark.parametrize(("amounts", "level"), [
    ((7_000, 7_000, 7_000, 2_999), "under"),
    ((7_000, 7_000, 7_000, 3_000), "approaching"),
    ((8_000, 8_000, 8_000, 6_000), "approaching"),
    ((8_000, 8_000, 8_000, 6_001), "over"),
])
def test_gst_levels(amounts, level):
    starts = [date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15), date(2026, 10, 15)]

    assert se.gst_watch(rows(*zip(starts, amounts)), TODAY).level == level


def test_gst_one_quarter_over_is_over():
    assert se.gst_watch(rows((date(2026, 10, 2), 30_001)), TODAY).level == "over"


def test_typical_month_needs_three_finished_months():
    assert se.typical_month([], TODAY) is None
    assert se.typical_month(rows((date(2026, 9, 3), 500)), TODAY) is None
    assert se.typical_month(rows((date(2026, 8, 3), 500)), TODAY).months == 3


def test_typical_month_is_a_quartile_range_with_empty_months():
    found = se.typical_month(rows((date(2026, 1, 9), 900), (date(2026, 5, 9), 400), (date(2026, 6, 9), 600),
                                  (date(2026, 7, 9), 800), (date(2026, 9, 9), 300),
                                  (date(2026, 10, 9), 700), (date(2026, 11, 1), 5_000)), TODAY)

    # May to October, August at $0: 0, 300, 400, 600, 700, 800. November is
    # unfinished and January too old.
    assert (found.months, found.low, found.high) == (6, 325.0, 675.0)


@pytest.mark.parametrize(("numbers", "suggested"), [
    ((), "INV-001"),
    (("INV-009", "INV-002"), "INV-010"),
    (("2026-3",), "2026-4"),
    (("A7-B", "Draft"), "A8-B"),
])
def test_next_number(numbers, suggested):
    assert se.next_number([InvoiceModel(number=n) for n in numbers]) == suggested


def test_the_tax_packet_carries_the_year(db, user, acme, chequing):
    assert tax_packet(db, user.id, 2026).self_employment is None

    invoice(db, user, acme, amount=15_000.0, issued=date(2026, 2, 1))
    expense(db, user, chequing, 1_000.0, 50)

    section = tax_packet(db, user.id, 2026).self_employment
    assert (section.invoices, section.revenue, section.business_expenses, section.net, section.cpp) == (
        1, 15_000.0, 500.0, 14_500.0, 1_309.0)


def test_no_academic_table_is_read(db, user, acme, chequing):
    invoice(db, user, acme)
    expense(db, user, chequing, 10.0, 100)
    seen: list[str] = []
    bind = db.get_bind()

    def capture(_conn, _cursor, statement, *_args):
        seen.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        se.self_employment(db, user.id, today=TODAY)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    touched = {name for sql in seen for name in re.findall(r'(?:from|join)\s+"?([a-z_]+)"?', sql)}
    assert {"invoices", "transactions"} <= touched, touched
    assert not touched & ACADEMIC_TABLES, touched & ACADEMIC_TABLES


# ------------------------------------------------------------------ routes --

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, chequing, client):
    base = f"/api/jobs/{user.id}"
    made = client.post(f"{base}/clients", json={"name": "Acme"}).json()
    body = {"client_id": made["id"], "number": "INV-001", "amount": 120, "issued_on": "2026-10-01"}

    first = client.post(f"{base}/invoices", json=body)
    assert first.status_code == 200 and first.json()["due_on"] == "2026-10-31"
    assert client.post(f"{base}/invoices", json=body).status_code == 400
    assert client.post(f"{base}/invoices", json={**body, "client_id": str(uuid.uuid4())}).status_code == 404
    assert client.post(f"{base}/invoices", json={**body, "number": "2", "amount": 0}).status_code == 422
    invoice_id = first.json()["id"]
    paid = client.post(f"{base}/invoices/{invoice_id}/paid", json={"paid_on": "2026-10-20",
                                                                   "account_id": str(chequing.id)})
    assert paid.json()["state"] == "paid" and paid.json()["deposited"] is True
    assert client.post(f"{base}/invoices/{invoice_id}/paid",
                       json={"paid_on": "2026-10-20", "account_id": str(uuid.uuid4())}).status_code == 404
    assert client.delete(f"{base}/invoices/{invoice_id}/paid").json()["state"] in ("outstanding", "overdue")
    assert client.delete(f"{base}/clients/{made['id']}").status_code == 400
    assert client.get(f"{base}/self-employment?year=2026").json()["revenue"] == 120.0
    assert client.get(f"{base}/self-employment?year=1999").status_code == 422
    assert client.delete(f"{base}/invoices/{invoice_id}").status_code == 204
    assert client.delete(f"{base}/clients/{made['id']}").status_code == 204


def test_tagging_an_expense(db, user, chequing, client):
    spent = expense(db, user, chequing, 60.0, None)
    earned = TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=chequing.id, kind="income", amount=60.0,
                              occurred_on=TODAY)
    db.add(earned)
    db.commit()
    url = f"/api/finances/{user.id}/transactions"

    assert client.patch(f"{url}/{spent.id}", json={"business_percent": 50}).json()["business_percent"] == 50
    assert client.patch(f"{url}/{earned.id}", json={"business_percent": 50}).status_code == 400
    assert client.patch(f"{url}/{spent.id}", json={"business_percent": 0}).status_code == 422
    assert client.patch(f"{url}/{spent.id}", json={"business_percent": 101}).status_code == 422
    assert client.patch(f"{url}/{spent.id}", json={"business_percent": None}).json()["business_percent"] is None
