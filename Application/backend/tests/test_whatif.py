"""The money what-if (Phase 4 item 14, §13.5).

Pinned, by hand where it can be: nothing changed is the year plan to the cent;
each change moves the ending by what it should; hours can only come off shifts
on the schedule; spending can't go below nothing; dates outside the plan are
refused; the exam-season stretch comes from the last final on the calendar; and
no grade, task or other academic table is ever read (§13.3, §13.5).
"""
import datetime
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.main
from app._database.db import get_db
from app._database.models import EventModel, TransactionModel
from app.Auth.dependencies import get_current_user
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Finances.schemas.whatif import Purchase, WhatIfIn
from app.Finances.services.plan_service import plan
from app.Finances.services.whatif_service import what_if
from app.Jobs.schemas.job import JobCreate, JobKind, ShiftMeeting, ShiftScheduleCreate
from app.Jobs.schemas.paycheque import DeductionEntry, PaychequeCreate
from app.Jobs.services.job_service import create_job, set_shift_schedule
from app.Jobs.services.paycheque_service import record_paycheque
from tests.conftest import make_account

ANCHOR = datetime.date(2026, 10, 14)
YEAR_END = datetime.date(2027, 4, 30)
DAYS = (YEAR_END - ANCHOR).days  # 198 days of spending after today
CENT = 0.011

#: Tables an academic figure lives in; the what-if may read none of them.
ACADEMIC_TABLES = {"grades", "course_category_weights", "grading_schemes", "tasks", "term_reviews",
                   "grade_distributions", "course_intel", "syllabus_parses", "degree_requirements"}


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    return user


@pytest.fixture
def chequing(db, termed):
    account = make_account(db, termed.id, "Chequing", share=100.0)
    db.add(TransactionModel(id=uuid.uuid4(), user_id=termed.id, account_id=account.id, kind="income",
                            amount=3000.0, description="x", occurred_on=ANCHOR))
    db.commit()
    return account


@pytest.fixture
def bookstore(db, termed, chequing):
    """$18.50/h, fortnightly from Sep 11; Tue and Thu 09:00-14:00 ($92.50), Sep 7 to Dec 11.

    Upcoming cheques: Oct 23 $1,295; Nov 6, Nov 20, Dec 4 $370 each; Dec 18 $185.
    """
    job = create_job(db, termed.id, JobCreate(
        name="Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=datetime.date(2026, 9, 7), pay_starts_on=datetime.date(2026, 9, 11),
        pay_schedule=Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[], until=None, count=None),
    ))
    set_shift_schedule(db, termed.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU", "TH"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=datetime.date(2026, 9, 7), ends_on=datetime.date(2026, 12, 11)))
    return job


def run(db, user, **changes):
    return what_if(db, user.id, WhatIfIn(**changes), on_day=ANCHOR)


# ------------------------------------------------------------ the baseline --

def test_nothing_changed_is_the_plan_to_the_cent(db, termed, bookstore):
    result = run(db, termed)
    planned = plan(db, termed.id, on_day=ANCHOR)

    assert result.baseline.ending_balance == planned.ending_balance
    assert result.baseline.lowest_balance == planned.lowest_balance
    assert result.scenario == result.baseline and result.difference == 0
    assert (result.starts_on, result.ends_on) == (ANCHOR, YEAR_END)


def test_the_curve_is_weekly_and_ends_on_the_last_day(db, termed, chequing):
    points = run(db, termed).baseline.points

    assert points[0].on_date == ANCHOR and points[-1].on_date == YEAR_END
    assert all((b.on_date - a.on_date).days <= 7 for a, b in zip(points, points[1:]))


# ------------------------------------------------------------- each change --

def test_a_stretch_with_no_shifts_loses_exactly_those_shifts(db, termed, bookstore):
    # Dec 1, 3, 8, 10: four shifts at $92.50.
    result = run(db, termed, no_shifts_from=datetime.date(2026, 12, 1), no_shifts_until=datetime.date(2026, 12, 11))

    assert result.difference == pytest.approx(-370.0, abs=CENT)
    assert any("No shifts from Dec 1 to Dec 11" in a and "$370" in a for a in result.assumptions)


def test_lost_shifts_are_lost_after_deductions(db, termed, bookstore):
    # A cheque with 20% deducted: the four lost shifts cost $370 x 0.8.
    record_paycheque(db, termed.id, PaychequeCreate(
        job_id=bookstore.id, occurred_on=datetime.date(2026, 9, 25), gross_amount=370.0,
        period_start=datetime.date(2026, 9, 7), period_end=datetime.date(2026, 9, 20),
        deductions=[DeductionEntry(description="Income tax", amount=74.0)],
    ))

    result = run(db, termed, no_shifts_from=datetime.date(2026, 12, 1), no_shifts_until=datetime.date(2026, 12, 11))

    assert result.difference == pytest.approx(-296.0, abs=CENT)


def shifted_job(db, user, name, kind, **pay):
    """A second job with Monday shifts, 10:00-14:00, to Dec 11."""
    job = create_job(db, user.id, JobCreate(
        name=name, kind=kind, started_on=datetime.date(2026, 9, 7), pay_starts_on=datetime.date(2026, 9, 30),
        pay_schedule=Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[], until=None, count=None), **pay,
    ))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["MO"], start_time=datetime.time(10, 0), end_time=datetime.time(14, 0),
                               location=None)],
        starts_on=datetime.date(2026, 9, 7), ends_on=datetime.date(2026, 12, 11)))
    return job


