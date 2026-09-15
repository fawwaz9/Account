"""Editing the two things the budget page could not edit.

Both had complete server-side CRUD and no caller. What the tests below are
really defending is the pair of rules the new editors make reachable for the
first time: a category name that collides, and an income split that adds up to
nothing.
"""
import datetime
import uuid

import pytest

from app._database.models import AccountModel, TransactionModel
from app.Finances.schemas.budget import SpendCategoryCreate, SpendCategoryUpdate
from app.Finances.schemas.deposit import DepositCreate
from app.Finances.services.budget_service import (
    create_category,
    delete_category,
    get_categories,
    update_category,
)
from app.Finances.services.deposit_service import record_deposit, split_income
from tests.conftest import make_account, make_category

ANCHOR = datetime.date(2026, 10, 14)
CENT = 0.011


# ------------------------------------------------------------- categories --

def test_renaming_onto_an_existing_name_is_refused(db, user):
    make_category(db, user.id, "Groceries")
    other = make_category(db, user.id, "Transport")

    with pytest.raises(ValueError):
        update_category(db, user.id, other.id, SpendCategoryUpdate(name="groceries"))


def test_renaming_a_category_keeps_its_expenses_attached(db, user):
    """The label moves; the rows do not. Renaming is not re-filing."""
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Food")
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
        amount=-25.0, description="Lunch", occurred_on=ANCHOR, category_id=category.id,
    ))
    db.commit()

    update_category(db, user.id, category.id, SpendCategoryUpdate(name="Groceries"))

    row = db.query(TransactionModel).filter(TransactionModel.user_id == user.id).one()
    assert row.category_id == category.id


def test_deleting_a_category_keeps_the_expenses_and_uncategorises_them(db, user):
    """The money was still spent. Only the label goes."""
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Books")
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
        amount=-40.0, description="Textbook", occurred_on=ANCHOR, category_id=category.id,
    ))
    db.commit()

    delete_category(db, user.id, category.id)

    rows = db.query(TransactionModel).filter(TransactionModel.user_id == user.id).all()
    assert len(rows) == 1, "the expense should survive its category"
    assert rows[0].category_id is None


def test_archiving_a_category_leaves_the_default_list(db, user):
    keep = make_category(db, user.id, "Rent")
    gone = make_category(db, user.id, "Nights out")

    update_category(db, user.id, gone.id, SpendCategoryUpdate(archived=True))

    offered = {c.name for c in get_categories(db, user.id)}
    assert offered == {keep.name}
    # Still there, and still reachable when asked for -- archiving is not deleting.
    everything = {c.name for c in get_categories(db, user.id, include_archived=True)}
    assert everything == {"Rent", "Nights out"}


def test_creating_a_category_that_differs_only_by_case_is_refused(db, user):
    create_category(db, user.id, SpendCategoryCreate(name="Coffee"))

    with pytest.raises(ValueError):
        create_category(db, user.id, SpendCategoryCreate(name="COFFEE"))


# ----------------------------------------------------------- income split --

def shares(db, user, **by_name) -> list[AccountModel]:
    made = []
    for name, share in by_name.items():
        made.append(make_account(db, user.id, name, share=share))
    return made


def test_shares_need_not_total_one_hundred(db, user):
    """The rule the new editor must not quietly tighten: income divides by
    ratio, so 130 is as valid as 100."""
    accounts = shares(db, user, Spending=80.0, Savings=50.0)

    split = split_income(1300.0, accounts)

    assert sum(entry.amount for entry in split) == pytest.approx(1300.0, abs=CENT)
    assert split[0].amount == pytest.approx(800.0, abs=CENT)
    assert split[1].amount == pytest.approx(500.0, abs=CENT)


def test_a_deposit_always_equals_the_sum_of_its_own_rows(db, user):
    """The silent one.

    Rounding three ways leaves a remainder. If it is dropped, the ledger gains
    a deposit whose parts do not add up to it -- money invented or lost, with
    nothing on screen to say so. The drift lands on the largest share.
    """
    accounts = shares(db, user, A=33.3, B=33.3, C=33.4)

    for amount in (0.01, 0.07, 10.00, 999.99, 1234.56):
        split = split_income(amount, accounts)
        assert sum(entry.amount for entry in split) == pytest.approx(amount, abs=CENT), (
            f"{amount} split into {[e.amount for e in split]}"
        )


def test_a_split_with_no_shares_is_refused_rather_than_silently_dropped(db, user):
    """Reachable for the first time now that every share can be zeroed at once."""
    shares(db, user, Spending=0.0, Savings=0.0)

    with pytest.raises(ValueError) as caught:
        record_deposit(db, user.id, DepositCreate(
            amount=500.0, description="Pay", occurred_on=ANCHOR))

    assert "share" in str(caught.value).lower()
    assert db.query(TransactionModel).filter(TransactionModel.user_id == user.id).count() == 0


def test_an_archived_account_takes_no_share_of_income(db, user):
    live = make_account(db, user.id, "Spending", share=50.0)
    make_account(db, user.id, "Old account", share=50.0, archived=True)

    rows = record_deposit(db, user.id, DepositCreate(
        amount=400.0, description="Pay", occurred_on=ANCHOR))

    assert len(rows) == 1
    assert rows[0].account_id == live.id
    assert rows[0].amount == pytest.approx(400.0, abs=CENT)


def test_renaming_to_an_exact_duplicate_is_a_refusal_not_a_500(db, user):
    """The unique index would raise IntegrityError at commit, which escapes the
    route's ValueError handler and reaches the client as a 500. The service
    check has to catch it first."""
    make_category(db, user.id, "Groceries")
    other = make_category(db, user.id, "Transport")

    with pytest.raises(ValueError):
        update_category(db, user.id, other.id, SpendCategoryUpdate(name="Groceries"))

    # The session is still usable: a failed rename must not poison it.
    assert {c.name for c in get_categories(db, user.id)} == {"Groceries", "Transport"}


def test_a_category_can_still_be_renamed_to_its_own_name(db, user):
    """The clash check excludes the row being edited, or saving an unchanged
    form would refuse itself."""
    category = make_category(db, user.id, "Groceries")

    updated = update_category(db, user.id, category.id, SpendCategoryUpdate(name="Groceries"))

    assert updated is not None


def test_changing_only_the_archive_flag_does_not_trip_the_name_check(db, user):
    make_category(db, user.id, "Groceries")
    other = make_category(db, user.id, "Transport")

    updated = update_category(db, user.id, other.id, SpendCategoryUpdate(archived=True))

    assert updated.archived is True
