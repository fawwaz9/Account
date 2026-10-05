"""CSV import (Phase 1 item 7): reading real bank formats, duplicates, commit, undo.

A bad import corrupts the ledger, which is real money (account-vision.md §15).
So beyond "does it parse", most of these pin the safety rails: nothing written
by a preview, only the named lines written by a commit, duplicates never
written silently, and undo removing exactly the import's rows -- counted
before and after, per the rule that a cleanup removing more than it should is
a failure even when everything else passes.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import ImportModel, TransactionModel
from app.Auth.dependencies import get_current_user
from app.Finances.schemas.importing import CommitRequest, ImportMapping
from app.Finances.services import import_service
from app.Finances.services.account_service import delete_account
from app.Finances.services.import_service import (
    commit,
    detect_mapping,
    parse_table,
    preview,
    read_rows,
    summaries,
    undo,
)
from tests.conftest import make_account, make_user

D = datetime.date

RBC = """Account Type,Account Number,Transaction Date,Cheque Number,Description 1,Description 2,CAD$,USD$
Chequing,01234-5678901,10/1/2026,,TIM HORTONS #4521,VANCOUVER BC,-4.50,
Chequing,01234-5678901,10/2/2026,,PAYROLL DEP,BOOKSTORE,812.40,
Chequing,01234-5678901,10/3/2026,,NETFLIX.COM,,-16.49,
"""

TD = """10/01/2026,TIM HORTONS #4521,4.50,,1234.56
10/03/2026,PAYROLL DEP,,812.40,2046.96
10/04/2026,SAFEWAY #4410,62.18,,1984.78
"""

BMO_CARD = """Item #,Card #,Transaction Date,Posting Date,Transaction Amount,Description
1,'5191',20261001,20261002,24.99,SPOTIFY P1234
2,'5191',20261003,20261004,-500.00,PAYMENT RECEIVED - THANK YOU
"""


def rows_of(text, mapping=None):
    table = parse_table(text)
    used = mapping or detect_mapping(table)[0]
    return used, read_rows(table, used)


def amounts(rows):
    return [(r.on_date, r.description, r.amount) for r in rows]


# --- reading the formats ---------------------------------------------------

def test_rbc_with_its_split_description():
    mapping, rows = rows_of(RBC)
    assert (mapping.has_header, mapping.date, mapping.description, mapping.amount) == (True, 2, [4, 5], 6)
    assert amounts(rows) == [
        (D(2026, 10, 1), "TIM HORTONS #4521 VANCOUVER BC", -4.5),
        (D(2026, 10, 2), "PAYROLL DEP BOOKSTORE", 812.4),
        (D(2026, 10, 3), "NETFLIX.COM", -16.49),
    ]


def test_td_without_a_header_reads_debit_and_credit_columns():
    mapping, rows = rows_of(TD)
    assert (mapping.has_header, mapping.date, mapping.description, mapping.debit, mapping.credit) == (
        False, 0, [1], 2, 3,
    )
    assert [r.amount for r in rows] == [-4.5, 812.4, -62.18]
    assert [r.line for r in rows] == [1, 2, 3]


def test_a_card_export_reads_compact_dates():
    mapping, rows = rows_of(BMO_CARD)
    assert (mapping.date, mapping.amount, mapping.description) == (2, 4, [5])
    assert rows[0].on_date == D(2026, 10, 1)
    # As written in the file -- inverting for a card account is the preview's job.
    assert [r.amount for r in rows] == [24.99, -500.0]


def test_withdrawals_and_deposits_headers():
    text = "Date,Description,Withdrawals,Deposits,Balance\n2026-10-01,Rent,900.00,,100.00\n2026-10-02,Bursary,,1500.00,1600.00\n"
    mapping, rows = rows_of(text)
    assert (mapping.debit, mapping.credit) == (2, 3)
    assert [r.amount for r in rows] == [-900.0, 1500.0]


def test_semicolons_and_decimal_commas():
    text = "Datum;Beschreibung;Betrag\n2026-10-01;Bakery;-3,50\n"
    _, rows = rows_of(text)
    assert rows[0].amount == -3.5


def test_date_order_is_read_from_the_dates():
    _, rows = rows_of("Date,Description,Amount\n13/02/2026,A,-1\n01/03/2026,B,-1\n")
    assert [r.on_date for r in rows] == [D(2026, 2, 13), D(2026, 3, 1)]  # day first
    _, rows = rows_of("Date,Description,Amount\n02/13/2026,A,-1\n03/01/2026,B,-1\n")
    assert [r.on_date for r in rows] == [D(2026, 2, 13), D(2026, 3, 1)]  # month first


def test_unreadable_rows_are_errors_not_guesses():
    _, rows = rows_of("Date,Description,Amount\nsoon,A,-1\n2026-10-01,B,lots\n2026-10-02,C,0.00\n")
    assert [r.status for r in rows] == ["error", "error", "error"]
    assert "Couldn't read a date" in rows[0].reason
    assert rows[1].reason == "Couldn't read an amount"
    assert rows[2].reason == "The amount is zero"


# --- the preview -----------------------------------------------------------

@pytest.fixture
def chequing(db, user):
    return make_account(db, user.id, "Chequing", share=100.0)


def txn(db, user, account, amount, on, description="x", import_id=None):
    row = TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id,
                           kind="income" if amount > 0 else "expense", amount=amount,
                           description=description, occurred_on=on, import_id=import_id)
    db.add(row)
    db.commit()
    return row


def count(db, user):
    return db.query(TransactionModel).filter(TransactionModel.user_id == user.id).count()


def test_a_preview_writes_nothing(db, user, chequing):
    before = count(db, user)
    shown = preview(db, user.id, chequing.id, RBC, None)
    assert count(db, user) == before
    assert (shown.new_count, shown.duplicate_count, shown.error_count) == (3, 0, 0)
    assert (shown.money_in, shown.money_out) == (812.4, 20.99)


def test_an_ambiguous_date_order_is_flagged(db, user, chequing):
    shown = preview(db, user.id, chequing.id, RBC, None)
    assert shown.date_order_assumed  # 10/1, 10/2, 10/3 read either way


def test_a_card_account_starts_inverted(db, user):
    card = make_account(db, user.id, "Mastercard", kind="debt")
    shown = preview(db, user.id, card.id, BMO_CARD, None)
    assert shown.mapping.invert
    assert [r.amount for r in shown.rows] == [-24.99, 500.0]  # a purchase is an expense


def test_a_hand_entered_row_on_the_same_day_is_a_duplicate(db, user, chequing):
    mine = txn(db, user, chequing, -4.5, D(2026, 10, 1), "Coffee")
    shown = preview(db, user.id, chequing.id, RBC, None)
    first = shown.rows[0]
    assert (first.status, first.duplicate_of) == ("duplicate", mine.id)
    assert shown.new_count == 2


def test_a_different_amount_on_the_same_day_is_not_a_duplicate(db, user, chequing):
    """Otherwise any purchase that day would hide the import's row, unticked."""
    txn(db, user, chequing, -6.25, D(2026, 10, 1), "Coffee")
    assert preview(db, user.id, chequing.id, RBC, None).rows[0].status == "new"