def test_a_salary_isnt_lost_to_a_stretch_without_shifts(db, termed, bookstore):
    shifted_job(db, termed, "Lab RA", JobKind.SALARIED, period_amount=800.0)

    result = run(db, termed, no_shifts_from=datetime.date(2026, 12, 1), no_shifts_until=datetime.date(2026, 12, 11))

    assert result.difference == pytest.approx(-370.0, abs=CENT)  # the Bookstore shifts only


def test_a_different_wage_moves_only_the_main_job(db, termed, bookstore):
    other = shifted_job(db, termed, "Tutoring", JobKind.HOURLY, hourly_rate=25.0)
    other.position = 5
    db.commit()

    result = run(db, termed, hourly_rate=20.0)

    assert result.difference == pytest.approx(2590.0 * 20 / 18.5 - 2590.0, abs=0.05)


def test_a_different_wage_scales_every_upcoming_cheque(db, termed, bookstore):
    # $2,590 of upcoming pay at $18.50 becomes $2,800 at $20.
    result = run(db, termed, hourly_rate=20.0)

    assert result.difference == pytest.approx(2590.0 * 20 / 18.5 - 2590.0, abs=0.05)


def test_more_hours_a_week_are_priced_at_the_main_job(db, termed, bookstore):
    # 2 more hours a week from Jan 4 (a Monday) to Jan 31: four weeks at $18.50.
    result = run(db, termed, hours_per_week=2, hours_from=datetime.date(2027, 1, 4),
                 hours_until=datetime.date(2027, 1, 31))

    assert result.difference == pytest.approx(4 * 2 * 18.5, abs=CENT)
    assert result.capped == []


def test_hours_only_come_off_shifts_on_the_schedule(db, termed, bookstore):
    # The schedule ends Dec 11, so nothing can come off in January.
    result = run(db, termed, hours_per_week=-5, hours_from=datetime.date(2027, 1, 4),
                 hours_until=datetime.date(2027, 1, 31))

    assert result.difference == 0
    assert any("fewer scheduled hours" in c for c in result.capped)


def test_spending_more_a_month_costs_it_every_day(db, termed, chequing):
    result = run(db, termed, monthly_spending_change=100.0)

    assert result.difference == pytest.approx(-100.0 * 12 / 365 * DAYS, abs=0.05)


def test_spending_cannot_go_below_nothing(db, termed, chequing):
    result = run(db, termed, monthly_spending_change=-10_000)

    assert any("below nothing" in c for c in result.capped)
    assert result.scenario.ending_balance >= result.baseline.ending_balance


