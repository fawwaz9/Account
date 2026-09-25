"""The limit resolution rule, and the zero that breaks the obvious version."""

from app.Finances.utils.limits import effective_limit


def test_a_months_override_beats_the_standing_limit():
    assert effective_limit(standing=400.0, override=500.0) == 500.0


def test_an_override_of_zero_still_wins():
    """The case that fails if the rule asks `if override:` instead of `is not None`.

    Zero means "nothing is meant to go here this month", which is a stricter
    instruction than the standing limit, not the absence of one. Falling through
    to 400 here would report a month deliberately closed as merely unbudgeted --
    and it is the month someone cared enough about to set to zero.
    """
    assert effective_limit(standing=400.0, override=0.0) == 0.0


def test_the_standing_limit_applies_when_the_month_has_no_row():
    assert effective_limit(standing=400.0, override=None) == 400.0


def test_no_limit_at_all_is_none_rather_than_zero():
    """None and 0.0 must not collapse: one draws no bar, the other draws a full one."""
    assert effective_limit(standing=None, override=None) is None


def test_a_month_can_impose_a_limit_on_a_category_that_has_no_standing_one():
    assert effective_limit(standing=None, override=250.0) == 250.0


# ---------------------------------------------------------- through the service --

import uuid
from datetime import date

from app._database.models import CategoryBudgetModel, TransactionModel
from app.Finances.schemas.budget import CategoryLimitUpsert, SpendCategoryUpdate
from app.Finances.services.budget_service import (
    get_budget_summary,
    set_category_limit,
    update_category,
)
from tests.conftest import make_account, make_category

ANCHOR = date(2026, 3, 14)
MONTH = date(2026, 3, 1)


def spend(db, user, account, category, amount: float, on: date = ANCHOR):
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
        amount=-amount, description="Spent", occurred_on=on,
        category_id=category.id if category else None,
    ))
    db.commit()


def row_for(summary, name: str):
    return next(entry for entry in summary.by_category if entry.category_name == name)


def test_a_limit_with_nothing_spent_still_appears(db, user):
    """Otherwise you could only ever see the limits you were already breaking.

    The list used to be built from spending alone, so a category you were safely
    under simply was not there -- which is the half of a budget that tells you
    things are fine.
    """
    category = make_category(db, user.id, "Groceries")
    category.monthly_limit = 400.0
    db.commit()

    summary = get_budget_summary(db, user.id, MONTH)

    entry = row_for(summary, "Groceries")
    assert entry.actual == 0.0
    assert entry.limit == 400.0
    assert entry.remaining == 400.0
    assert entry.used_percent == 0.0


def test_spending_against_a_limit_reports_what_is_left(db, user):
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Transport")
    category.monthly_limit = 150.0
    db.commit()
    spend(db, user, account, category, 88.0)

    entry = row_for(get_budget_summary(db, user.id, MONTH), "Transport")

    assert entry.actual == 88.0
    assert entry.remaining == 62.0
    assert entry.used_percent == 58.7


def test_overspending_reports_a_negative_remainder_and_over_100_percent(db, user):
    """What the red bar is drawn from. `used_percent` is deliberately not clamped
    here -- ProgressBar needs to see it exceed 100 to pick the `over` colour."""
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Groceries")
    category.monthly_limit = 400.0
    db.commit()
    spend(db, user, account, category, 412.0)

    entry = row_for(get_budget_summary(db, user.id, MONTH), "Groceries")

    assert entry.remaining == -12.0
    assert entry.used_percent > 100


def test_a_category_with_no_limit_is_unchanged(db, user):
    """The rows that existed before this feature must look exactly as they did."""
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Odds")
    spend(db, user, account, category, 31.0)

    entry = row_for(get_budget_summary(db, user.id, MONTH), "Odds")

    assert entry.limit is None
    assert entry.remaining == 0.0
    assert entry.used_percent == 0.0


def test_uncategorised_spending_never_carries_a_limit(db, user):
    """It has no row to hang one on, and `.get` must not invent one."""
    account = make_account(db, user.id, "Chequing")
    spend(db, user, account, None, 23.0)

    entry = row_for(get_budget_summary(db, user.id, MONTH), "Uncategorised")

    assert entry.actual == 23.0
    assert entry.limit is None