def test_the_same_merchant_a_few_days_apart_is_a_duplicate_but_not_a_week(db, user, chequing):
    txn(db, user, chequing, -16.49, D(2026, 9, 30), "NETFLIX.COM 8842")  # 3 days before
    assert preview(db, user.id, chequing.id, RBC, None).rows[2].status == "duplicate"


def test_a_week_apart_is_not_a_duplicate(db, user, chequing):
    txn(db, user, chequing, -16.49, D(2026, 9, 25), "NETFLIX.COM")  # 8 days before
    assert preview(db, user.id, chequing.id, RBC, None).rows[2].status == "new"


def test_two_coffees_in_the_file_are_two_coffees(db, user, chequing):
    """One existing coffee matches one row; the second is still new."""
    text = "Date,Description,Amount\n2026-10-01,Coffee,-4.50\n2026-10-01,Coffee,-4.50\n"
    txn(db, user, chequing, -4.5, D(2026, 10, 1), "Coffee")
    shown = preview(db, user.id, chequing.id, text, None)
    assert [r.status for r in shown.rows] == ["duplicate", "new"]


def test_another_account_is_not_a_duplicate(db, user, chequing):
    other = make_account(db, user.id, "Savings", kind="savings")
    txn(db, user, other, -4.5, D(2026, 10, 1), "Coffee")
    assert preview(db, user.id, chequing.id, RBC, None).rows[0].status == "new"


