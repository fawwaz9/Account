"""The term simulator (Phase 4 item 9, §13.19).

The boundary first, because it is the point: **the work slider moves time and
money and nothing academic**, and nothing academic renders unless study hours are
set directly. Then the 168-hour arithmetic, the exertion pricing, the money side
through the what-if, and the defaults from the student's own figures.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import ActivityModel, GradeModel, TaskModel, TransactionModel
from app.Auth.dependencies import get_current_user
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Insights.schemas.term_sim import WEEK_HOURS, TermIn
from app.Insights.services.term_sim_service import DEFAULT_POINTS_PER_MINUTE, defaults, simulate
from app.Jobs.schemas.job import JobCreate, JobKind, ShiftMeeting, ShiftScheduleCreate
from app.Jobs.services.job_service import create_job, set_shift_schedule
from tests.conftest import make_account, make_course

TODAY = datetime.date(2026, 10, 14)  # a Wednesday; the next four weeks start Oct 19


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    return user


@pytest.fixture
def money(db, termed):
    account = make_account(db, termed.id, "Chequing", share=100.0)
    db.add(TransactionModel(id=uuid.uuid4(), user_id=termed.id, account_id=account.id, kind="income",
                            amount=3000.0, description="x", occurred_on=TODAY))
    db.commit()
    job = create_job(db, termed.id, JobCreate(
        name="Bookstore", kind=JobKind.HOURLY, hourly_rate=20.0,
        started_on=datetime.date(2026, 9, 7), pay_starts_on=datetime.date(2026, 9, 11),
        pay_schedule=Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[], until=None, count=None),
    ))
    # 10 hours a week: Tue and Thu, 09:00-14:00.
    set_shift_schedule(db, termed.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU", "TH"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=datetime.date(2026, 9, 7), ends_on=datetime.date(2026, 12, 11)))
    return job


@pytest.fixture
def course(db, termed):
    """A current course with one marked and one unmarked assessment, and estimated work ahead."""
    row = make_course(db, termed.id, "CPSC 310", year=2, semester="Fall",
                      category_weights={"Assignment": 50.0, "Final": 50.0})
    db.add(GradeModel(id=uuid.uuid4(), course_id=row.id, name="A1", category="Assignment", score=80,
                      max_score=100, weight=0.0))
    db.add(GradeModel(id=uuid.uuid4(), course_id=row.id, name="Final", category="Final", score=None,
                      max_score=100, weight=0.0))
    # 32 hours of estimated work due over the four weeks from Oct 19: 8 a week.
    for n in range(4):
        db.add(TaskModel(id=uuid.uuid4(), user_id=termed.id, title=f"t{n}", course_id=row.id,
                         due_date=datetime.date(2026, 10, 20) + datetime.timedelta(weeks=n), estimated_minutes=480))
    db.commit()
    return row


def sim(db, user, **sliders):
    return simulate(db, user.id, TermIn(**sliders), today=TODAY)


# ----------------------------------------------------------------- the boundary --

@pytest.mark.parametrize("work", [0, 10, 25, 60])
def test_the_work_slider_never_moves_anything_academic(db, termed, money, course, work):
    reference = sim(db, termed, study_hours=6, work_hours=10).academic
    moved = sim(db, termed, study_hours=6, work_hours=work).academic

    assert moved == reference


def test_nothing_academic_renders_without_study_hours_set(db, termed, money, course):
    result = sim(db, termed, work_hours=25)

    assert result.academic is None
    assert any("Set study hours yourself" in a for a in result.assumptions)


def test_the_work_slider_moves_time_and_money(db, termed, money, course):
    light = sim(db, termed, work_hours=5)
    heavy = sim(db, termed, work_hours=25)

    assert heavy.time.total - light.time.total == pytest.approx(20)
    assert heavy.money.difference > light.money.difference


# ------------------------------------------------------------- the 168 hours --

def test_the_week_adds_up_by_room(db, termed):
    result = sim(db, termed, sleep_hours=8, overhead_hours=3, class_hours=15, study_hours=20, work_hours=10,
                 workouts_per_week=3, workout_minutes=60)

    rooms = {r.room: r.hours for r in result.time.rooms}
    assert rooms == {"academic": 35.0, "money": 10.0, "body": 3.0, "life": 77.0}
    assert result.time.total == 125.0 and result.time.fits and result.time.spare == 43.0


def test_a_week_that_doesnt_fit_says_by_how_much(db, termed):
    result = sim(db, termed, sleep_hours=8, overhead_hours=4, class_hours=20, study_hours=40, work_hours=30,
                 workouts_per_week=5, workout_minutes=60)

    assert result.time.total == 179.0 and not result.time.fits
    assert result.time.short_by == 179.0 - WEEK_HOURS and result.time.spare == 0


def test_unset_study_and_work_come_from_the_weeks_ahead(db, termed, money, course):
    result = sim(db, termed, class_hours=0, sleep_hours=8, overhead_hours=0)

    rooms = {r.room: r.hours for r in result.time.rooms}
    assert rooms["academic"] == 8.0   # the tasks' estimates
    assert rooms["money"] == 10.0     # the scheduled shifts


# ---------------------------------------------------------------- the rooms --

def test_study_hours_set_are_measured_against_the_estimates(db, termed, course):
    short = sim(db, termed, study_hours=6).academic
    covered = sim(db, termed, study_hours=10).academic

    assert (short.estimated_hours, short.coverage) == (8.0, 75)
    assert "about 2.0 hours short" in short.reading
    assert covered.coverage == 125 and "covers the 8" in covered.reading


def test_the_bands_are_as_they_stand_and_never_move(db, termed, course):
    a = sim(db, termed, study_hours=1).academic.bands
    b = sim(db, termed, study_hours=40).academic.bands

    assert a == b
    (band,) = a
    assert (band.code, band.worst, band.current, band.best) == ("CPSC 310", 40.0, 80.0, 90.0)


def test_workouts_are_priced_at_your_usual_effort(db, termed):
    # Last weeks: four 30-minute runs at 49 points each (9.8 MET).
    for n in range(4):
        db.add(ActivityModel(id=uuid.uuid4(), user_id=termed.id, on_date=datetime.date(2026, 10, 5) + datetime.timedelta(days=n),
                             kind="run", minutes=30, met=9.8, weight=1.0, points=49, formula_version=1))
    termed.preferences = {**(termed.preferences or {}), "exertion_goal": 200}
    db.commit()

    result = sim(db, termed, workouts_per_week=3, workout_minutes=60)

    assert result.body.points_per_week == round(3 * 60 * 49 / 30)
    assert result.body.goal == 200 and result.body.meets_goal is True


def test_with_nothing_logged_effort_is_moderate(db, termed):
    result = sim(db, termed, workouts_per_week=2, workout_minutes=30)

    assert result.body.points_per_week == round(2 * 30 * DEFAULT_POINTS_PER_MINUTE)
    assert result.body.meets_goal is None


def test_spending_moves_only_money(db, termed, money):
    plain = sim(db, termed)
    spender = sim(db, termed, monthly_spending_change=200)

    assert spender.money.difference < plain.money.difference
    assert spender.time == plain.time and spender.body == plain.body


# ------------------------------------------------------------- the defaults --

def test_defaults_come_from_the_students_own_figures(db, termed, money, course):
    found = defaults(db, termed.id, today=TODAY)

    assert (found.study_hours, found.work_hours, found.sleep_hours, found.overhead_hours) == (8.0, 10.0, 8.0, 3.0)
    assert found.workouts_per_week == 0 and found.workout_minutes == 45


@pytest.fixture
def client(db, termed):
    app.main.app.dependency_overrides[get_current_user] = lambda: termed
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, termed, client):
    assert client.get(f"/api/insights/{termed.id}/term/defaults").json()["sleep_hours"] == 8.0
    body = client.post(f"/api/insights/{termed.id}/term", json={"study_hours": 5}).json()
    assert body["academic"]["study_hours"] == 5 and "time" in body
    assert client.post(f"/api/insights/{termed.id}/term", json={"sleep_hours": 2}).status_code == 422
    assert client.post(f"/api/insights/{termed.id}/term", json={"work_hours": 61}).status_code == 422
