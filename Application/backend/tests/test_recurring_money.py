"""Standing instructions, and the rules about when a payment becomes real.

The dangerous property here is not the recurrence -- that engine is already
tested -- it is that money must be written exactly once. A catch-up that runs
twice, or a projection that leaks into a balance, is a wrong number in the one
place the app cannot be wrong about.
"""
from datetime import date, timedelta

import pytest

from app._database.models import RecurringTransactionModel, TransactionModel
from app.Calendar.schemas.event import Recurrence
from app.Finances.schemas.recurring import RecurringCreate, RecurringUpdate
from app.Finances.services.account_service import get_accounts
from app.Finances.services.recurring_service import (
    create_rule,
    delete_rule,
    list_rules,
    run_due,
    skip_occurrence,
    upcoming,
    update_rule,
)
from app.Finances.services.transaction_service import list_transactions
from conftest import make_account, make_category, make_user, sqlite_only

START = date(2026, 1, 1)
#: Far enough past the start that several monthly payments are owed.
MARCH = date(2026, 3, 15)


def monthly(**overrides):
    fields = {
        "kind": "expense",
        "amount": 1500.0,
        "description": "Rent",
        "starts_on": START,
        "recurrence": Recurrence(freq="monthly", interval=1, byday=[], until=None, count=None),
    }
    fields.update(overrides)
    return RecurringCreate(**fields)


def balance_of(db, user, account_id) -> float:
    rows = list_transactions(db, user.id, account_id=account_id, limit=500)
    return round(sum(row.signed_amount for row in rows), 2)


# ------------------------------------------------------------ materialising --

def test_a_due_instruction_writes_its_payments(db, user):
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    result = run_due(db, user.id, through=MARCH)

    # January, February and March are owed; April is not.
    assert result.created == 3
    assert [row.occurred_on for row in result.transactions] == [
        date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
    ]


def test_running_twice_does_not_pay_twice(db, user):
    """The property the whole design rests on: (rule, date) is written once."""
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    run_due(db, user.id, through=MARCH)
    second = run_due(db, user.id, through=MARCH)

    assert second.created == 0
    assert db.query(TransactionModel).count() == 3
    assert balance_of(db, user, account.id) == -4500.0


def test_a_later_run_writes_only_what_is_newly_owed(db, user):
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))
    run_due(db, user.id, through=date(2026, 2, 15))

    later = run_due(db, user.id, through=date(2026, 4, 15))

    assert later.created == 2
    assert [row.occurred_on for row in later.transactions] == [date(2026, 3, 1), date(2026, 4, 1)]


def test_an_expense_leaves_the_account(db, user):
    """Signing goes through the ordinary money path, so it cannot drift from it."""
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    run_due(db, user.id, through=date(2026, 1, 15))

    assert balance_of(db, user, account.id) == -1500.0


def test_recurring_income_arrives(db, user):
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(kind="income", amount=800.0, description="Stipend", account_id=account.id))

    run_due(db, user.id, through=date(2026, 1, 15))

    assert balance_of(db, user, account.id) == 800.0


def test_an_inactive_instruction_is_not_charged(db, user):
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id, active=False))

    assert run_due(db, user.id, through=MARCH).created == 0


def test_pausing_stops_future_payments_but_keeps_past_ones(db, user):
    account = make_account(db, user.id, "Spending")
    rule = create_rule(db, user.id, monthly(account_id=account.id))
    run_due(db, user.id, through=date(2026, 1, 15))

    update_rule(db, user.id, rule.id, RecurringUpdate(active=False))

    assert run_due(db, user.id, through=MARCH).created == 0
    assert db.query(TransactionModel).count() == 1


def test_a_skipped_month_is_not_charged(db, user):
    account = make_account(db, user.id, "Spending")
    rule = create_rule(db, user.id, monthly(account_id=account.id))

    skip_occurrence(db, user.id, rule.id, date(2026, 2, 1))
    result = run_due(db, user.id, through=MARCH)

    assert [row.occurred_on for row in result.transactions] == [date(2026, 1, 1), date(2026, 3, 1)]


def test_the_catchup_does_not_reach_back_forever(db, user):
    """A rule left alone over a summer must not write a year of rent at once."""
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    result = run_due(db, user.id, through=date(2027, 1, 1))

    # A 120-day catch-up window, not the whole twelve months since the start.
    assert result.created == 4
    assert min(row.occurred_on for row in result.transactions) >= date(2026, 9, 1)


# ---------------------------------------------------- the other three kinds --

def test_a_recurring_transfer_writes_both_legs(db, user):
    spending = make_account(db, user.id, "Spending")
    savings = make_account(db, user.id, "Savings")
    create_rule(db, user.id, monthly(
        kind="transfer", amount=200.0, description="To savings",
        account_id=spending.id, to_account_id=savings.id,
    ))

    run_due(db, user.id, through=date(2026, 1, 15))

    assert balance_of(db, user, spending.id) == -200.0
    assert balance_of(db, user, savings.id) == 200.0


def test_a_recurring_deposit_splits_by_income_share(db, user):
    spending = make_account(db, user.id, "Spending", share=75.0)
    savings = make_account(db, user.id, "Savings", share=25.0)
    create_rule(db, user.id, monthly(
        kind="deposit", amount=1000.0, description="Paycheque", account_id=None,
    ))

    run_due(db, user.id, through=date(2026, 1, 15))

    assert balance_of(db, user, spending.id) == 750.0
    assert balance_of(db, user, savings.id) == 250.0


