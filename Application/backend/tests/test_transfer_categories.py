"""Transfers carry a category (Phase 4 D27), on SQLite and Postgres.

The promises: both legs hold the category and move together when either is
edited; only the outgoing leg counts in a category's spending, on the account
page and the budget page; a transfer with no category is in no category row; a
recurring transfer writes it; and the spending guard, the categoriser and the
shared merchant map still learn from expenses alone.
"""
from datetime import date

import pytest

from app._database import aggregates
from app.Calendar.schemas.event import Recurrence
from app.Finances.schemas.budget import AccountCategoryLimitUpsert
from app.Finances.schemas.recurring import RecurringCreate, RecurringUpdate
from app.Finances.schemas.transaction import TransactionCreate, TransactionKind, TransactionUpdate, TransferCreate
from app.Finances.services.activity_service import counts_in_category, get_account_activity
from app.Finances.services.budget_service import delete_category, get_budget_summary, set_account_category_limit
from app.Finances.services.categorize_service import Categorizer
from app.Finances.services.recurring_service import create_rule, run_due, update_rule
from app.Finances.services.transaction_service import (
    create_transaction,
    create_transfer,
    list_transactions,
    update_transaction,
)
from conftest import make_account, make_category, make_user

DAY = date(2026, 10, 6)


@pytest.fixture
def pots(db, user):
    """Chequing and Savings, and the Savings and Rent categories."""
    return (
        make_account(db, user.id, "Chequing"),
        make_account(db, user.id, "Savings"),
        make_category(db, user.id, "Savings"),
        make_category(db, user.id, "Rent"),
    )


def move(db, user, source, target, amount=200.0, category=None, description="Top-up"):
    return create_transfer(db, user.id, TransferCreate(
        amount=amount, occurred_on=DAY, description=description,
        from_account_id=source.id, to_account_id=target.id,
        category_id=category.id if category else None,
    ))


def by_category(rows):
    return {row.category_name: row.actual for row in rows}


# ------------------------------------------------------------------ the legs --

def test_both_legs_hold_the_category(db, user, pots):
    chequing, savings, saving, _ = pots

    legs = move(db, user, chequing, savings, category=saving)

    assert {leg.category_id for leg in legs} == {saving.id}
    assert {row.category_id for row in list_transactions(db, user.id)} == {saving.id}


def test_a_transfer_still_needs_no_category(db, user, pots):
    chequing, savings, _, _ = pots

    legs = move(db, user, chequing, savings)

    assert [leg.category_id for leg in legs] == [None, None]


def test_another_users_category_is_refused(db, user, pots):
    chequing, savings, _, _ = pots
    theirs = make_category(db, make_user(db, "stranger@example.com").id, "Theirs")

    with pytest.raises(ValueError, match="category does not exist"):
        move(db, user, chequing, savings, category=theirs)
    assert list_transactions(db, user.id) == []


@pytest.mark.parametrize("leg", [0, 1], ids=["outgoing", "incoming"])
def test_editing_either_legs_category_moves_both(db, user, pots, leg):
    chequing, savings, saving, rent = pots
    legs = move(db, user, chequing, savings, category=saving)

    update_transaction(db, user.id, legs[leg].id, TransactionUpdate(category_id=rent.id))

    assert {row.category_id for row in list_transactions(db, user.id)} == {rent.id}


def test_clearing_the_category_clears_both(db, user, pots):
    chequing, savings, saving, _ = pots
    legs = move(db, user, chequing, savings, category=saving)

    update_transaction(db, user.id, legs[1].id, TransactionUpdate(category_id=None))

    assert {row.category_id for row in list_transactions(db, user.id)} == {None}


def test_an_edit_that_leaves_the_category_out_keeps_it(db, user, pots):
    chequing, savings, saving, _ = pots
    legs = move(db, user, chequing, savings, category=saving)

    update_transaction(db, user.id, legs[0].id, TransactionUpdate(description="Moved"))

    assert {row.category_id for row in list_transactions(db, user.id)} == {saving.id}


def test_deleting_the_category_clears_both_legs(db, user, pots):
    chequing, savings, saving, _ = pots
    move(db, user, chequing, savings, category=saving)

    delete_category(db, user.id, saving.id)

    assert {row.category_id for row in list_transactions(db, user.id)} == {None}


# -------------------------------------------------------------- what counts --

