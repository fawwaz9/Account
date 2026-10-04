"""Cash tips go to one chosen account, and wait when there is none.

The rules, as decided with the owner:
  - no account chosen (or the chosen one archived or gone): the tip is HELD --
    recorded on the shift, absent from the budget, tip_in_ledger false;
  - choosing an account files every held tip into it;
  - changing the account affects tips from now on -- tips already in the
    budget stay where they landed.

Every test that moves money counts the rows in every account before and after,
so a write that lands somewhere it should not cannot hide behind a passing
assertion about the one account it was meant for.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.Auth.dependencies import get_current_user
from app._database.db import get_db
from app._database.models import AccountModel, ShiftRecordModel, TransactionModel
from app.Finances.services.account_service import delete_account
from app.Jobs.schemas.job import JobCreate, JobKind, ShiftCreate, ShiftRecordUpsert
from app.Jobs.services.job_service import (
    add_shift,
    confirm_shift,
    create_job,
    list_shifts,
    set_cash_tip_account,
)
from tests.conftest import make_account, make_user

MON = datetime.date(2026, 10, 5)
TUE = datetime.date(2026, 10, 6)


@pytest.fixture
def job(db, user):
    return create_job(db, user.id, JobCreate(
        name="Cafe", kind=JobKind.HOURLY, hourly_rate=16.0,
        started_on=datetime.date(2026, 9, 1),
    ))


@pytest.fixture
def cash(db, user):
    return make_account(db, user.id, "Cash", share=0.0)


@pytest.fixture
def chequing(db, user):
    return make_account(db, user.id, "Chequing", share=100.0)


def shift(db, user, job, on):
    return add_shift(db, user.id, job.id, ShiftCreate(
        on_date=on, start_time=datetime.time(9), end_time=datetime.time(13),
    ))


def tip(db, user, event_id, on, amount=40.0, cash=True):
    confirm_shift(db, user.id, event_id, on, ShiftRecordUpsert(
        confirmed=True, tip_amount=amount, tip_is_cash=cash))


def rows_by_account(db, user):
    """{account name: [amounts]} for every income row, every account."""
    out = {}
    for row, account in (
        db.query(TransactionModel, AccountModel)
        .join(AccountModel, AccountModel.id == TransactionModel.account_id)
        .filter(TransactionModel.user_id == user.id, TransactionModel.kind == "income")
        .all()
    ):
        out.setdefault(account.name, []).append(round(row.amount, 2))
    return out


def in_ledger(db, user, on):
    occurrences = list_shifts(db, user.id, on, on)
    return occurrences[0].tip_in_ledger


# ------------------------------------------------------------ held by default

def test_with_no_account_chosen_a_cash_tip_is_held(db, user, job, cash, chequing):
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON)

    assert rows_by_account(db, user) == {}, "a tip with nowhere chosen must not reach the budget"
    assert in_ledger(db, user, MON) is False
    record = db.query(ShiftRecordModel).one()
    assert record.tip_amount == 40.0, "the tip is still recorded on the shift"


def test_with_an_account_chosen_the_whole_tip_lands_there_as_one_row(db, user, job, cash, chequing):
    set_cash_tip_account(db, user.id, cash.id)
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON)

    # One row, full amount, and Chequing -- which takes 100% of income -- untouched.
    assert rows_by_account(db, user) == {"Cash": [40.0]}
    assert in_ledger(db, user, MON) is True


def test_an_on_cheque_tip_never_writes_a_row(db, user, job, cash):
    set_cash_tip_account(db, user.id, cash.id)
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON, cash=False)

    assert rows_by_account(db, user) == {}


# ------------------------------------------------------ choosing files the held

def test_choosing_an_account_files_every_held_tip_and_says_how_many(db, user, job, cash, chequing):
    for on in (MON, TUE):
        tip(db, user, shift(db, user, job, on), on, amount=25.0)
    tip(db, user, shift(db, user, job, MON + datetime.timedelta(days=2)),
        MON + datetime.timedelta(days=2), amount=99.0, cash=False)  # on-cheque: not held, never filed

    filed = set_cash_tip_account(db, user.id, cash.id)

    assert filed == 2
    assert rows_by_account(db, user) == {"Cash": [25.0, 25.0]}
    assert in_ledger(db, user, MON) is True


def test_changing_the_account_leaves_tips_already_filed_where_they_are(db, user, job, cash, chequing):
    set_cash_tip_account(db, user.id, cash.id)
    tip(db, user, shift(db, user, job, MON), MON, amount=30.0)

    filed = set_cash_tip_account(db, user.id, chequing.id)
    tip(db, user, shift(db, user, job, TUE), TUE, amount=12.0)

    assert filed == 0, "nothing was held, so nothing is filed"
    assert rows_by_account(db, user) == {"Cash": [30.0], "Chequing": [12.0]}


# ------------------------------------------------------- tips from now on

def test_re_saving_a_shift_leaves_a_filed_tip_alone(db, user, job, cash, chequing):
    set_cash_tip_account(db, user.id, cash.id)
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON)
    before = {row.id for row in db.query(TransactionModel).all()}

    set_cash_tip_account(db, user.id, chequing.id)
    tip(db, user, event_id, MON)  # same tip: a re-save for the hours

    assert {row.id for row in db.query(TransactionModel).all()} == before
    assert rows_by_account(db, user) == {"Cash": [40.0]}


def test_a_legacy_split_tip_survives_a_re_save_untouched(db, user, job, cash, chequing):
    """Tips written by the old rule are a group of split rows. They stay."""
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON, amount=40.0)  # held: nothing chosen
    record = db.query(ShiftRecordModel).one()
    group = uuid.uuid4()
    legacy = [
        TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id,
                         kind="income", amount=amount, description="Cafe tips",
                         occurred_on=MON, group_id=group)
        for account, amount in ((chequing, 28.0), (cash, 12.0))
    ]
    db.add_all(legacy)
    db.flush()
    record.tip_transaction_id = legacy[0].id
    db.commit()

    tip(db, user, event_id, MON, amount=40.0)

    assert sorted(row.id for row in db.query(TransactionModel).all()) == sorted(r.id for r in legacy)


def test_changing_the_amount_rewrites_it_into_the_current_account(db, user, job, cash, chequing):
    set_cash_tip_account(db, user.id, cash.id)
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON, amount=40.0)

    set_cash_tip_account(db, user.id, chequing.id)
    tip(db, user, event_id, MON, amount=55.0)

    assert rows_by_account(db, user) == {"Chequing": [55.0]}, "the old row goes, not just the new one arrives"


def test_changing_the_amount_with_no_account_holds_it_and_removes_the_old_row(db, user, job, cash):
    set_cash_tip_account(db, user.id, cash.id)
    event_id = shift(db, user, job, MON)
    tip(db, user, event_id, MON, amount=40.0)

    set_cash_tip_account(db, user.id, None)
    tip(db, user, event_id, MON, amount=55.0)

    assert rows_by_account(db, user) == {}
    assert in_ledger(db, user, MON) is False


# ------------------------------------------------------ the account goes away

def test_an_archived_account_holds_new_tips(db, user, job, cash):
    set_cash_tip_account(db, user.id, cash.id)
    cash.archived = True
    db.commit()

    tip(db, user, shift(db, user, job, MON), MON)

    assert rows_by_account(db, user) == {}
    assert in_ledger(db, user, MON) is False


def test_a_deleted_account_holds_new_tips(db, user, job, cash, chequing):
    set_cash_tip_account(db, user.id, cash.id)
    delete_account(db, user.id, cash.id)  # allowed: it holds no transactions

    tip(db, user, shift(db, user, job, MON), MON)

    assert rows_by_account(db, user) == {}


def test_choosing_an_archived_account_is_refused_and_writes_nothing(db, user, job, cash):
    tip(db, user, shift(db, user, job, MON), MON)
    cash.archived = True
    db.commit()

    assert set_cash_tip_account(db, user.id, cash.id) is None
    db.refresh(user)
    assert (user.preferences or {}).get("cash_tip_account_id") is None
    assert rows_by_account(db, user) == {}


# ------------------------------------------------------------- through the app

@pytest.fixture
def client(db, user):
    import app.main

    user.auth_provider = "local"
    db.commit()
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    with TestClient(app.main.app) as test_client:
        yield test_client
    app.main.app.dependency_overrides.clear()


def test_the_route_chooses_files_and_reports(db, user, job, cash, client):
    tip(db, user, shift(db, user, job, MON), MON)

    response = client.put(f"/api/jobs/{user.id}/cash-tip-account", json={"account_id": str(cash.id)})

    assert response.status_code == 200
    assert response.json() == {"account_id": str(cash.id), "filed": 1}
    assert client.get("/api/users/me").json()["preferences"]["cash_tip_account_id"] == str(cash.id)


def test_the_route_refuses_someone_elses_account_and_writes_nothing(db, user, job, client):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_account(db, stranger.id, "Their cash", share=0.0)
    tip(db, user, shift(db, user, job, MON), MON)

    response = client.put(f"/api/jobs/{user.id}/cash-tip-account", json={"account_id": str(theirs.id)})

    assert response.status_code == 404
    db.refresh(user)
    assert (user.preferences or {}).get("cash_tip_account_id") is None
    assert db.query(TransactionModel).count() == 0


def test_the_route_clears_with_null(db, user, cash, client):
    set_cash_tip_account(db, user.id, cash.id)

    response = client.put(f"/api/jobs/{user.id}/cash-tip-account", json={"account_id": None})

    assert response.status_code == 200
    assert response.json() == {"account_id": None, "filed": 0}
    db.refresh(user)
    assert user.preferences["cash_tip_account_id"] is None


def test_the_generic_preferences_save_cannot_set_it(db, user, cash, client):
    # It has a side effect and an ownership check; only the route above sets it.
    client.patch(f"/api/users/{user.id}", json={"preferences": {"cash_tip_account_id": str(cash.id)}})

    db.refresh(user)
    assert (user.preferences or {}).get("cash_tip_account_id") is None
