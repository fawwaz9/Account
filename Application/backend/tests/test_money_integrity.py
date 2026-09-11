"""Regression tests for the ledger bugs found in Ideas/audit.md.

Each one fails against the code as it was when the audit was written. They exist
because these are the defects most likely to be reintroduced by a later refactor:
group_id means two different things, and only these tests say which.
"""
from datetime import date

import pytest

from app.Finances.schemas.deposit import DepositAllocation, DepositCreate
from app.Finances.schemas.transaction import (
    TransactionCreate,
    TransactionKind,
    TransactionUpdate,
    TransferCreate,
)
from app.Finances.services.deposit_service import record_deposit
from app.Finances.services.transaction_service import (
    create_transaction,
    create_transfer,
    delete_transaction,
    list_transactions,
    update_transaction,
)
from conftest import make_account, make_category, make_user

TODAY = date(2026, 9, 1)


def three_way_deposit(db, user):
    accounts = [make_account(db, user.id, name) for name in ("Spending", "Savings", "Invest")]
    record_deposit(db, user.id, DepositCreate(
        amount=600.0,
        occurred_on=TODAY,
        description="Paycheque",
        allocations=[DepositAllocation(account_id=a.id, amount=200.0) for a in accounts],
    ))
    return accounts


# ----------------------------------------------------------------- deleting --

def test_deleting_one_deposit_leg_leaves_the_others(db, user):
    """audit #3: group deletion treated a deposit like a transfer and took all of it."""
    three_way_deposit(db, user)
    rows = list_transactions(db, user.id)
    assert len(rows) == 3

    delete_transaction(db, user.id, rows[0].id, scope="row")

    assert len(list_transactions(db, user.id)) == 2


def test_deleting_a_deposit_with_group_scope_takes_all_of_it(db, user):
    three_way_deposit(db, user)
    rows = list_transactions(db, user.id)

    delete_transaction(db, user.id, rows[0].id, scope="group")

    assert list_transactions(db, user.id) == []


def test_deleting_half_a_transfer_always_removes_both(db, user):
    """Half a transfer is not a thing -- scope must not be able to leave one leg."""
    source = make_account(db, user.id, "From")
    target = make_account(db, user.id, "To")
    create_transfer(db, user.id, TransferCreate(
        amount=50.0, occurred_on=TODAY, description="move", 
        from_account_id=source.id, to_account_id=target.id,
    ))
    rows = list_transactions(db, user.id)
    assert len(rows) == 2

    delete_transaction(db, user.id, rows[0].id, scope="row")

    assert list_transactions(db, user.id) == []


# ----------------------------------------------------------------- updating --

def test_editing_a_deposit_leg_does_not_touch_its_siblings(db, user):
    """audit #4: the partner sync negated a sibling, creating negative income."""
    three_way_deposit(db, user)
    rows = sorted(list_transactions(db, user.id), key=lambda r: str(r.id))

    update_transaction(db, user.id, rows[0].id, TransactionUpdate(amount=250.0))

    after = list_transactions(db, user.id)
    assert sorted(r.signed_amount for r in after) == [200.0, 200.0, 250.0]
    assert all(r.signed_amount > 0 for r in after), "income must never go negative"


def test_editing_a_transfer_date_moves_both_halves(db, user):
    """audit #8: the carry-over was nested inside the amount branch."""
    source = make_account(db, user.id, "From")
    target = make_account(db, user.id, "To")
    create_transfer(db, user.id, TransferCreate(
        amount=50.0, occurred_on=TODAY, description="move",
        from_account_id=source.id, to_account_id=target.id,
    ))
    rows = list_transactions(db, user.id)

    update_transaction(db, user.id, rows[0].id, TransactionUpdate(occurred_on=date(2026, 10, 5)))

    assert {r.occurred_on for r in list_transactions(db, user.id)} == {date(2026, 10, 5)}


def test_editing_a_transfer_amount_still_mirrors_the_other_leg(db, user):
    source = make_account(db, user.id, "From")
    target = make_account(db, user.id, "To")
    create_transfer(db, user.id, TransferCreate(
        amount=50.0, occurred_on=TODAY, description="move",
        from_account_id=source.id, to_account_id=target.id,
    ))
    rows = list_transactions(db, user.id)

    update_transaction(db, user.id, rows[0].id, TransactionUpdate(amount=75.0))

    assert sorted(r.signed_amount for r in list_transactions(db, user.id)) == [-75.0, 75.0]


# ------------------------------------------------------------- group_size --

def test_group_size_counts_the_siblings(db, user):
    three_way_deposit(db, user)
    assert {r.group_size for r in list_transactions(db, user.id)} == {3}


def test_group_size_is_one_for_a_standalone_row(db, user):
    account = make_account(db, user.id, "Spending")
    create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.EXPENSE, account_id=account.id,
        amount=10.0, occurred_on=TODAY, description="coffee",
    ))
    assert [r.group_size for r in list_transactions(db, user.id)] == [1]


# ------------------------------------------------------------ cross-tenant --

def test_cannot_attach_another_users_category(db, user):
    """audit #7: category_id was trusted from the client without an ownership check."""
    other = make_user(db, "other@example.com")
    theirs = make_category(db, other.id, "Theirs")
    account = make_account(db, user.id, "Spending")

    with pytest.raises(ValueError):
        create_transaction(db, user.id, TransactionCreate(
            kind=TransactionKind.EXPENSE, account_id=account.id, amount=10.0,
            occurred_on=TODAY, description="coffee", category_id=theirs.id,
        ))