def test_someone_elses_account_is_not_yours_to_preview(db, user, chequing):
    other = make_user(db, "other@example.com")
    assert preview(db, other.id, chequing.id, RBC, None) is None


def test_an_oversized_file_is_refused(db, user, chequing):
    text = "Date,Description,Amount\n" + "2026-10-01,A,-1\n" * 3001
    with pytest.raises(ValueError, match="more than 3000 rows"):
        preview(db, user.id, chequing.id, text, None)


# --- commit ----------------------------------------------------------------

def mapping_of(text):
    return detect_mapping(parse_table(text))[0]


def test_a_commit_writes_only_the_lines_named(db, user, chequing):
    before = count(db, user)
    summary = commit(db, user.id, CommitRequest(
        account_id=chequing.id, csv_text=RBC, mapping=mapping_of(RBC), lines=[2, 4], filename="oct.csv",
    ))
    assert count(db, user) == before + 2
    rows = db.query(TransactionModel).filter(TransactionModel.import_id == summary.id).all()
    assert sorted((r.description, r.amount, r.kind) for r in rows) == [
        ("NETFLIX.COM", -16.49, "expense"),
        ("TIM HORTONS #4521 VANCOUVER BC", -4.5, "expense"),
    ]
    assert (summary.row_count, summary.rows_remaining, summary.filename) == (2, 2, "oct.csv")
    assert (summary.first_date, summary.last_date) == (D(2026, 10, 1), D(2026, 10, 3))


def test_the_same_file_twice_adds_nothing_unticked(db, user, chequing):
    commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=RBC,
                                      mapping=mapping_of(RBC), lines=[2, 3, 4]))
    again = preview(db, user.id, chequing.id, RBC, None)
    assert (again.new_count, again.duplicate_count) == (0, 3)


def test_an_unreadable_or_missing_line_is_refused_and_nothing_is_written(db, user, chequing):
    text = "Date,Description,Amount\n2026-10-01,A,-1\nsoon,B,-1\n"
    before = count(db, user)
    with pytest.raises(ValueError, match="couldn't be read"):
        commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=text,
                                          mapping=mapping_of(text), lines=[2, 3]))
    with pytest.raises(ValueError, match="not in the file"):
        commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=text,
                                          mapping=mapping_of(text), lines=[9]))
    assert count(db, user) == before
    assert db.query(ImportModel).count() == 0


def test_a_commit_into_someone_elses_account_writes_nothing(db, user, chequing):
    other = make_user(db, "other@example.com")
    assert commit(db, other.id, CommitRequest(account_id=chequing.id, csv_text=RBC,
                                              mapping=mapping_of(RBC), lines=[2])) is None
    assert db.query(TransactionModel).count() == 0


def test_imported_repeats_reach_the_subscription_audit(db, user, chequing):
    text = ("Date,Description,Amount\n2026-07-03,NETFLIX.COM 8842101,-16.49\n"
            "2026-08-03,NETFLIX.COM 8842102,-16.49\n2026-09-03,NETFLIX.COM 8842103,-16.49\n")
    summary = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=text,
                                                mapping=mapping_of(text), lines=[2, 3, 4]))
    assert summary.subscription_candidates == 1


# --- undo ------------------------------------------------------------------

