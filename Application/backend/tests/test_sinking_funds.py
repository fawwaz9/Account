"""Putting money aside for something that lands all at once.

Two rules carry the feature. The monthly figure is **derived**, never stored, so
a missed month or a moved target corrects itself. And a contribution row exists
only once the money has actually moved, so nothing here ever claims a balance
that is still sitting in the current account.
"""
import datetime
import uuid

import pytest

from app._database.models import SinkingContributionModel, TransactionModel
from app.Finances.schemas.sinking import (
    ContributionRequest,
    SinkingFundCreate,
    SinkingFundUpdate,
)
from app.Finances.services.account_service import balances_by_account
from app.Finances.services.safe_service import safe_to_spend
from app.Finances.services.sinking_service import (
    contribute,
    create_fund,
    delete_fund,
    list_funds,
    months_left,
    undo_contribution,
    update_fund,
)
from app.Finances.services.transaction_service import delete_transaction
from tests.conftest import make_account

OCT = datetime.date(2026, 10, 14)
JAN = datetime.date(2027, 1, 15)
CENT = 0.011


@pytest.fixture
def accounts(db, user):
    chequing = make_account(db, user.id, "Chequing", share=100.0)
    savings = make_account(db, user.id, "Savings")
    savings.kind = "savings"
    db.commit()
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=chequing.id,
        kind="income", amount=4000.0, description="Opening", occurred_on=OCT,
    ))
    db.commit()
    return chequing, savings


def a_fund(db, user, accounts, *, target=2400.0, due=JAN, name="Tuition"):
    chequing, savings = accounts
    return create_fund(db, user.id, SinkingFundCreate(
        name=name, target_amount=target, due_on=due,
        from_account_id=chequing.id, to_account_id=savings.id,
    ), on_day=OCT)


# --- the derived figure ---------------------------------------------------

def test_the_monthly_figure_is_the_target_over_the_months_left(db, user, accounts):
    """October, November, December, January: four contributions of 600."""
    fund = a_fund(db, user, accounts)

    assert months_left(JAN, OCT) == 4
    assert fund.per_month == pytest.approx(600.0, abs=CENT)


def test_setting_a_month_aside_lowers_what_is_left(db, user, accounts):
    fund = a_fund(db, user, accounts)
    after = contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))

    assert after.saved == pytest.approx(600.0, abs=CENT)
    assert after.remaining == pytest.approx(1800.0, abs=CENT)
    assert after.funded_this_month is True


def test_a_missed_month_raises_the_rest_rather_than_shortening_the_target(db, user, accounts):
    """The whole reason the figure is derived rather than stored."""
    fund = a_fund(db, user, accounts)

    # Nothing set aside in October; by November there are three months left.
    november = datetime.date(2026, 11, 3)
    listed = [f for f in list_funds(db, user.id) if f.id == fund.id][0]
    assert listed.target_amount == 2400.0

    from app.Finances.services.sinking_service import as_schema, get_fund
    row = get_fund(db, user.id, fund.id)
    assert as_schema(row, november).per_month == pytest.approx(800.0, abs=CENT)


def test_raising_the_target_changes_the_figure_on_the_next_read(db, user, accounts):
    fund = a_fund(db, user, accounts)
    updated = update_fund(db, user.id, fund.id,
                          SinkingFundUpdate(target_amount=3200.0), on_day=OCT)

    assert updated.per_month == pytest.approx(800.0, abs=CENT)


def test_a_fund_due_in_the_past_asks_for_the_whole_remainder(db, user, accounts):
    """Zero months left is a division by nothing; spreading it moves the deadline."""
    fund = a_fund(db, user, accounts, due=datetime.date(2026, 9, 1))

    assert fund.months_left == 0
    assert fund.per_month == pytest.approx(2400.0, abs=CENT)
    assert fund.overdue is True


# --- the money actually moving --------------------------------------------

def test_confirming_writes_one_transfer_and_moves_both_balances(db, user, accounts):
    chequing, savings = accounts
    fund = a_fund(db, user, accounts)

    contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))

    balances = balances_by_account(db, user.id)
    assert balances[chequing.id] == pytest.approx(3400.0, abs=CENT)
    assert balances[savings.id] == pytest.approx(600.0, abs=CENT)

    rows = db.query(TransactionModel).filter(TransactionModel.kind == "transfer").all()
    assert len(rows) == 2
    assert len({row.group_id for row in rows}) == 1


def test_a_month_cannot_be_funded_twice(db, user, accounts):
    fund = a_fund(db, user, accounts)
    contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))

    with pytest.raises(ValueError, match="already been set aside"):
        contribute(db, user.id, fund.id, ContributionRequest(
            occurred_on=datetime.date(2026, 10, 28)))


