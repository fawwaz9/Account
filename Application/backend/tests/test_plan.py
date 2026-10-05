"""The year plan and the hours-to-goal solver (Phase 1 item 10).

Hand-computed throughout, like the forecast's tests. The plan reuses the
forecast's engine, so what is new here is the wider net (all liquid money), the
monthly roll-up, the school-year horizon and the solver.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import TransactionModel
from app.Auth.dependencies import get_current_user
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Finances.schemas.recurring import RecurringCreate
from app.Finances.services.plan_service import plan
from app.Finances.services.recurring_service import create_rule
from app.Jobs.schemas.job import JobCreate, JobKind
from app.Jobs.services.job_service import create_job
from tests.conftest import make_account

ANCHOR = datetime.date(2026, 10, 14)
YEAR_END = datetime.date(2027, 4, 30)  # school year 2's Winter term ends here
WEEKS = (YEAR_END - ANCHOR).days / 7   # 198 days = 28.2857 weeks
CENT = 0.011
D = datetime.timedelta


def txn(db, user, account, kind, amount, on, description="x"):
    db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind=kind,
                            amount=amount, description=description, occurred_on=on))
    db.commit()


def monthly(db, user, kind, amount, on, account, to=None, description="Rule"):
    return create_rule(db, user.id, RecurringCreate(
        kind=kind, account_id=account.id, to_account_id=to.id if to else None, amount=amount,
        description=description, starts_on=on,
        recurrence=Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[], until=None, count=None),
        active=True,
    ))


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    return user


@pytest.fixture
def chequing(db, termed):
    account = make_account(db, termed.id, "Chequing", share=100.0)
    txn(db, termed, account, "income", 3000.0, ANCHOR)  # today: no history
    return account


def rent(db, user, account):
    return monthly(db, user, "expense", 600.0, datetime.date(2026, 10, 20), account, description="Rent")


# --- the horizon ----------------------------------------------------------

def test_it_runs_to_the_end_of_the_school_year(db, termed, chequing):
    result = plan(db, termed.id, on_day=ANCHOR)
    assert result.ends_on == YEAR_END
    assert [m.month for m in result.months][0] == datetime.date(2026, 10, 1)
    assert [m.month for m in result.months][-1] == datetime.date(2027, 4, 1)
    assert len(result.months) == 7


def test_in_the_summer_it_plans_the_next_school_year(db, termed, chequing):
    result = plan(db, termed.id, on_day=datetime.date(2027, 5, 10))
    assert result.ends_on == datetime.date(2028, 4, 30)
    # From the school year, not the fallback that happens to agree in this case.
    assert not any("isn't known" in a for a in result.assumptions)


def test_without_a_school_year_it_runs_to_the_next_april(db, user):
    make_account(db, user.id, "Chequing", share=100.0)
    result = plan(db, user.id, on_day=ANCHOR)
    assert result.ends_on == datetime.date(2027, 4, 30)
    assert any("April 30" in a for a in result.assumptions)


def test_a_target_date_in_the_past_is_refused(db, termed, chequing):
    with pytest.raises(ValueError):
        plan(db, termed.id, on_day=ANCHOR, target=100, target_on=ANCHOR)


# --- what counts ----------------------------------------------------------

def test_liquid_money_is_spending_savings_and_emergency(db, termed, chequing):
    savings = make_account(db, termed.id, "Savings", kind="savings")
    txn(db, termed, savings, "income", 1000.0, ANCHOR)
    rainy = make_account(db, termed.id, "Rainy day", kind="emergency")
    txn(db, termed, rainy, "income", 500.0, ANCHOR)
    tfsa = make_account(db, termed.id, "TFSA", kind="investment")
    txn(db, termed, tfsa, "income", 9000.0, ANCHOR)

    result = plan(db, termed.id, on_day=ANCHOR)
    assert result.starting_balance == pytest.approx(4500.0, abs=CENT)


def test_moving_money_between_liquid_accounts_changes_nothing(db, termed, chequing):
    savings = make_account(db, termed.id, "Savings", kind="savings")
    tfsa = make_account(db, termed.id, "TFSA", kind="investment")
    monthly(db, termed, "transfer", 200.0, datetime.date(2026, 10, 15), chequing, to=savings,
            description="Save")
    monthly(db, termed, "transfer", 50.0, datetime.date(2026, 10, 15), chequing, to=tfsa,
            description="Invest")

    result = plan(db, termed.id, on_day=ANCHOR)
    # Only the TFSA transfer leaves liquid money: 7 x 50 = 350.
    assert result.ending_balance == pytest.approx(3000.0 - 350.0, abs=CENT)


# --- the months -----------------------------------------------------------

def test_months_carry_a_running_balance(db, termed, chequing):
    rent(db, termed, chequing)
    result = plan(db, termed.id, on_day=ANCHOR)

    oct_, nov = result.months[0], result.months[1]
    assert (oct_.money_in, oct_.money_out, oct_.end_balance) == (0.0, 600.0, 2400.0)
    assert nov.end_balance == pytest.approx(1800.0, abs=CENT)
    # Seven rents, Oct to Apr: 3000 - 4200 = -1200.
    assert result.ending_balance == pytest.approx(-1200.0, abs=CENT)
    assert result.lowest_balance == pytest.approx(-1200.0, abs=CENT)


def test_day_to_day_spending_lands_in_its_month(db, termed):
    account = make_account(db, termed.id, "Chequing", share=100.0)
    txn(db, termed, account, "income", 3280.0, ANCHOR - D(days=56))
    txn(db, termed, account, "expense", -280.0, ANCHOR - D(days=7), "Books")  # $5 a day
    rent(db, termed, account)

    result = plan(db, termed.id, on_day=ANCHOR)
    # October: Oct 15-31 is 17 days x 5 = 85, plus rent 600.
    assert result.months[0].money_out == pytest.approx(685.0, abs=CENT)
    # November: 30 x 5 + 600 = 750.
    assert result.months[1].money_out == pytest.approx(750.0, abs=CENT)


# --- the solver -----------------------------------------------------------

def hourly(db, user, rate=20.0):
    # No pay schedule, so it adds nothing to the base plan: the solver prices
    # extra hours at its rate, and the base stays easy to check by hand.
    return create_job(db, user.id, JobCreate(name="Bookstore", kind=JobKind.HOURLY, hourly_rate=rate))


def test_the_solver_turns_a_shortfall_into_weekly_hours(db, termed, chequing):
    rent(db, termed, chequing)
    hourly(db, termed)

    goal = plan(db, termed.id, on_day=ANCHOR, target=2000.0).goal
    # Base -1200, target 2000: short 3200. At $20 an hour over 28.29 weeks that
    # is 5.66 hours a week, rounded up to the half hour: 6.
    assert goal.base_end_balance == pytest.approx(-1200.0, abs=CENT)
    assert goal.shortfall == pytest.approx(3200.0, abs=CENT)
    assert goal.net_hourly == pytest.approx(20.0, abs=CENT)
    assert goal.extra_hours_per_week == 6.0
    ends = {s.extra_hours_per_week: s.end_balance for s in goal.scenarios}
    assert ends[0] == pytest.approx(-1200.0, abs=CENT)
    assert ends[8] == pytest.approx(-1200.0 + 8 * WEEKS * 20, abs=CENT)


def test_a_target_already_met_needs_no_extra_hours(db, termed, chequing):
    hourly(db, termed)
    goal = plan(db, termed.id, on_day=ANCHOR, target=1000.0).goal
    assert goal.shortfall == pytest.approx(-2000.0, abs=CENT)
    assert goal.extra_hours_per_week is None


def test_an_earlier_target_date_ends_the_plan_there(db, termed, chequing):
    rent(db, termed, chequing)
    hourly(db, termed)
    goal = plan(db, termed.id, on_day=ANCHOR, target=3000.0,
                target_on=datetime.date(2026, 12, 31)).goal
    # Three rents to Dec 31: base 1200, short 1800 over 11.14 weeks at $20:
    # 8.08 hours, rounded up to 8.5.
    assert goal.target_on == datetime.date(2026, 12, 31)
    assert goal.shortfall == pytest.approx(1800.0, abs=CENT)
    assert goal.extra_hours_per_week == 8.5


def test_an_extra_hour_counts_at_the_liquid_share_of_income(db, termed):
    """Pay split 60/40 with an investment account: an hour adds 60% of its pay."""
    account = make_account(db, termed.id, "Chequing", share=60.0)
    make_account(db, termed.id, "TFSA", share=40.0, kind="investment")
    txn(db, termed, account, "income", 1000.0, ANCHOR)
    hourly(db, termed)
    goal = plan(db, termed.id, on_day=ANCHOR, target=2000.0).goal
    assert goal.net_hourly == pytest.approx(12.0, abs=CENT)


def test_another_users_jobs_and_term_change_nothing(db):
    """The other user exists first, so a lookup that forgot its filter would
    take theirs: their job would price the owner's hours, their missing school
    year would set the owner's horizon."""
    from tests.conftest import make_user

    other = make_user(db, "other@example.com")
    owner = make_user(db, "owner@example.com")
    owner.current_school_year, owner.current_semester, owner.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    account = make_account(db, owner.id, "Chequing", share=100.0)
    txn(db, owner, account, "income", 3000.0, ANCHOR)

    alone = plan(db, owner.id, on_day=ANCHOR, target=9000.0)
    assert alone.goal is None and alone.ends_on == YEAR_END
    assert not any("isn't known" in a for a in alone.assumptions), "the owner's school year"

    theirs = make_account(db, other.id, "Theirs", share=100.0)
    txn(db, other, theirs, "income", 77000.0, ANCHOR)
    hourly(db, other, rate=55.0)

    assert plan(db, owner.id, on_day=ANCHOR, target=9000.0).model_dump() == alone.model_dump()


def test_without_an_hourly_job_the_solver_says_so(db, termed, chequing):
    result = plan(db, termed.id, on_day=ANCHOR, target=5000.0)
    assert result.goal is None
    assert any("can't be priced" in a for a in result.assumptions)


# --- the route ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, client, chequing):
    assert client.get(f"/api/finances/{user.id}/plan").status_code == 200
    body = client.get(f"/api/finances/{user.id}/plan", params={"target": 500}).json()
    assert body["months"] and body["goal"] is None  # no hourly job
    assert client.get(f"/api/finances/{user.id}/plan",
                      params={"until": "2000-01-01"}).status_code == 400
    assert client.get(f"/api/finances/{user.id}/plan", params={"target": -5}).status_code == 422
