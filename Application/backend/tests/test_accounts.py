"""Creating, removing, and the two accounts the app cannot do without.

Deleting an account was already refused while it held history. What was missing
is the other kind of refusal: some accounts cannot go at all, because something
else reads them. Safe-to-spend sums spending accounts; losing the last one makes
it report $0.00 with no explanation, which is a wrong answer that looks exactly
like a right one.

The guard is by *role*, not by name -- "Spending" renamed to "Chequing" is still
the only spending account, and someone holding three of them may delete any two.
"""
import datetime
import uuid

import pytest

from app._database.models import TransactionModel
from app.Finances.schemas.account import AccountCreate, AccountKind, AccountUpdate
from app.Finances.services.account_service import (
    create_account,
    delete_account,
    get_accounts,
    update_account,
    would_orphan_role,
)
from app.Finances.services.safe_service import safe_to_spend
from tests.conftest import make_account

ANCHOR = datetime.date(2026, 10, 14)


def deposit(db, user, account, amount, on=ANCHOR):
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        kind="income", amount=amount, description="Opening", occurred_on=on,
    ))
    db.commit()


@pytest.fixture
def roles(db, user):
    """One of each protected kind, which is the state the guard defends."""
    return {
        "spending": make_account(db, user.id, "Chequing", kind="spending"),
        "savings": make_account(db, user.id, "Savings", kind="savings"),
    }


# --------------------------------------------------------- the last of a role --

@pytest.mark.parametrize("role", ["spending", "savings"])
def test_the_last_of_a_protected_role_cannot_be_deleted(db, user, roles, role):
    with pytest.raises(ValueError) as caught:
        delete_account(db, user.id, roles[role].id)

    # The refusal has to say what depends on it, or it reads as an arbitrary no.
    assert roles[role].name in str(caught.value)
    assert role in str(caught.value)


@pytest.mark.parametrize("role", ["spending", "savings"])
def test_the_last_of_a_protected_role_cannot_be_archived(db, user, roles, role):
    with pytest.raises(ValueError):
        update_account(db, user.id, roles[role].id, AccountUpdate(archived=True))

    db.refresh(roles[role])
    assert roles[role].archived is False


@pytest.mark.parametrize("role", ["spending", "savings"])
def test_the_last_of_a_protected_role_cannot_be_re_kinded(db, user, roles, role):
    """The one that looks harmless.

    Changing the only spending account to "other" empties the role exactly as
    deleting it would, and nothing on screen would say so.
    """
    with pytest.raises(ValueError):
        update_account(db, user.id, roles[role].id, AccountUpdate(kind=AccountKind.OTHER))

    db.refresh(roles[role])
    assert roles[role].kind == role


def test_a_second_account_of_the_role_makes_the_first_removable(db, user, roles):
    make_account(db, user.id, "Everyday", kind="spending")

    removed = delete_account(db, user.id, roles["spending"].id)

    assert removed is not None


def test_an_archived_account_does_not_count_as_the_survivor(db, user, roles):
    """Archived accounts are not offered and are not what safe-to-spend reads."""
    make_account(db, user.id, "Old current account", kind="spending", archived=True)

    with pytest.raises(ValueError):
        delete_account(db, user.id, roles["spending"].id)


def test_an_already_archived_account_can_still_be_deleted(db, user, roles):
    """It left service when it was archived; removing it now changes nothing."""
    stale = make_account(db, user.id, "Closed account", kind="savings", archived=True)

    assert would_orphan_role(db, user.id, stale) is False
    assert delete_account(db, user.id, stale.id) is not None


def test_an_unprotected_kind_is_not_guarded(db, user, roles):
    """Only spending and savings are load-bearing. An only "other" may go."""
    lent = make_account(db, user.id, "Money Lent", kind="other")

    assert delete_account(db, user.id, lent.id) is not None


def test_renaming_does_not_lift_the_guard(db, user, roles):
    """Protection reads the kind, so it survives a rename."""
    update_account(db, user.id, roles["spending"].id, AccountUpdate(name="Current account"))

    with pytest.raises(ValueError):
        delete_account(db, user.id, roles["spending"].id)


def test_the_role_refusal_comes_before_the_history_one(db, user, roles):
    """Clearing transactions cannot lift this refusal, so it is said first.

    Being told to empty an account and then refused anyway is the wrong order
    to find that out in.
    """
    deposit(db, user, roles["spending"], 500.0)

    with pytest.raises(ValueError) as caught:
        delete_account(db, user.id, roles["spending"].id)

    assert "transactions" not in str(caught.value)


# ---------------------------------------------------------------- creating --

def test_creating_an_account_whose_name_differs_only_by_case_is_refused(db, user, roles):
    with pytest.raises(ValueError):
        create_account(db, user.id, AccountCreate(name="chequing", kind=AccountKind.OTHER))


def test_a_created_account_starts_at_a_zero_balance(db, user):
    created = create_account(db, user.id, AccountCreate(name="Travel", kind=AccountKind.SAVINGS))

    assert created.balance == 0.0


# -------------------------------------------------------------------- debt --

def test_a_debt_account_is_not_spendable(db, user, roles):
    """`SPENDABLE_KINDS` is spending only, so debt is excluded without a rule."""
    deposit(db, user, roles["spending"], 1500.0)
    card = make_account(db, user.id, "Visa", kind="debt")
    deposit(db, user, card, -1000.0)

    figure = safe_to_spend(db, user.id, on_day=ANCHOR)

    names = [entry.name for entry in figure.accounts]
    assert "Visa" not in names
    assert figure.spendable == pytest.approx(1500.0, abs=0.011)


def test_a_debt_balance_does_not_inflate_safe_to_spend(db, user, roles):
    """The sign is the whole design: a negative balance must not be subtracted
    a second time, and must not be counted as money to spend either."""
    deposit(db, user, roles["spending"], 1500.0)
    card = make_account(db, user.id, "Visa", kind="debt")
    deposit(db, user, card, -1000.0)

    figure = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert figure.safe_now == pytest.approx(1500.0, abs=0.011)


# ------------------------------------------------------- the flag the UI reads --

def locks(db, user):
    return {account.name: account.role_locked for account in get_accounts(db, user.id)}


def test_the_only_account_of_a_role_is_flagged_locked(db, user, roles):
    flags = locks(db, user)

    assert flags["Chequing"] is True
    assert flags["Savings"] is True


def test_a_second_account_of_the_role_clears_the_lock_on_both(db, user, roles):
    make_account(db, user.id, "Everyday", kind="spending")

    flags = locks(db, user)

    assert flags["Chequing"] is False
    assert flags["Everyday"] is False
    # Savings is untouched: the roles are counted apart.
    assert flags["Savings"] is True


def test_an_unprotected_kind_is_never_locked(db, user, roles):
    make_account(db, user.id, "Money Lent", kind="other")

    assert locks(db, user)["Money Lent"] is False


def test_the_flag_agrees_with_what_the_service_actually_refuses(db, user, roles):
    """The flag exists to grey out a control. If it disagreed with the guard,
    the UI would either offer an action that fails or hide one that works."""
    for account in get_accounts(db, user.id):
        if account.role_locked:
            with pytest.raises(ValueError):
                delete_account(db, user.id, account.id)