def test_undo_removes_exactly_the_imports_rows(db, user, chequing):
    mine = txn(db, user, chequing, -12.0, D(2026, 10, 2), "Hand-entered")
    first = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=RBC,
                                              mapping=mapping_of(RBC), lines=[2, 3]))
    text = "Date,Description,Amount\n2026-10-09,Other import,-7.00\n"
    second = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=text,
                                               mapping=mapping_of(text), lines=[2]))
    before = count(db, user)

    assert undo(db, user.id, first.id) == 2
    assert count(db, user) == before - 2
    remaining = {r.id for r in db.query(TransactionModel).filter(TransactionModel.user_id == user.id)}
    assert mine.id in remaining
    assert db.query(TransactionModel).filter(TransactionModel.import_id == second.id).count() == 1
    assert [s.id for s in summaries(db, user.id)] == [second.id]


def test_undo_of_someone_elses_import_touches_nothing(db, user, chequing):
    summary = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=RBC,
                                                mapping=mapping_of(RBC), lines=[2]))
    other = make_user(db, "other@example.com")
    before = count(db, user)
    assert undo(db, other.id, summary.id) is None
    assert count(db, user) == before


def test_a_row_removed_by_hand_is_not_counted_as_remaining(db, user, chequing):
    summary = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=RBC,
                                                mapping=mapping_of(RBC), lines=[2, 3]))
    one = db.query(TransactionModel).filter(TransactionModel.import_id == summary.id).first()
    db.delete(one)
    db.commit()
    [now] = summaries(db, user.id)
    assert (now.row_count, now.rows_remaining) == (2, 1)


def test_undo_refuses_if_the_count_would_not_match(db, user, chequing, monkeypatch):
    """The before-and-after check is what stops a wrong filter quietly deleting more."""
    summary = commit(db, user.id, CommitRequest(account_id=chequing.id, csv_text=RBC,
                                                mapping=mapping_of(RBC), lines=[2, 3]))
    before = count(db, user)
    real_query = db.query

    class Wrong:
        def __init__(self, q):
            self.q = q

        def filter(self, *a):
            return Wrong(self.q.filter(*a))

        def delete(self, **kw):
            return 99  # pretend the statement touched more rows than it should

        def __getattr__(self, name):
            return getattr(self.q, name)

    def query(*models):
        q = real_query(*models)
        return Wrong(q) if len(models) == 1 and models[0] is TransactionModel else q

    monkeypatch.setattr(db, "query", query)
    with pytest.raises(RuntimeError, match="nothing was changed"):
        undo(db, user.id, summary.id)
    monkeypatch.undo()
    assert count(db, user) == before


def test_an_account_whose_imports_are_undone_can_be_deleted(db, user):
    spare = make_account(db, user.id, "Spare")
    make_account(db, user.id, "Chequing", share=100.0)  # the last spending account stays
    summary = commit(db, user.id, CommitRequest(account_id=spare.id, csv_text=RBC,
                                                mapping=mapping_of(RBC), lines=[2]))
    for row in db.query(TransactionModel).filter(TransactionModel.import_id == summary.id):
        db.delete(row)  # every imported row removed by hand, the record left behind
    db.commit()
    assert delete_account(db, user.id, spare.id) is not None
    assert db.query(ImportModel).count() == 0


# --- the routes ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, client, chequing):
    base = f"/api/finances/{user.id}/imports"
    shown = client.post(f"{base}/preview", json={"account_id": str(chequing.id), "csv_text": RBC}).json()
    assert shown["new_count"] == 3
    made = client.post(base, json={
        "account_id": str(chequing.id), "csv_text": RBC, "mapping": shown["mapping"], "lines": [2, 3, 4],
    })
    assert made.status_code == 201
    import_id = made.json()["id"]
    assert [i["id"] for i in client.get(base).json()] == [import_id]
    assert client.delete(f"{base}/{import_id}").json() == {"removed": 3}
    assert client.delete(f"{base}/{import_id}").status_code == 404
    assert client.post(f"{base}/preview", json={
        "account_id": str(chequing.id), "csv_text": "x" * 1_000_001,
    }).status_code == 422
