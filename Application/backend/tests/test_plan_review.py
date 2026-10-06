"""The plan loop (Phase 1 D37): a saved plan against what each month did.

Actuals are hand-computed against the plan's own definitions -- liquid money,
transfers between liquid accounts netting to nothing, card purchases counted
when made and card payments not at all, tuition counted and named.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import SavedPlanModel, TransactionModel, TuitionPaymentModel
from app.Auth.dependencies import get_current_user
from app.Finances.services.plan_review_service import review, save_plan
from app.shared.dates import user_today
from conftest import make_account, make_user

TODAY = date(2026, 6, 15)


def money(db, user, account, kind, amount, on, group=None):
    row = TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind=kind,
                           amount=amount, occurred_on=on, group_id=group)
    db.add(row)
    db.commit()
    return row


def transfer(db, user, source, target, amount, on):
    group = uuid.uuid4()
    money(db, user, source, "transfer", -amount, on, group)
    money(db, user, target, "transfer", amount, on, group)


def saved(db, user, saved_on, months):
    db.add(SavedPlanModel(
        id=uuid.uuid4(), user_id=user.id, saved_on=saved_on, starts_on=saved_on,
        ends_on=date(2027, 4, 30), starting_balance=0.0,
        months=[{"month": m.isoformat(), "money_in": i, "money_out": o, "end_balance": e}
                for m, i, o, e in months],
    ))
    db.commit()


@pytest.fixture
def accounts(db, user):
    return {
        "chequing": make_account(db, user.id, "Chequing"),
        "savings": make_account(db, user.id, "Savings", kind="savings"),
        "tfsa": make_account(db, user.id, "TFSA", kind="investment"),
        "card": make_account(db, user.id, "Visa", kind="debt"),
    }


def test_nothing_saved_says_nothing(db, user):
    assert review(db, user.id, on_day=TODAY).model_dump() == {"latest": None, "months": []}


def test_a_month_against_the_plan_saved_before_it(db, user, accounts):
    a = accounts
    saved(db, user, date(2026, 4, 20), [
        (date(2026, 4, 1), 100, 50, 900),   # the month it was saved in: not compared
        (date(2026, 5, 1), 2000, 1500, 1400),
        (date(2026, 6, 1), 2000, 1500, 1900),  # not finished yet: not compared
    ])
    money(db, user, a["chequing"], "income", 1000.0, date(2026, 4, 30))  # April: opening money
    money(db, user, a["chequing"], "income", 2100.0, date(2026, 5, 2))
    money(db, user, a["chequing"], "expense", -400.0, date(2026, 5, 3))
    money(db, user, a["chequing"], "expense", 25.0, date(2026, 5, 4))      # a refund
    transfer(db, user, a["chequing"], a["savings"], 500.0, date(2026, 5, 5))  # nets to nothing
    transfer(db, user, a["chequing"], a["tfsa"], 300.0, date(2026, 5, 6))     # money out
    money(db, user, a["card"], "expense", -200.0, date(2026, 5, 7))        # a card purchase counts...
    transfer(db, user, a["chequing"], a["card"], 200.0, date(2026, 5, 20))   # ...paying it does not
    tuition = money(db, user, a["chequing"], "expense", -900.0, date(2026, 5, 10))
    db.add(TuitionPaymentModel(id=uuid.uuid4(), user_id=user.id, transaction_id=tuition.id,
                               semester="Summer", school_year=3, occurred_on=date(2026, 5, 10)))
    db.commit()

    result = review(db, user.id, on_day=TODAY)
    assert result.latest.saved_on == date(2026, 4, 20)
    [may] = result.months
    assert may.month == date(2026, 5, 1) and may.plan_saved_on == date(2026, 4, 20)
    assert (may.planned_in, may.planned_out, may.planned_end) == (2000, 1500, 1400)
    assert may.actual_in == 2100.0
    assert may.actual_out == 400.0 - 25.0 + 300.0 + 200.0 + 900.0
    assert may.tuition_out == 900.0
    # Liquid only: 1000 + 2100 - 400 + 25 - 300 (to the TFSA) - 200 (card paid) - 900.
    assert may.actual_end == 1325.0


def test_each_month_uses_the_newest_plan_saved_before_it_began(db, user, accounts):
    saved(db, user, date(2026, 2, 10), [(date(2026, 3, 1), 1, 1, 1), (date(2026, 4, 1), 2, 2, 2),
                                        (date(2026, 5, 1), 3, 3, 3)])
    saved(db, user, date(2026, 3, 14), [(date(2026, 3, 1), 9, 9, 9), (date(2026, 4, 1), 20, 20, 20),
                                        (date(2026, 5, 1), 30, 30, 30)])
    months = review(db, user.id, on_day=TODAY).months
    assert [(m.month.month, m.planned_in, m.plan_saved_on.month) for m in months] == [
        (3, 1, 2),   # March: the March 14 plan began mid-month, so February's stands
        (4, 20, 3),
        (5, 30, 3),
    ]


def test_an_archived_account_still_held_its_money(db, user):
    old = make_account(db, user.id, "Old chequing", archived=True)
    saved(db, user, date(2026, 4, 1), [(date(2026, 5, 1), 0, 0, 0)])
    money(db, user, old, "income", 300.0, date(2026, 5, 3))
    [may] = review(db, user.id, on_day=TODAY).months
    assert (may.actual_in, may.actual_end) == (300.0, 300.0)


def test_another_users_money_is_not_counted(db, user, accounts):
    other = make_user(db, "other@example.com")
    theirs = make_account(db, other.id, "Theirs")
    saved(db, user, date(2026, 4, 1), [(date(2026, 5, 1), 0, 0, 0)])
    money(db, other, theirs, "income", 5000.0, date(2026, 5, 3))
    [may] = review(db, user.id, on_day=TODAY).months
    assert (may.actual_in, may.actual_end) == (0.0, 0.0)


def test_saving_keeps_every_plan(db, user, accounts):
    first = save_plan(db, user.id)
    second = save_plan(db, user.id)
    assert first.id != second.id
    assert db.query(SavedPlanModel).filter(SavedPlanModel.user_id == user.id).count() == 2
    assert first.saved_on == user_today(db, user.id)
    assert first.months and set(first.months[0]) == {"month", "money_in", "money_out", "end_balance"}


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, accounts, client):
    base = f"/api/finances/{user.id}/plan"
    assert client.get(f"{base}/review").json() == {"latest": None, "months": []}
    made = client.post(f"{base}/saved")
    assert made.status_code == 200
    assert client.get(f"{base}/review").json()["latest"]["id"] == made.json()["id"]
