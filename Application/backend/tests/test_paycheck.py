"""Paycheque verification: BC overtime and vacation pay, with the math shown.

Phase 1 item 11. A false "you're short" costs as much trust as a missed one, so
most of these pin what does NOT get flagged as carefully as what does. Figures
are worked by hand beside each assertion; the rate is $18.50 throughout, so
time and a half is $27.75 and double time $37.00.
"""
import datetime

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app.Auth.dependencies import get_current_user
from app.Jobs.schemas.job import JobCreate, JobKind, ShiftCreate, ShiftRecordUpsert
from app.Jobs.schemas.paycheque import PaychequeCreate
from app.Jobs.services.job_service import add_shift, confirm_shift, create_job
from app.Jobs.services.pay_rules import (
    DAILY_OVERTIME,
    DOUBLE_TIME,
    REGULAR,
    WEEKLY_OVERTIME,
    Worked,
    split,
    vacation_percent,
    week_start,
)
from app.Jobs.services.paycheck_service import check_paycheque
from app.Jobs.services.paycheque_service import record_paycheque
from tests.conftest import make_account

CENT = 0.011
T = datetime.time
D = datetime.date
SUN = D(2026, 9, 6)  # a Sunday, in the past: a cheque is for work already done


def minutes_by_kind(portions):
    out = {}
    for p in portions:
        out[p.kind] = out.get(p.kind, 0) + p.minutes
    return out


# --- the rules, alone -----------------------------------------------------

def test_a_week_begins_on_sunday():
    assert week_start(SUN) == SUN
    assert week_start(SUN + datetime.timedelta(days=6)) == SUN  # Saturday
    assert week_start(SUN + datetime.timedelta(days=7)) == SUN + datetime.timedelta(days=7)


def test_past_eight_hours_in_a_day_is_time_and_a_half():
    assert minutes_by_kind(split([Worked(SUN, 10 * 60, 18.5)])) == {REGULAR: 480, DAILY_OVERTIME: 120}


def test_past_twelve_hours_is_double_time():
    assert minutes_by_kind(split([Worked(SUN, 13 * 60, 18.5)])) == {
        REGULAR: 480, DAILY_OVERTIME: 240, DOUBLE_TIME: 60,
    }


def test_two_shifts_in_a_day_count_as_one_day():
    # 6h then 7h: the second shift crosses 8 and 12.
    portions = split([Worked(SUN, 360, 18.5, T(8)), Worked(SUN, 420, 18.5, T(15))])
    assert minutes_by_kind(portions) == {REGULAR: 480, DAILY_OVERTIME: 240, DOUBLE_TIME: 60}
    assert [p.minutes for p in portions if p.kind == REGULAR] == [360, 120]


def test_daily_overtime_is_not_counted_again_weekly():
    # Mon-Fri 9h: 40 regular hours and five of daily overtime -- no weekly.
    week = [Worked(SUN + datetime.timedelta(days=d), 9 * 60, 18.5) for d in range(1, 6)]
    assert minutes_by_kind(split(week)) == {REGULAR: 2400, DAILY_OVERTIME: 300}


def test_past_forty_regular_hours_is_weekly_overtime_on_the_latest_hours():
    # Sun-Fri 8h: 48 regular hours, the last 8 (Friday) become weekly overtime.
    week = [Worked(SUN + datetime.timedelta(days=d), 8 * 60, 18.5) for d in range(6)]
    portions = split(week)
    assert minutes_by_kind(portions) == {REGULAR: 2400, WEEKLY_OVERTIME: 480}
    assert {p.on_date for p in portions if p.kind == WEEKLY_OVERTIME} == {SUN + datetime.timedelta(days=5)}


def test_a_new_week_resets_the_forty():
    # Sat 8h and the following Sun 8h, after a full week: the Sunday is a new week.
    first = [Worked(SUN + datetime.timedelta(days=d), 8 * 60, 18.5) for d in range(1, 6)]  # 40h Mon-Fri
    sat = Worked(SUN + datetime.timedelta(days=6), 8 * 60, 18.5)
    nxt = Worked(SUN + datetime.timedelta(days=7), 8 * 60, 18.5)
    kinds = [(p.on_date, p.kind) for p in split(first + [sat, nxt])]
    assert (sat.on_date, WEEKLY_OVERTIME) in kinds
    assert (nxt.on_date, REGULAR) in kinds and (nxt.on_date, WEEKLY_OVERTIME) not in kinds