def test_a_purchase_comes_out_on_its_day(db, termed, chequing):
    day = datetime.date(2026, 11, 20)
    result = run(db, termed, purchases=[Purchase(label="laptop", amount=800.0, on_date=day)])

    assert result.difference == pytest.approx(-800.0, abs=CENT)
    before = {p.on_date: p.balance for p in result.baseline.points}
    after = {p.on_date: p.balance for p in result.scenario.points}
    assert after[ANCHOR] == before[ANCHOR]


def test_changes_add_up(db, termed, bookstore):
    one = run(db, termed, monthly_spending_change=50.0).difference
    two = run(db, termed, purchases=[Purchase(label="bike", amount=300.0, on_date=datetime.date(2027, 2, 1))]).difference
    both = run(db, termed, monthly_spending_change=50.0,
               purchases=[Purchase(label="bike", amount=300.0, on_date=datetime.date(2027, 2, 1))]).difference

    assert both == pytest.approx(one + two, abs=CENT)


# ---------------------------------------------------------------- refusals --

@pytest.mark.parametrize("changes", [
    {"purchases": [{"label": "x", "amount": 10.0, "on_date": "2027-05-15"}]},
    {"purchases": [{"label": "x", "amount": 10.0, "on_date": "2026-10-14"}]},
    {"hours_per_week": 2, "hours_from": "2026-01-01"},
])
def test_dates_outside_the_plan_are_refused(db, termed, chequing, changes):
    with pytest.raises(ValueError):
        what_if(db, termed.id, WhatIfIn(**changes), on_day=ANCHOR)


@pytest.mark.parametrize("changes", [
    {"hours_per_week": 41}, {"hourly_rate": 0}, {"hourly_rate": 201}, {"monthly_spending_change": 10_001},
    {"purchases": [{"label": "x", "amount": 100_001, "on_date": "2026-12-01"}]},
    {"no_shifts_from": "2026-12-01"},
    {"no_shifts_from": "2026-12-10", "no_shifts_until": "2026-12-01"},
])
def test_absurd_inputs_are_refused_not_computed(changes):
    with pytest.raises(ValueError):
        WhatIfIn(**changes)


# ------------------------------------------------------- exam season, silo --

def test_exam_season_is_the_three_weeks_up_to_the_last_final(db, termed, chequing):
    for day in (datetime.date(2026, 12, 9), datetime.date(2026, 12, 16)):
        db.add(EventModel(id=uuid.uuid4(), user_id=termed.id, title="Final", kind="final", starts_on=day))
    db.commit()

    season = run(db, termed).exam_season

    assert (season.starts_on, season.ends_on) == (datetime.date(2026, 11, 26), datetime.date(2026, 12, 16))


def test_no_finals_no_suggestion(db, termed, chequing):
    assert run(db, termed).exam_season is None


def test_no_academic_table_is_read(db, termed, bookstore):
    seen: list[str] = []
    bind = db.get_bind()

    def capture(_conn, _cursor, statement, *_args):
        seen.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        run(db, termed, hours_per_week=4, hourly_rate=20.0, monthly_spending_change=25.0,
            no_shifts_from=datetime.date(2026, 12, 1), no_shifts_until=datetime.date(2026, 12, 11))
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    assert seen, "the capture saw no queries, so it proved nothing"
    touched = {name for sql in seen for name in re.findall(r'(?:from|join)\s+"?([a-z_]+)"?', sql)}
    assert {"jobs", "transactions"} <= touched, touched
    assert not touched & ACADEMIC_TABLES, touched & ACADEMIC_TABLES


@pytest.fixture
def client(db, termed):
    app.main.app.dependency_overrides[get_current_user] = lambda: termed
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, termed, chequing, client):
    url = f"/api/finances/{termed.id}/what-if"

    body = client.post(url, json={"monthly_spending_change": 10}).json()
    assert body["difference"] < 0 and "baseline" in body and "scenario" in body
    assert client.post(url, json={"purchases": [{"label": "x", "amount": 5, "on_date": "2099-01-01"}]}).status_code == 422
    assert client.post(url, json={"hours_per_week": 99}).status_code == 422
