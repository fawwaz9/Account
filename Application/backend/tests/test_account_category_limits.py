"""Where an account's target comes from, and the zero that decides it."""

from app.Finances.utils.limits import planned_for_account


def test_an_account_with_no_category_limits_keeps_its_manual_target():
    """The case that protects real data.

    Savings carries a $9,000 target and Money Lent $1,200; neither would ever be
    itemised by category. Deriving unconditionally would report both as
    budgeting nothing.
    """
    assert planned_for_account([], 9000.0) == (9000.0, False)


def test_an_account_with_limits_derives_its_target_from_them():
    assert planned_for_account([400.0, 150.0, 50.0], 10000.0) == (600.0, True)


def test_a_single_limit_of_zero_still_derives():
    """The falsy-check bug, in its account-level form.

    One limit of 0 means "nothing is meant to leave this account". `if
    sum(limits):` is false for that and would fall through to the manual target,
    reporting a deliberately closed account as merely unbudgeted -- on the
    account somebody cared enough about to close.
    """
    assert planned_for_account([0.0], 10000.0) == (0.0, True)


def test_limits_that_happen_to_sum_to_zero_still_derive():
    """Two categories at zero are still a budget, and still not the manual one."""
    assert planned_for_account([0.0, 0.0], 500.0) == (0.0, True)


def test_the_derived_total_is_rounded_to_cents():
    """Floats are floats. 0.1 + 0.2 must not reach the client as 0.30000000000000004."""
    assert planned_for_account([0.1, 0.2], 0.0) == (0.3, True)


def test_the_flag_says_which_answer_was_given():
    """Returned together so no caller can take the figure and describe it wrongly."""
    assert planned_for_account([], 5.0)[1] is False
    assert planned_for_account([5.0], 0.0)[1] is True


# ---------------------------------------------------------- through the services --

import uuid
from datetime import date

from app._database.models import (
    AccountCategoryLimitModel,
    BudgetTargetModel,
    TransactionModel,
)
from app.Finances.schemas.budget import AccountCategoryLimitUpsert
from app.Finances.services.account_service import delete_account
from app.Finances.services.activity_service import get_account_activity
from app.Finances.services.budget_service import (
    delete_category,
    get_budget_summary,
    set_account_category_limit,
)
from tests.conftest import make_account, make_category, make_user

ANCHOR = date(2026, 3, 14)
MONTH = date(2026, 3, 1)


def set_limit(db, user, account, category, amount):
    return set_account_category_limit(db, user.id, AccountCategoryLimitUpsert(
        account_id=account.id, category_id=category.id, limit_amount=amount,
    ))


def target(db, user, account, amount):
    db.add(BudgetTargetModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        month=MONTH, planned_amount=amount,
    ))
    db.commit()


def spend(db, user, account, category, amount):
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
        amount=-amount, description="Spent", occurred_on=ANCHOR,
        category_id=category.id if category else None,
    ))
    db.commit()


def row_for(rows, name):
    return next(r for r in rows if r.category_name == name)


def test_an_account_without_limits_keeps_the_target_that_was_typed(db, user):
    """The Savings case, which is why the rule is conditional at all."""
    savings = make_account(db, user.id, "Savings", kind="savings")
    target(db, user, savings, 9000.0)

    activity = get_account_activity(db, user.id, savings.id, MONTH)

    assert activity.planned == 9000.0
    assert activity.planned_is_derived is False


def test_an_account_with_limits_derives_its_target_from_them(db, user):
    account = make_account(db, user.id, "Chequing")
    target(db, user, account, 10000.0)
    food = make_category(db, user.id, "Food")
    books = make_category(db, user.id, "Books")
    set_limit(db, user, account, food, 400.0)
    set_limit(db, user, account, books, 150.0)

    activity = get_account_activity(db, user.id, account.id, MONTH)

    assert activity.planned == 550.0, "not the 10000 typed into Planned spend"
    assert activity.planned_is_derived is True


def test_the_budget_page_reports_the_same_target_as_the_account_page(db, user):
    """Two screens, one rule. If these disagree the app contradicts itself."""
    account = make_account(db, user.id, "Chequing")
    target(db, user, account, 10000.0)
    set_limit(db, user, account, make_category(db, user.id, "Food"), 400.0)

    activity = get_account_activity(db, user.id, account.id, MONTH)
    summary = get_budget_summary(db, user.id, MONTH)
    entry = next(e for e in summary.accounts if e.account_id == account.id)

    assert entry.planned == activity.planned == 400.0
    assert entry.planned_is_derived is True