def test_overtime_is_paid_at_the_shifts_own_rate():
    [regular, overtime] = split([Worked(SUN, 9 * 60, 22.0)])
    assert regular.amount == pytest.approx(176.0)   # 8 x 22
    assert overtime.amount == pytest.approx(33.0)   # 1 x 33


def test_vacation_pay_is_four_percent_then_six_after_five_years():
    assert vacation_percent(D(2022, 3, 1), D(2027, 2, 28)) == 4.0
    assert vacation_percent(D(2022, 3, 1), D(2027, 3, 1)) == 6.0
    assert vacation_percent(D(2024, 2, 29), D(2029, 2, 28)) == 6.0
    assert vacation_percent(None, D(2027, 1, 1)) == 4.0


# --- the check, against real shifts and cheques ---------------------------

@pytest.fixture
def chequing(db, user):
    return make_account(db, user.id, "Chequing", share=100.0)


@pytest.fixture
def job(db, user, chequing):
    return create_job(db, user.id, JobCreate(
        name="Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5, started_on=D(2026, 1, 5),
    ))


def shift(db, user, job, day, start, end):
    return add_shift(db, user.id, job.id, ShiftCreate(on_date=day, start_time=T(start), end_time=T(end)))


def cheque(db, user, job, gross, start=SUN, end=SUN + datetime.timedelta(days=13)):
    return record_paycheque(db, user.id, PaychequeCreate(
        job_id=job.id, occurred_on=end + datetime.timedelta(days=5), gross_amount=gross,
        period_start=start, period_end=end, deductions=[],
    ))


def two_weeks(db, user, job):
    """Mon 5h, Tue 9h, Thu 5h (week 1); Tue 5h (week 2). 24h, one of them overtime.

    Regular 23 x 18.50 = 425.50; overtime 1 x 27.75; expected 453.25.
    """
    shift(db, user, job, SUN + datetime.timedelta(days=1), 9, 14)
    shift(db, user, job, SUN + datetime.timedelta(days=2), 8, 17)
    shift(db, user, job, SUN + datetime.timedelta(days=4), 9, 14)
    shift(db, user, job, SUN + datetime.timedelta(days=9), 9, 14)


def test_a_cheque_that_matches_the_hours(db, user, job):
    two_weeks(db, user, job)
    result = check_paycheque(db, user.id, cheque(db, user, job, 453.25).id)
    assert result.status == "as_expected"
    assert result.expected == pytest.approx(453.25, abs=CENT)
    labels = {line.label: line for line in result.lines}
    assert labels["Regular hours"].hours == 23 and labels["Regular hours"].amount == pytest.approx(425.5)
    overtime = labels["Overtime, past 8 hours in a day"]
    assert (overtime.hours, overtime.rate, overtime.amount) == (1, 27.75, 27.75)
    assert "s.40(1)" in overtime.rule
    assert "Statutory holiday pay isn't checked." in result.notes


def test_overtime_paid_as_straight_time_is_short(db, user, job):
    """The vision's own example: a 9-hour Tuesday paid as nine plain hours."""
    two_weeks(db, user, job)
    # 24 x 18.50 = 444.00, against 453.25: 9.25 short (the half on one hour).
    result = check_paycheque(db, user.id, cheque(db, user, job, 444.0).id)
    assert result.status == "short"
    assert result.difference == pytest.approx(-9.25, abs=CENT)
    assert result.summary == "Looks $9.25 short of what the hours come to."


def test_vacation_pay_on_the_cheque_matches(db, user, job):
    two_weeks(db, user, job)
    # 453.25 + 4% = 471.38.
    result = check_paycheque(db, user.id, cheque(db, user, job, 471.38).id)
    assert result.status == "as_expected_with_vacation"
    assert result.expected_with_vacation == pytest.approx(471.38, abs=CENT)
    assert "4% vacation pay" in result.summary


def test_between_the_two_says_to_check_the_vacation_line(db, user, job):
    two_weeks(db, user, job)
    result = check_paycheque(db, user.id, cheque(db, user, job, 462.0).id)
    assert result.status == "unclear"