def test_a_recurring_expense_keeps_its_category(db, user):
    account = make_account(db, user.id, "Spending")
    category = make_category(db, user.id, "Subscriptions")
    create_rule(db, user.id, monthly(
        amount=11.99, description="Spotify", account_id=account.id, category_id=category.id,
    ))

    result = run_due(db, user.id, through=date(2026, 1, 15))

    assert result.transactions[0].category_id == category.id


# ------------------------------------------------------------- projections --

def test_upcoming_never_writes_anything(db, user):
    """A projection is not money that moved, and must not reach the ledger."""
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    charges = upcoming(db, user.id, date(2026, 6, 1), date(2026, 8, 31))

    assert len(charges) == 3
    assert db.query(TransactionModel).count() == 0
    assert balance_of(db, user, account.id) == 0.0


def test_upcoming_signs_money_leaving_as_negative(db, user):
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    [charge] = upcoming(db, user.id, date(2026, 6, 1), date(2026, 6, 30))

    assert charge.signed_amount == -1500.0
    assert charge.account_name == "Spending"


def test_a_payment_already_made_is_not_also_upcoming(db, user):
    """Otherwise a commitment would be counted twice: once paid, once owed."""
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))
    run_due(db, user.id, through=date(2026, 1, 15))

    charges = upcoming(db, user.id, date(2026, 1, 1), date(2026, 1, 31))

    assert charges == []


def test_an_over_long_projection_is_refused(db, user):
    with pytest.raises(ValueError, match="longer than"):
        upcoming(db, user.id, date(2026, 1, 1), date(2028, 1, 1))


# ------------------------------------------------------------- bookkeeping --

def test_deleting_an_instruction_keeps_the_money_it_moved(db, user):
    """The rent really was paid; forgetting the rule must not rewrite that."""
    account = make_account(db, user.id, "Spending")
    rule = create_rule(db, user.id, monthly(account_id=account.id))
    run_due(db, user.id, through=MARCH)

    delete_rule(db, user.id, rule.id)

    assert db.query(RecurringTransactionModel).count() == 0
    assert db.query(TransactionModel).count() == 3
    assert balance_of(db, user, account.id) == -4500.0


@sqlite_only
def test_a_broken_rule_does_not_stop_the_others(db, user):
    """One instruction pointing at a gone account must not block the rest.

    The database now refuses to delete an account a rule still points at, so
    this state is no longer reachable through the app. It is still reachable in
    a database written *before* foreign keys were enforced, which is every
    SQLite database this project created until now -- so the defensive branch in
    `run_due` stays, and the only honest way to set the scenario up is to drop
    enforcement for the two statements that fabricate it.

    **SQLite only, and the reason is the point.** On Postgres this state cannot
    be fabricated at all: there is no per-connection switch for foreign keys,
    and no Postgres database of this app has ever existed without them. So the
    legacy row the defensive branch guards against can never appear there. The
    branch still earns its place while any SQLite file is still in use -- and
    once the move to Postgres is complete and no such file remains, this is a
    test, and a branch, that can be deleted outright.
    """
    good = make_account(db, user.id, "Spending")
    doomed = make_account(db, user.id, "Old")
    create_rule(db, user.id, monthly(amount=10.0, description="Good", account_id=good.id))
    create_rule(db, user.id, monthly(amount=20.0, description="Broken", account_id=doomed.id))

    db.query(TransactionModel).filter(TransactionModel.account_id == doomed.id).delete()
    db.commit()

    # Straight through the driver with enforcement off, which is the only way to
    # produce a row a pre-enforcement database could hold. The pragma goes back
    # on immediately: the fixture shares one connection, so leaving it off would
    # quietly disable foreign keys for the rest of the test.
    raw = db.get_bind().raw_connection()
    cursor = raw.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.execute("DELETE FROM accounts WHERE id = ?", (doomed.id.hex,))
    raw.commit()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    db.expire_all()

    result = run_due(db, user.id, through=date(2026, 1, 15))

    assert result.created == 1
    assert len(result.skipped) == 1
    assert "Broken" in result.skipped[0]


def test_the_next_due_date_is_reported(db, user):
    account = make_account(db, user.id, "Spending")
    create_rule(db, user.id, monthly(account_id=account.id))

    [rule] = list_rules(db, user.id)

    assert rule.next_due_on is not None
    assert rule.next_due_on.day == 1


# -------------------------------------------------------------- validation --

def test_a_transfer_needs_a_destination(db, user):
    account = make_account(db, user.id, "Spending")
    with pytest.raises(ValueError, match="somewhere to go"):
        monthly(kind="transfer", account_id=account.id)


def test_a_deposit_takes_no_single_account(db, user):
    account = make_account(db, user.id, "Spending")
    with pytest.raises(ValueError, match="splits across accounts"):
        monthly(kind="deposit", account_id=account.id)


def test_only_an_expense_carries_a_category(db, user):
    account = make_account(db, user.id, "Spending")
    category = make_category(db, user.id, "Subscriptions")
    with pytest.raises(ValueError, match="Only an expense"):
        monthly(kind="income", account_id=account.id, category_id=category.id)


def test_another_users_account_cannot_be_charged(db, user):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_account(db, stranger.id, "Theirs")

    with pytest.raises(ValueError, match="account does not exist"):
        create_rule(db, user.id, monthly(account_id=theirs.id))