def test_clearing_the_last_limit_returns_the_account_to_its_typed_target(db, user):
    account = make_account(db, user.id, "Chequing")
    target(db, user, account, 10000.0)
    food = make_category(db, user.id, "Food")
    set_limit(db, user, account, food, 400.0)

    set_limit(db, user, account, food, None)

    activity = get_account_activity(db, user.id, account.id, MONTH)
    assert activity.planned == 10000.0
    assert activity.planned_is_derived is False
    assert db.query(AccountCategoryLimitModel).count() == 0, "the row should be gone, not zeroed"


def test_a_limit_shows_on_the_account_page_with_nothing_spent_against_it(db, user):
    """Otherwise you only ever see the limits you are already breaking."""
    account = make_account(db, user.id, "Chequing")
    set_limit(db, user, account, make_category(db, user.id, "Food"), 400.0)

    entry = row_for(get_account_activity(db, user.id, account.id, MONTH).by_category, "Food")

    assert entry.actual == 0.0
    assert entry.limit == 400.0
    assert entry.remaining == 400.0


def test_overspending_a_category_on_an_account_reports_it(db, user):
    account = make_account(db, user.id, "Chequing")
    food = make_category(db, user.id, "Food")
    set_limit(db, user, account, food, 400.0)
    spend(db, user, account, food, 412.0)

    entry = row_for(get_account_activity(db, user.id, account.id, MONTH).by_category, "Food")

    assert entry.remaining == -12.0
    assert entry.used_percent > 100


def test_the_budget_page_shows_no_category_limits(db, user):
    """The mistake that got the first attempt removed, asserted against.

    A limit belongs to one account; the budget summary spans all of them, so a
    limit there would be judged against the wrong money.
    """
    account = make_account(db, user.id, "Chequing")
    food = make_category(db, user.id, "Food")
    set_limit(db, user, account, food, 400.0)
    spend(db, user, account, food, 100.0)

    entry = row_for(get_budget_summary(db, user.id, MONTH).by_category, "Food")

    assert entry.limit is None
    assert entry.remaining == 0.0
    assert entry.used_percent == 0.0


def test_uncategorised_spending_carries_no_limit(db, user):
    account = make_account(db, user.id, "Chequing")
    spend(db, user, account, None, 23.0)

    entry = row_for(get_account_activity(db, user.id, account.id, MONTH).by_category, "Uncategorised")
    assert entry.limit is None


def test_a_limit_of_zero_closes_the_category_on_that_account(db, user):
    account = make_account(db, user.id, "Chequing")
    food = make_category(db, user.id, "Food")
    target(db, user, account, 10000.0)
    set_limit(db, user, account, food, 0.0)
    spend(db, user, account, food, 15.0)

    activity = get_account_activity(db, user.id, account.id, MONTH)
    entry = row_for(activity.by_category, "Food")

    assert entry.limit == 0.0
    assert entry.remaining == -15.0
    assert activity.planned == 0.0, "not 10000 -- a limit of zero is still a budget"
    assert activity.planned_is_derived is True


def test_limits_are_per_account_not_per_category(db, user):
    """The whole reason this is keyed on the pair."""
    chequing = make_account(db, user.id, "Chequing")
    card = make_account(db, user.id, "Card")
    food = make_category(db, user.id, "Food")
    set_limit(db, user, chequing, food, 400.0)
    set_limit(db, user, card, food, 100.0)

    a = row_for(get_account_activity(db, user.id, chequing.id, MONTH).by_category, "Food")
    b = row_for(get_account_activity(db, user.id, card.id, MONTH).by_category, "Food")

    assert (a.limit, b.limit) == (400.0, 100.0)


def test_deleting_a_category_removes_the_limits_that_pointed_at_it(db, user):
    """A foreign key, so leaving them fails the delete rather than littering."""
    account = make_account(db, user.id, "Chequing")
    food = make_category(db, user.id, "Food")
    set_limit(db, user, account, food, 400.0)

    delete_category(db, user.id, food.id)

    assert db.query(AccountCategoryLimitModel).count() == 0


def test_deleting_an_account_removes_its_limits(db, user):
    # Not a spending account: deleting the only one of those is refused on its
    # own merits, which would make this pass for the wrong reason.
    account = make_account(db, user.id, "Spare", kind="other")
    set_limit(db, user, account, make_category(db, user.id, "Food"), 400.0)

    delete_account(db, user.id, account.id)

    assert db.query(AccountCategoryLimitModel).count() == 0


def test_a_limit_on_someone_elses_account_is_refused(db, user):
    intruder = make_user(db, "intruder@example.com")
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Food")

    assert set_account_category_limit(db, intruder.id, AccountCategoryLimitUpsert(
        account_id=account.id, category_id=category.id, limit_amount=1.0,
    )) is False
    assert db.query(AccountCategoryLimitModel).count() == 0