def test_an_archived_category_with_a_limit_is_not_offered(db, user):
    """Archived is history. A limit on one is not a plan for this month."""
    category = make_category(db, user.id, "Old habit")
    category.monthly_limit = 50.0
    category.archived = True
    db.commit()

    summary = get_budget_summary(db, user.id, MONTH)

    assert all(entry.category_name != "Old habit" for entry in summary.by_category)


def test_a_months_override_replaces_the_standing_limit_for_that_month_only(db, user):
    category = make_category(db, user.id, "Groceries")
    category.monthly_limit = 400.0
    db.commit()

    set_category_limit(db, user.id, CategoryLimitUpsert(
        category_id=category.id, month=MONTH, limit_amount=500.0,
    ))

    march = row_for(get_budget_summary(db, user.id, MONTH), "Groceries")
    april = row_for(get_budget_summary(db, user.id, date(2026, 4, 1)), "Groceries")

    assert march.limit == 500.0
    assert march.limit_is_override is True
    assert april.limit == 400.0, "a neighbouring month must be untouched"
    assert april.limit_is_override is False


def test_clearing_an_override_falls_back_to_the_standing_limit(db, user):
    """And removes the row, rather than writing the standing value into it.

    A row left behind holding 400 would look identical today and stop following
    the standing limit the moment it changed -- which is what stops a default
    being a default.
    """
    category = make_category(db, user.id, "Groceries")
    category.monthly_limit = 400.0
    db.commit()
    set_category_limit(db, user.id, CategoryLimitUpsert(
        category_id=category.id, month=MONTH, limit_amount=500.0,
    ))

    set_category_limit(db, user.id, CategoryLimitUpsert(
        category_id=category.id, month=MONTH, limit_amount=None,
    ))

    entry = row_for(get_budget_summary(db, user.id, MONTH), "Groceries")
    assert entry.limit == 400.0
    assert entry.limit_is_override is False
    assert db.query(CategoryBudgetModel).filter(
        CategoryBudgetModel.category_id == category.id
    ).count() == 0, "the override row should be gone, not rewritten"


def test_a_month_can_be_closed_to_zero(db, user):
    """The end-to-end version of the falsy-check bug: 0 must survive the service
    as well as the rule, or a month deliberately shut reads as unbudgeted."""
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Takeaway")
    category.monthly_limit = 120.0
    db.commit()
    spend(db, user, account, category, 15.0)
    set_category_limit(db, user.id, CategoryLimitUpsert(
        category_id=category.id, month=MONTH, limit_amount=0.0,
    ))

    entry = row_for(get_budget_summary(db, user.id, MONTH), "Takeaway")

    assert entry.limit == 0.0, "not 120.0 -- the override of zero is the instruction"
    assert entry.remaining == -15.0


def test_a_limit_is_removed_by_sending_null_and_kept_by_omission(db, user):
    """The PATCH ambiguity. Absent means "leave it"; explicit null means "remove".

    Told apart by whether the key was sent, which is what exclude_unset reports.
    Without it a limit can be set and never taken off.
    """
    category = make_category(db, user.id, "Books")
    category.monthly_limit = 75.0
    db.commit()

    update_category(db, user.id, category.id, SpendCategoryUpdate(name="Textbooks"))
    assert category.monthly_limit == 75.0, "an unrelated edit must not clear the limit"

    update_category(
        db, user.id, category.id,
        SpendCategoryUpdate.model_validate({"monthly_limit": None}),
    )
    assert category.monthly_limit is None


def test_setting_a_limit_on_someone_elses_category_is_refused(db, user):
    from tests.conftest import make_user

    intruder = make_user(db, "intruder@example.com")
    category = make_category(db, user.id, "Private")

    assert set_category_limit(db, intruder.id, CategoryLimitUpsert(
        category_id=category.id, month=MONTH, limit_amount=1.0,
    )) is False
    assert db.query(CategoryBudgetModel).count() == 0