def test_the_rule():
    category = object()
    assert counts_in_category(TransactionKind.EXPENSE.value, -5.0, None)
    assert counts_in_category(TransactionKind.TRANSFER.value, -5.0, category)
    assert not counts_in_category(TransactionKind.TRANSFER.value, 5.0, category)
    assert not counts_in_category(TransactionKind.TRANSFER.value, -5.0, None)
    assert not counts_in_category(TransactionKind.INCOME.value, 5.0, category)


def test_the_account_page_counts_the_outgoing_leg_against_its_limit(db, user, pots):
    chequing, savings, saving, _ = pots
    set_account_category_limit(db, user.id, AccountCategoryLimitUpsert(
        account_id=chequing.id, category_id=saving.id, limit_amount=300.0,
    ))
    move(db, user, chequing, savings, category=saving)

    activity = get_account_activity(db, user.id, chequing.id, DAY)

    (row,) = activity.by_category
    assert (row.category_name, row.actual, row.limit, row.remaining) == ("Savings", 200.0, 300.0, 100.0)
    # The breakdown now adds up to the money out.
    assert sum(r.actual for r in activity.by_category) == activity.total_out


def test_the_receiving_account_counts_nothing(db, user, pots):
    chequing, savings, saving, _ = pots
    move(db, user, chequing, savings, category=saving)

    assert get_account_activity(db, user.id, savings.id, DAY).by_category == []


def test_an_uncategorised_transfer_is_in_no_category_row(db, user, pots):
    chequing, savings, _, rent = pots
    move(db, user, chequing, savings)
    create_transaction(db, user.id, TransactionCreate(
        kind="expense", account_id=chequing.id, amount=900.0, occurred_on=DAY, category_id=rent.id,
    ))

    assert by_category(get_account_activity(db, user.id, chequing.id, DAY).by_category) == {"Rent": 900.0}
    assert by_category(get_budget_summary(db, user.id, DAY).by_category) == {"Rent": 900.0}


def test_the_budget_page_counts_a_categorised_transfer_once(db, user, pots):
    chequing, savings, saving, rent = pots
    move(db, user, chequing, savings, category=saving)
    create_transaction(db, user.id, TransactionCreate(
        kind="expense", account_id=chequing.id, amount=900.0, occurred_on=DAY, category_id=rent.id,
    ))

    assert by_category(get_budget_summary(db, user.id, DAY).by_category) == {"Rent": 900.0, "Savings": 200.0}


# ----------------------------------------------------------------- recurring --

def monthly_transfer(source, target, category):
    return RecurringCreate(
        kind="transfer", amount=150.0, description="To savings", starts_on=DAY,
        account_id=source.id, to_account_id=target.id, category_id=category.id,
        recurrence=Recurrence(freq="monthly", interval=1, byday=[], until=None, count=None),
    )


def test_a_recurring_transfer_writes_categorised_legs(db, user, pots):
    chequing, savings, saving, _ = pots
    create_rule(db, user.id, monthly_transfer(chequing, savings, saving))

    run_due(db, user.id, through=DAY)

    rows = list_transactions(db, user.id)
    assert len(rows) == 2
    assert {row.category_id for row in rows} == {saving.id}


def test_a_recurring_transfers_category_can_be_changed(db, user, pots):
    chequing, savings, saving, rent = pots
    rule = create_rule(db, user.id, monthly_transfer(chequing, savings, saving))

    assert update_rule(db, user.id, rule.id, RecurringUpdate(category_id=rent.id)).category_id == rent.id


def test_recurring_income_still_takes_no_category(db, user, pots):
    chequing, _, saving, _ = pots
    with pytest.raises(ValueError, match="Only an expense or a transfer"):
        RecurringCreate(
            kind="income", amount=1.0, starts_on=DAY, account_id=chequing.id, category_id=saving.id,
            recurrence=Recurrence(freq="monthly", interval=1, byday=[], until=None, count=None),
        )


# ---------------------------------------------- left to expenses on purpose --

def test_the_categoriser_learns_nothing_from_a_transfer(db, user, pots):
    chequing, savings, saving, _ = pots
    for _ in range(3):
        move(db, user, chequing, savings, category=saving, description="Chequing to Savings")

    assert Categorizer(db, user.id).trained == 0


def test_a_transfer_casts_no_merchant_vote(db):
    for n in range(3):
        person = make_user(db, f"mover{n}@example.com")
        source, target = make_account(db, person.id, "Chequing"), make_account(db, person.id, "Savings")
        move(db, person, source, target, category=make_category(db, person.id, "Coffee"),
             description="BLENZ COFFEE #1234")

    assert aggregates.recount_merchant_categories(db) == 0