def test_more_than_the_hours_is_over(db, user, job):
    two_weeks(db, user, job)
    # 520 against the larger expectation 471.38: 48.62 over.
    result = check_paycheque(db, user.id, cheque(db, user, job, 520.0).id)
    assert result.status == "over"
    assert result.difference == pytest.approx(48.62, abs=CENT)


def test_rounding_on_the_stub_is_not_a_shortfall(db, user, job):
    two_weeks(db, user, job)
    assert check_paycheque(db, user.id, cheque(db, user, job, 452.5).id).status == "as_expected"


def test_payroll_tips_count_and_cash_tips_do_not(db, user, job):
    """A cash tip is already in hand; it will never be on the cheque."""
    day = SUN + datetime.timedelta(days=1)
    payroll = shift(db, user, job, day, 9, 14)  # 5h = 92.50
    cash = shift(db, user, job, day + datetime.timedelta(days=1), 9, 14)
    confirm_shift(db, user.id, payroll, day, ShiftRecordUpsert(tip_amount=20.0, tip_is_cash=False))
    confirm_shift(db, user.id, cash, day + datetime.timedelta(days=1),
                  ShiftRecordUpsert(tip_amount=35.0, tip_is_cash=True))
    # 10h x 18.50 = 185.00, plus the 20.00 through payroll: 205.00.
    result = check_paycheque(db, user.id, cheque(db, user, job, 205.0).id)
    assert result.status == "as_expected"
    assert {line.label: line.amount for line in result.lines}["Tips paid through payroll"] == 20.0
    # Vacation pay is on wages, not tips: 4% of 185.00 = 7.40.
    assert result.expected_with_vacation == pytest.approx(212.40, abs=CENT)


def test_unconfirmed_shifts_are_said_to_be_assumed(db, user, job):
    two_weeks(db, user, job)
    result = check_paycheque(db, user.id, cheque(db, user, job, 453.25).id)
    assert any("4 shifts have not been confirmed" in note for note in result.notes)


def test_the_stored_verdict_now_includes_overtime(db, user, job):
    two_weeks(db, user, job)
    recorded = cheque(db, user, job, 444.0)
    assert recorded.expected_gross == pytest.approx(453.25, abs=CENT)
    assert recorded.variance == pytest.approx(-9.25, abs=CENT)


def test_salaried_is_checked_against_the_period_amount(db, user, chequing):
    salaried = create_job(db, user.id, JobCreate(name="RA", kind=JobKind.SALARIED, period_amount=1200.0))
    result = check_paycheque(db, user.id, cheque(db, user, salaried, 1100.0).id)
    assert result.status == "short" and result.difference == pytest.approx(-100.0, abs=CENT)
    assert result.vacation_percent is None


def test_contract_work_and_a_missing_period_cannot_be_checked(db, user, chequing):
    contract = create_job(db, user.id, JobCreate(name="Tutoring", kind=JobKind.CONTRACT))
    assert check_paycheque(db, user.id, cheque(db, user, contract, 300.0).id).status == "cannot_check"

    hourly = create_job(db, user.id, JobCreate(name="Cafe", kind=JobKind.HOURLY, hourly_rate=17.0))
    no_period = record_paycheque(db, user.id, PaychequeCreate(
        job_id=hourly.id, occurred_on=D(2026, 10, 20), gross_amount=300.0, deductions=[],
    ))
    result = check_paycheque(db, user.id, no_period.id)
    assert result.status == "cannot_check" and "No pay period" in result.summary


def test_another_users_cheque_is_not_found(db, user, job):
    from tests.conftest import make_user

    two_weeks(db, user, job)
    mine = cheque(db, user, job, 453.25)
    other = make_user(db, "other@example.com")
    assert check_paycheque(db, other.id, mine.id) is None


# --- the route ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, job, client):
    two_weeks(db, user, job)
    recorded = cheque(db, user, job, 444.0)
    body = client.get(f"/api/jobs/{user.id}/paycheques/{recorded.id}/check").json()
    assert body["status"] == "short" and body["lines"]
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/jobs/{user.id}/paycheques/{missing}/check").status_code == 404
