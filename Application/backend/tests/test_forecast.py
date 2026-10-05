"""The cash-flow forecast, runway and merchant run-rates (Phase 1 item 9).

Every expected figure below is worked out by hand in a comment beside it,
because a forecast checked against its own arithmetic proves nothing. The ways
it can go wrong are mostly in what is counted twice or not at all: a recurring
expense in both the pace and the schedule, a transfer between two spending
accounts, a cheque due today that is already in the ledger.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import TransactionModel, TuitionPaymentModel
from app.Auth.dependencies import get_current_user
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Finances.schemas.recurring import RecurringCreate
from app.Finances.services.forecast_service import forecast, merchant_key
from app.Finances.services.recurring_service import create_rule
from app.Jobs.schemas.job import JobCreate, JobKind, ShiftMeeting, ShiftScheduleCreate
from app.Jobs.schemas.paycheque import DeductionEntry, PaychequeCreate
from app.Jobs.services.job_service import create_job, set_shift_schedule
from app.Jobs.services.paycheque_service import record_paycheque
from tests.conftest import make_account

# A Wednesday in October. With school year 2 and a first year of 2025, the
# current term is Fall 2026: Sep 1 to Dec 31, so the horizon is 78 days out.
ANCHOR = datetime.date(2026, 10, 14)
TERM_END = datetime.date(2026, 12, 31)
CENT = 0.011
D = datetime.timedelta


def ago(days):
    return ANCHOR - D(days=days)


def txn(db, user, account, kind, amount, on, description="x", recurring_id=None):
    row = TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind=kind,
        amount=amount, description=description, occurred_on=on, recurring_id=recurring_id,
    )
    db.add(row)
    db.commit()
    return row


def monthly(db, user, kind, amount, on, account, to=None, description="Rule"):
    return create_rule(db, user.id, RecurringCreate(
        kind=kind, account_id=account.id if account else None,
        to_account_id=to.id if to else None, amount=amount, description=description,
        starts_on=on,
        recurrence=Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[], until=None, count=None),
        active=True,
    ))


@pytest.fixture
def termed(db, user):
    user.current_school_year = 2
    user.current_semester = "Fall"
    user.first_year_calendar_year = 2025
    db.commit()
    return user


@pytest.fixture
def chequing(db, user):
    return make_account(db, user.id, "Chequing", share=100.0)


def run(db, user):
    return forecast(db, user.id, on_day=ANCHOR)


def balance_on(result, day):
    return next(p.balance for p in result.points if p.on_date == day)


# --- the horizon and the starting point -----------------------------------

def test_the_horizon_is_the_end_of_the_term(db, termed, chequing):
    result = run(db, termed)
    assert result.ends_on == TERM_END and result.ends_at_term_end
    assert len(result.points) == (TERM_END - ANCHOR).days + 1 == 79


def test_without_a_known_term_it_looks_sixteen_weeks_ahead(db, user, chequing):
    result = run(db, user)
    assert result.ends_on == ANCHOR + D(weeks=16) and not result.ends_at_term_end
    assert any("16 weeks" in a for a in result.assumptions)


def test_it_starts_from_spending_accounts_only(db, termed, chequing):
    txn(db, termed, chequing, "income", 1840.20, ANCHOR)
    savings = make_account(db, termed.id, "Savings", kind="savings")
    txn(db, termed, savings, "income", 3200.0, ANCHOR)

    result = run(db, termed)
    assert result.starting_balance == pytest.approx(1840.20, abs=CENT)


def test_no_history_means_no_invented_spending(db, termed, chequing):
    txn(db, termed, chequing, "income", 500.0, ANCHOR)  # today: not history yet

    result = run(db, termed)
    assert result.spending_history_days == 0
    assert result.daily_spending == 0.0
    assert {p.balance for p in result.points} == {500.0}
    assert result.negative_on is None
    assert result.runway is None
    assert any("No spending history" in a for a in result.assumptions)


# --- the pace of one-off spending -----------------------------------------

def test_the_pace_is_one_off_spending_over_the_days_covered(db, termed, chequing):
    # Opened 56 days ago with $3,000; ten one-off coffees of $28 since.
    # Pace: 280 / 56 = $5.00 a day.
    txn(db, termed, chequing, "income", 3000.0, ago(56))
    for i in range(10):
        txn(db, termed, chequing, "expense", -28.0, ago(5 * i + 1), "Coffee")

    result = run(db, termed)
    assert result.spending_history_days == 56
    assert result.daily_spending == pytest.approx(5.0, abs=CENT)
    # Start 2,720. Today keeps what is spent; tomorrow is 2,715; day 10 is 2,670.
    assert balance_on(result, ANCHOR) == pytest.approx(2720.0, abs=CENT)
    assert balance_on(result, ANCHOR + D(days=1)) == pytest.approx(2715.0, abs=CENT)
    assert balance_on(result, ANCHOR + D(days=10)) == pytest.approx(2670.0, abs=CENT)


def test_recurring_rows_tuition_and_other_accounts_are_not_in_the_pace(db, termed, chequing):
    """Each is counted elsewhere or not at all; in the pace it would count twice."""
    txn(db, termed, chequing, "income", 9000.0, ago(56))
    txn(db, termed, chequing, "expense", -112.0, ago(3), "Groceries")  # the only one-off
    rent = monthly(db, termed, "expense", 900.0, ago(40), chequing, description="Rent")
    txn(db, termed, chequing, "expense", -900.0, ago(40), "Rent", recurring_id=rent.id)
    fees = txn(db, termed, chequing, "expense", -4100.0, ago(30), "Tuition")
    db.add(TuitionPaymentModel(id=uuid.uuid4(), user_id=termed.id, transaction_id=fees.id,
                               occurred_on=ago(30)))
    card = make_account(db, termed.id, "Visa", kind="debt")
    txn(db, termed, card, "expense", -300.0, ago(2), "Shoes")
    db.commit()

    result = run(db, termed)
    # 112 / 56 = $2.00 a day.
    assert result.daily_spending == pytest.approx(2.0, abs=CENT)


def test_a_short_history_is_divided_by_the_days_it_covers(db, termed, chequing):
    # First row 10 days ago; $100 spent since: $10 a day, not 100 / 56.
    txn(db, termed, chequing, "income", 1000.0, ago(10))
    txn(db, termed, chequing, "expense", -100.0, ago(4), "Books")

    result = run(db, termed)
    assert result.spending_history_days == 10
    assert result.daily_spending == pytest.approx(10.0, abs=CENT)
    assert any("only 10 days" in a for a in result.assumptions)


def test_it_names_the_first_day_below_zero(db, termed, chequing):
    # Balance 100 after $280 over 56 days: $5 a day. Day 20 is exactly 0 (not
    # negative); day 21 is -5.
    txn(db, termed, chequing, "income", 380.0, ago(56))
    txn(db, termed, chequing, "expense", -280.0, ago(7), "Laptop repair")

    result = run(db, termed)
    assert balance_on(result, ANCHOR + D(days=20)) == pytest.approx(0.0, abs=CENT)
    assert result.negative_on == ANCHOR + D(days=21)
    assert result.lowest_on == TERM_END
    # 100 - 78 * 5 = -290.
    assert result.lowest_balance == pytest.approx(-290.0, abs=CENT)
    assert result.ending_balance == result.lowest_balance


# --- standing instructions ------------------------------------------------

def test_standing_instructions_land_on_their_dates(db, termed, chequing):
    txn(db, termed, chequing, "income", 2000.0, ANCHOR)
    savings = make_account(db, termed.id, "Savings", kind="savings")
    other = make_account(db, termed.id, "Cash", kind="spending")
    monthly(db, termed, "expense", 612.0, datetime.date(2026, 10, 20), chequing, description="Rent")
    monthly(db, termed, "transfer", 100.0, datetime.date(2026, 10, 15), chequing, to=savings,
            description="Save")
    monthly(db, termed, "transfer", 50.0, datetime.date(2026, 10, 16), chequing, to=other,
            description="Cash out")  # spending to spending: nets to nothing
    monthly(db, termed, "income", 250.0, datetime.date(2026, 11, 1), chequing,
            description="Bursary")

    result = run(db, termed)
    rent = [e for e in result.events if e.description == "Rent"]
    assert [e.on_date for e in rent] == [datetime.date(2026, m, 20) for m in (10, 11, 12)]
    assert {e.amount for e in rent} == {-612.0}
    assert {e.amount for e in result.events if e.description == "Save"} == {-100.0}
    assert not [e for e in result.events if e.description == "Cash out"]
    assert {e.amount for e in result.events if e.description == "Bursary"} == {250.0}
    # Oct 20: 2000 - 100 (Oct 15) - 612 = 1288.
    assert balance_on(result, datetime.date(2026, 10, 20)) == pytest.approx(1288.0, abs=CENT)


def test_a_split_deposit_counts_at_the_spending_share(db, user, termed):
    chequing = make_account(db, termed.id, "Chequing", share=60.0)
    make_account(db, termed.id, "Savings", share=40.0, kind="savings")
    monthly(db, termed, "deposit", 1000.0, datetime.date(2026, 11, 1), None, description="RESP")

    result = run(db, termed)
    [nov] = [e for e in result.events if e.on_date == datetime.date(2026, 11, 1)]
    assert nov.amount == pytest.approx(600.0, abs=CENT) and nov.split
    assert any("60%" in a for a in result.assumptions)


# --- pay ------------------------------------------------------------------

def hourly_job(db, user, pay_from=datetime.date(2026, 9, 11)):
    """$18.50/h, fortnightly from Sep 11: Oct 23, Nov 6, Nov 20, Dec 4, Dec 18.

    Shifts Tue and Thu, 09:00-14:00 (5h = $92.50), Sep 7 to Dec 11.
    """
    job = create_job(db, user.id, JobCreate(
        name="Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=datetime.date(2026, 9, 7), pay_starts_on=pay_from,
        pay_schedule=Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[], until=None, count=None),
    ))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU", "TH"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=datetime.date(2026, 9, 7), ends_on=datetime.date(2026, 12, 11)))
    return job


def test_hourly_pay_is_the_scheduled_shifts_on_each_pay_date(db, termed, chequing):
    hourly_job(db, termed)
    result = run(db, termed)
    pay = {e.on_date: e.amount for e in result.events if e.source == "pay"}

    # First cheque, Oct 23: all unpaid work since Sep 7 plus shifts to Oct 23.
    # Tue/Thu Sep 8 .. Oct 22 = 14 shifts x 92.50 = 1295.00.
    assert pay[datetime.date(2026, 10, 23)] == pytest.approx(1295.0, abs=CENT)
    # Oct 24 .. Nov 6: Oct 27, 29, Nov 3, 5 = 370.00. Same for the next two.
    assert pay[datetime.date(2026, 11, 6)] == pytest.approx(370.0, abs=CENT)
    assert pay[datetime.date(2026, 11, 20)] == pytest.approx(370.0, abs=CENT)
    assert pay[datetime.date(2026, 12, 4)] == pytest.approx(370.0, abs=CENT)
    # Dec 5 .. Dec 18: Dec 8, 10 (the schedule ends Dec 11) = 185.00.
    assert pay[datetime.date(2026, 12, 18)] == pytest.approx(185.0, abs=CENT)
    assert any("before deductions" in a for a in result.assumptions)


def test_pay_is_net_of_the_deduction_rate_cheques_show(db, termed, chequing):
    job = hourly_job(db, termed)
    # Sep 7-20 covered: Sep 8, 10, 15, 17 = 4 shifts, $370 gross, $74 deducted (20%).
    record_paycheque(db, termed.id, PaychequeCreate(
        job_id=job.id, occurred_on=datetime.date(2026, 9, 25), gross_amount=370.0,
        period_start=datetime.date(2026, 9, 7), period_end=datetime.date(2026, 9, 20),
        deductions=[DeductionEntry(description="Income tax", amount=74.0)],
    ))

    result = run(db, termed)
    pay = {e.on_date: e.amount for e in result.events if e.source == "pay"}
    # Unpaid now starts Sep 21: Sep 22 .. Oct 22 = 10 shifts = 925 gross -> 740 net.
    assert pay[datetime.date(2026, 10, 23)] == pytest.approx(740.0, abs=CENT)
    assert pay[datetime.date(2026, 11, 6)] == pytest.approx(296.0, abs=CENT)  # 370 x 0.8
    assert any("20% deductions" in a for a in result.assumptions)


def test_a_cheque_due_today_is_not_counted_again(db, termed, chequing):
    """It may already be in the ledger. Its work moves to the next pay date."""
    hourly_job(db, termed, pay_from=ANCHOR)
    result = run(db, termed)
    assert ANCHOR not in {e.on_date for e in result.events if e.source == "pay"}


def test_salaried_pay_is_the_period_amount(db, termed, chequing):
    create_job(db, termed.id, JobCreate(
        name="Lab RA", kind=JobKind.SALARIED, period_amount=800.0,
        started_on=datetime.date(2026, 9, 1), pay_starts_on=datetime.date(2026, 9, 30),
        pay_schedule=Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[], until=None, count=None),
    ))
    result = run(db, termed)
    pay = [e for e in result.events if e.source == "pay"]
    assert [e.on_date for e in pay] == [datetime.date(2026, m, 30) for m in (10, 11, 12)]
    assert {e.amount for e in pay} == {800.0}


def test_a_job_without_a_pay_schedule_says_so(db, termed, chequing):
    create_job(db, termed.id, JobCreate(name="Tutoring", kind=JobKind.HOURLY, hourly_rate=25.0))
    result = run(db, termed)
    assert not [e for e in result.events if e.source == "pay"]
    assert any("Tutoring has no pay schedule" in a for a in result.assumptions)


# --- runway ---------------------------------------------------------------

def test_runway_divides_liquid_money_by_the_recent_net_outflow(db, termed, chequing):
    # Liquid: chequing 1,000 + savings 3,000 + emergency 500 = 4,500.
    # Investments and the card are not liquid.
    txn(db, termed, chequing, "income", 1600.0, ago(56))
    txn(db, termed, chequing, "expense", -600.0, ago(20), "Rent")
    savings = make_account(db, termed.id, "Savings", kind="savings")
    txn(db, termed, savings, "income", 3000.0, ago(90))
    emergency = make_account(db, termed.id, "Rainy day", kind="emergency")
    txn(db, termed, emergency, "income", 500.0, ago(90))
    stocks = make_account(db, termed.id, "TFSA", kind="investment")
    txn(db, termed, stocks, "income", 9000.0, ago(90))
    card = make_account(db, termed.id, "Visa", kind="debt")
    txn(db, termed, card, "expense", -1640.0, ago(10), "Flights")

    result = run(db, termed)
    # Over the last 56 days: +1600 - 600 - 1640 = -640, so $11.43 a day out.
    assert result.runway.liquid == pytest.approx(4500.0, abs=CENT)
    assert result.runway.daily_burn == pytest.approx(640 / 56, abs=CENT)
    # 4500 / (640/56) = 393.75 days -> 393.
    assert result.runway.lasts_until == ANCHOR + D(days=393)


def test_no_burn_means_no_end_date(db, termed, chequing):
    txn(db, termed, chequing, "income", 2000.0, ago(30))
    txn(db, termed, chequing, "expense", -500.0, ago(5), "Books")
    result = run(db, termed)
    assert result.runway.daily_burn == 0.0
    assert result.runway.lasts_until is None


def test_transfers_burn_nothing(db, termed, chequing):
    savings = make_account(db, termed.id, "Savings", kind="savings")
    txn(db, termed, chequing, "income", 1000.0, ago(40))
    txn(db, termed, chequing, "transfer", -800.0, ago(10), "To savings")
    txn(db, termed, savings, "transfer", 800.0, ago(10), "From chequing")
    result = run(db, termed)
    assert result.runway.daily_burn == 0.0


# --- merchant run-rates ---------------------------------------------------

def test_merchants_group_across_receipt_noise(db):
    assert merchant_key("Subway #1234") == merchant_key("SUBWAY 0042") == "subway"
    assert merchant_key("  DoorDash*Order 88 ") == "doordash order"
    assert merchant_key(None) == merchant_key("1234") == ""


def test_run_rates_carry_the_pace_to_the_horizon(db, termed, chequing):
    # 56 days of history; DoorDash 4 x $30 = $120 -> 120/56 a day x 78 days = 167.14.
    txn(db, termed, chequing, "income", 5000.0, ago(56))
    for days in (3, 10, 17, 24):
        txn(db, termed, chequing, "expense", -30.0, ago(days), "DoorDash #19")
    for days in (4, 11):
        txn(db, termed, chequing, "expense", -9.0, ago(days), "Subway 0042")
    txn(db, termed, chequing, "expense", -400.0, ago(6), "Ikea")  # once: no pace
    rule = monthly(db, termed, "expense", 17.0, ago(30), chequing, description="Spotify")
    for days in (30, 1):
        txn(db, termed, chequing, "expense", -17.0, ago(days), "Spotify", recurring_id=rule.id)

    result = run(db, termed)
    assert [r.merchant for r in result.run_rates] == ["DoorDash #19", "Subway 0042"]
    dd = result.run_rates[0]
    assert dd.spent == pytest.approx(120.0, abs=CENT) and dd.occurrences == 4
    assert dd.projected == pytest.approx(120 / 56 * 78, abs=CENT)


def test_run_rates_include_card_spending(db, termed, chequing):
    card = make_account(db, termed.id, "Visa", kind="debt")
    txn(db, termed, chequing, "income", 100.0, ago(56))
    for days in (2, 9):
        txn(db, termed, card, "expense", -6.5, ago(days), "Tim Hortons")
    result = run(db, termed)
    assert [r.merchant for r in result.run_rates] == ["Tim Hortons"]


# --- the route ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route_answers_for_the_signed_in_user(db, user, client, chequing):
    response = client.get(f"/api/finances/{user.id}/forecast")
    assert response.status_code == 200
    body = response.json()
    assert body["starting_balance"] == 0.0
    assert body["points"] and body["assumptions"]


# --- another user's rows change nothing -----------------------------------
#
# Mutation testing found the shared non-interference world could not see this
# service's user filters: everything in it is dated today, and the forecast
# reads only history before today. This builds what the forecast actually
# reads -- past spending, income, tuition, income shares, a paid job, rules --
# for a second user, and requires that none of it moves the first user's answer.

def _full_world(db, owner, chequing_share=60.0):
    chequing = make_account(db, owner.id, "Chequing", share=chequing_share)
    savings = make_account(db, owner.id, "Savings", share=100.0 - chequing_share, kind="savings")
    txn(db, owner, chequing, "income", 2400.0, ago(50))
    txn(db, owner, savings, "income", 1500.0, ago(50))
    for days in (2, 9, 16):
        txn(db, owner, chequing, "expense", -14.0, ago(days), "Blenz Coffee")
    fees = txn(db, owner, chequing, "expense", -900.0, ago(20), "Tuition")
    db.add(TuitionPaymentModel(id=uuid.uuid4(), user_id=owner.id, transaction_id=fees.id,
                               occurred_on=ago(20)))
    db.commit()
    monthly(db, owner, "expense", 600.0, datetime.date(2026, 10, 25), chequing, description="Rent")
    monthly(db, owner, "deposit", 300.0, datetime.date(2026, 11, 3), None, description="Bursary")
    hourly_job(db, owner)
    return chequing


def test_another_users_rows_change_nothing(db):
    from tests.conftest import make_user

    # The other user exists first, so a lookup that forgot its filter and took
    # the first user would take theirs -- and they have no term set.
    other = make_user(db, "other@example.com")
    owner = make_user(db, "owner@example.com")
    owner.current_school_year, owner.current_semester, owner.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    _full_world(db, owner)

    alone = forecast(db, owner.id, on_day=ANCHOR)
    assert alone.ends_at_term_end, "the owner's own term, not the first user's"
    assert alone.run_rates and alone.runway and [e for e in alone.events if e.source == "pay"]

    # Everything the forecast reads, for the other user -- with an earlier
    # history, the same merchant, a bigger income share and a paid job.
    their_chequing = make_account(db, other.id, "Their chequing", share=900.0)
    txn(db, other, their_chequing, "income", 50000.0, ago(55))
    for days in (1, 3, 5, 7):
        txn(db, other, their_chequing, "expense", -14.0, ago(days), "Blenz Coffee")
    txn(db, other, their_chequing, "expense", -20000.0, ago(6), "Car")
    their_fees = txn(db, other, their_chequing, "expense", -14.0, ago(4), "Blenz Coffee")
    db.add(TuitionPaymentModel(id=uuid.uuid4(), user_id=other.id, transaction_id=their_fees.id,
                               occurred_on=ago(4)))
    db.commit()
    monthly(db, other, "expense", 2000.0, datetime.date(2026, 10, 25), their_chequing,
            description="Their rent")
    hourly_job(db, other)

    assert forecast(db, owner.id, on_day=ANCHOR).model_dump() == alone.model_dump()