def test_a_smaller_month_is_allowed_and_the_rest_absorbs_it(db, user, accounts):
    """Putting something aside beats putting nothing aside."""
    fund = a_fund(db, user, accounts)
    after = contribute(db, user.id, fund.id, ContributionRequest(amount=200.0, occurred_on=OCT))

    assert after.saved == pytest.approx(200.0, abs=CENT)
    # 2200 left over the three months from November.
    from app.Finances.services.sinking_service import as_schema, get_fund
    row = get_fund(db, user.id, fund.id)
    assert as_schema(row, datetime.date(2026, 11, 3)).per_month == pytest.approx(
        733.33, abs=CENT)


def test_a_contribution_cannot_overshoot_the_target(db, user, accounts):
    fund = a_fund(db, user, accounts, target=500.0)
    after = contribute(db, user.id, fund.id, ContributionRequest(amount=900.0, occurred_on=OCT))

    assert after.saved == pytest.approx(500.0, abs=CENT)
    assert after.remaining == 0.0


def test_a_finished_fund_refuses_more(db, user, accounts):
    fund = a_fund(db, user, accounts, target=500.0)
    contribute(db, user.id, fund.id, ContributionRequest(amount=500.0, occurred_on=OCT))

    with pytest.raises(ValueError, match="already reached its target"):
        contribute(db, user.id, fund.id, ContributionRequest(
            occurred_on=datetime.date(2026, 11, 3)))


# --- how it reaches safe to spend -----------------------------------------

def test_an_unfunded_month_is_subtracted_from_safe_to_spend(db, user, accounts):
    """A promise you made to yourself, and the point of the feature."""
    before = safe_to_spend(db, user.id, on_day=OCT)
    a_fund(db, user, accounts)
    after = safe_to_spend(db, user.id, on_day=OCT)

    assert after.earmarked == pytest.approx(600.0, abs=CENT)
    assert after.safe_now == pytest.approx(before.safe_now - 600.0, abs=CENT)


def test_a_funded_month_is_not_subtracted_twice(db, user, accounts):
    """Once transferred it sits in savings, which safe-to-spend already skips.

    Counting it again here would take the same money off twice.
    """
    fund = a_fund(db, user, accounts)
    contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))

    safe = safe_to_spend(db, user.id, on_day=OCT)
    assert safe.earmarked == 0.0
    assert safe.spendable == pytest.approx(3400.0, abs=CENT)
    assert safe.safe_now == pytest.approx(3400.0, abs=CENT)


def test_an_archived_fund_earmarks_nothing(db, user, accounts):
    fund = a_fund(db, user, accounts)
    update_fund(db, user.id, fund.id, SinkingFundUpdate(archived=True))

    assert safe_to_spend(db, user.id, on_day=OCT).earmarked == 0.0


# --- undoing --------------------------------------------------------------

def test_undoing_a_contribution_moves_the_money_back(db, user, accounts):
    chequing, _ = accounts
    fund = a_fund(db, user, accounts)
    funded = contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))

    undo_contribution(db, user.id, fund.id, funded.contributions[0].id)

    assert balances_by_account(db, user.id)[chequing.id] == pytest.approx(4000.0, abs=CENT)
    assert db.query(SinkingContributionModel).count() == 0


def test_deleting_the_transfer_clears_the_contribution(db, user, accounts):
    """The other half of the cascade: a fund must not claim money that is gone."""
    fund = a_fund(db, user, accounts)
    contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))
    row = db.query(TransactionModel).filter(TransactionModel.kind == "transfer").first()

    delete_transaction(db, user.id, row.id, scope="group")

    assert db.query(SinkingContributionModel).count() == 0


def test_deleting_a_fund_takes_its_transfers(db, user, accounts):
    chequing, _ = accounts
    fund = a_fund(db, user, accounts)
    contribute(db, user.id, fund.id, ContributionRequest(occurred_on=OCT))

    delete_fund(db, user.id, fund.id)

    assert db.query(SinkingContributionModel).count() == 0
    assert db.query(TransactionModel).filter(TransactionModel.kind == "transfer").count() == 0
    assert balances_by_account(db, user.id)[chequing.id] == pytest.approx(4000.0, abs=CENT)


# --- guards ---------------------------------------------------------------

def test_a_fund_cannot_move_money_to_itself(db, user, accounts):
    from pydantic import ValidationError
    chequing, _ = accounts

    with pytest.raises(ValidationError):
        SinkingFundCreate(
            name="Nope", target_amount=100.0, due_on=JAN,
            from_account_id=chequing.id, to_account_id=chequing.id,
        )


def test_an_account_that_is_not_yours_is_refused(db, user, accounts):
    chequing, _ = accounts

    with pytest.raises(ValueError, match="does not exist"):
        create_fund(db, user.id, SinkingFundCreate(
            name="Nope", target_amount=100.0, due_on=JAN,
            from_account_id=chequing.id, to_account_id=uuid.uuid4(),
        ))


def test_funds_are_listed_soonest_due_first(db, user, accounts):
    a_fund(db, user, accounts, due=datetime.date(2027, 5, 1), name="Later")
    a_fund(db, user, accounts, due=datetime.date(2026, 12, 1), name="Sooner")

    assert [f.name for f in list_funds(db, user.id)] == ["Sooner", "Later"]
