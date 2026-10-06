"""One switch per account for net worth and every analytic (Phase 1 D39).

An unticked account is treated as if it did not exist by every figure built
from more than one account. The invariant test pins that the strongest way
available: compute every analytic, add an unticked account with activity of
every kind, and require every figure to be *unchanged* -- then tick it, and
require them to move, so the test cannot pass by computing nothing.
"""
import uuid
from datetime import date, timedelta

import pytest

from app._database.models import (
    AccountModel,
    BudgetTargetModel,
    RecurringTransactionModel,
    SavedPlanModel,
    SinkingFundModel,
    TransactionModel,
)
from app.Finances.schemas.account import AccountUpdate
from app.Finances.services.account_service import net_worth, update_account
from app.Finances.services.budget_service import get_budget_summary
from app.Finances.services.forecast_service import forecast
from app.Finances.services.plan_review_service import review
from app.Finances.services.plan_service import plan
from app.Finances.services.safe_service import safe_to_spend
from app.Finances.services.subscription_service import find_subscriptions
from app.Finances.services.tuition_service import course_cost, term_budget
from conftest import make_account, make_course

TODAY = date(2026, 10, 14)  # inside the Fall 2026 term set on the user below


def money(db, user, account, kind, amount, on, description=None, course=None, group=None):
    db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind=kind,
                            amount=amount, occurred_on=on, description=description,
                            course_id=course.id if course else None, group_id=group))
    db.commit()


@pytest.fixture
def world(db, user):
    """A counted chequing account with a life of its own, and a course."""
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    chequing = make_account(db, user.id, "Chequing", share=1.0)
    course = make_course(db, user.id, "CPSC 110", year=2, semester="Fall")
    money(db, user, chequing, "income", 3000.0, date(2026, 9, 1), "Pay")
    for day in (5, 12, 19, 26):
        money(db, user, chequing, "expense", -6.0, date(2026, 9, day), "Coffee Shop")
    money(db, user, chequing, "expense", -80.0, TODAY - timedelta(days=3), "Groceries")
    money(db, user, chequing, "expense", -40.0, date(2026, 9, 10), "Calculator", course=course)
    # A plan saved before September, so September is compared with it.
    db.add(SavedPlanModel(id=uuid.uuid4(), user_id=user.id, saved_on=date(2026, 8, 20),
                          starts_on=date(2026, 8, 20), ends_on=date(2027, 4, 30), starting_balance=0.0,
                          months=[{"month": "2026-09-01", "money_in": 3000, "money_out": 500,
                                   "end_balance": 2500}]))
    db.commit()
    return chequing, course


def every_figure(db, user, course) -> dict:
    return {
        "net_worth": net_worth(db, user.id).model_dump(),
        "safe_to_spend": safe_to_spend(db, user.id, on_day=TODAY).model_dump(),
        "forecast": forecast(db, user.id, on_day=TODAY).model_dump(),
        "plan": plan(db, user.id, on_day=TODAY).model_dump(),
        "plan_review": review(db, user.id, on_day=TODAY).model_dump(),
        "budget_summary": _dump(get_budget_summary(db, user.id, TODAY)),
        "term_budget": term_budget(db, user.id, today=TODAY).model_dump(),
        "course_cost": course_cost(db, user.id, course.id).model_dump(),
        "subscriptions": [c.model_dump() for c in find_subscriptions(db, user.id)],
    }


def _dump(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


def uncounted(db, user, course, kind, other_counted):
    """An account with activity that would touch every analytic -- unticked."""
    pot = AccountModel(id=uuid.uuid4(), user_id=user.id, name="Lent out", kind=kind,
                       income_share=0.0, archived=False, position=9, counts_toward_net_worth=False)
    db.add(pot)
    db.commit()
    sign = 1 if kind != "debt" else -1
    money(db, user, pot, "income", 5000.0 * sign, date(2026, 9, 2), "Deposit")
    for month in (7, 8, 9):  # a monthly charge the subscription finder would flag
        money(db, user, pot, "expense", -15.99, date(2026, month, 8), "Streamflix")
    for day in (6, 13, 20, 27):  # a merchant the run-rates would name
        money(db, user, pot, "expense", -25.0, date(2026, 9, day), "Diner")
    money(db, user, pot, "expense", -700.0, TODAY - timedelta(days=2), "Big purchase")
    money(db, user, pot, "expense", -120.0, date(2026, 9, 11), "Textbook", course=course)
    # Older than anything counted: the history window must not stretch to it.
    money(db, user, pot, "expense", -1.0, date(2026, 5, 1), "Old")
    db.add(RecurringTransactionModel(id=uuid.uuid4(), user_id=user.id, kind="expense", account_id=pot.id,
                                     amount=200.0, description="Rent share", starts_on=date(2026, 9, 20),
                                     recur_freq="monthly", recur_interval=1, skipped_dates=[], active=True))
    db.add(BudgetTargetModel(id=uuid.uuid4(), user_id=user.id, account_id=pot.id,
                             month=TODAY.replace(day=1), planned_amount=400.0))
    db.add(SinkingFundModel(id=uuid.uuid4(), user_id=user.id, name="Trip", target_amount=900.0,
                            due_on=date(2027, 1, 31), from_account_id=pot.id, to_account_id=other_counted.id))
    db.commit()
    return pot


@pytest.mark.parametrize("kind", ["spending", "savings", "debt"])
def test_an_unticked_account_changes_no_figure(db, user, world, kind):
    chequing, course = world
    before = every_figure(db, user, course)

    pot = uncounted(db, user, course, kind, chequing)
    after = every_figure(db, user, course)
    for name in before:
        assert after[name] == before[name], f"an unticked {kind} account moved {name}"

    # Ticked, it counts: the same activity now moves the figures, so the
    # equality above is about the switch and not about nothing being read.
    update_account(db, user.id, pot.id, AccountUpdate(counts_toward_net_worth=True))
    ticked = every_figure(db, user, course)
    moved = {name for name in before if ticked[name] != before[name]}
    expected = {"net_worth", "safe_to_spend", "forecast", "plan", "budget_summary", "term_budget",
                "course_cost", "subscriptions"}
    if kind in ("spending", "savings"):
        expected.add("plan_review")  # its deposit lands in September's liquid money
    assert expected <= moved, f"ticked {kind}: did not move {sorted(expected - moved)}"


def test_money_moved_to_an_unticked_account_still_left(db, user, world):
    """Only the unticked account's own activity vanishes: a transfer from a
    counted account to it really took money out of what counts."""
    chequing, course = world
    pot = make_account(db, user.id, "Lent out", kind="savings")
    update_account(db, user.id, pot.id, AccountUpdate(counts_toward_net_worth=False))
    before = net_worth(db, user.id).net_worth
    group = uuid.uuid4()
    money(db, user, chequing, "transfer", -500.0, date(2026, 9, 15), "Lent", group=group)
    money(db, user, pot, "transfer", 500.0, date(2026, 9, 15), "Lent", group=group)

    assert net_worth(db, user.id).net_worth == pytest.approx(before - 500.0)
    [september] = review(db, user.id, on_day=TODAY).months
    assert september.actual_out == pytest.approx(24.0 + 40.0 + 500.0)  # coffee, calculator, the loan
