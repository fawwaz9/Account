"""Focus sessions (Phase 4 item 4): a timer tagged per course.

Pinned: one session at a time (starting another stops the first); minutes from
start to stop; a session forgotten past 12 hours records nothing; only your own
courses; per course this week and this term, beside the grade; another user's
sessions never count.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import FocusSessionModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.grade_service import add_grade
from app.Tasks.schemas.focus import FocusStart
from app.Tasks.services.focus_service import TRUST_HOURS, running, start, stop, summary
from conftest import make_course, make_user

# Monday Nov 2, 2026, 15:00 UTC: 09:00 in the fixture user's zone (America/Regina).
T0 = datetime(2026, 11, 2, 15, 0)


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester = 3, "Fall"
    db.commit()
    return user


@pytest.fixture
def cpsc(db, termed):
    return make_course(db, termed.id, "CPSC 310", year=3, semester="Fall")


def test_minutes_from_start_to_stop(db, termed, cpsc):
    start(db, termed.id, FocusStart(course_id=cpsc.id), now=T0)

    stopped = stop(db, termed.id, now=T0 + timedelta(minutes=50, seconds=40))

    assert (stopped.minutes, stopped.course_code) == (50, "CPSC 310")
    assert running(db, termed.id) is None


def test_one_at_a_time(db, termed, cpsc):
    start(db, termed.id, FocusStart(course_id=cpsc.id), now=T0)
    start(db, termed.id, FocusStart(), now=T0 + timedelta(minutes=30))

    rows = db.query(FocusSessionModel).filter(FocusSessionModel.user_id == termed.id).order_by(FocusSessionModel.started_at).all()

    assert [r.minutes for r in rows] == [30, None]


def test_a_forgotten_session_records_nothing(db, termed, cpsc):
    start(db, termed.id, FocusStart(course_id=cpsc.id), now=T0)

    stopped = stop(db, termed.id, now=T0 + timedelta(hours=TRUST_HOURS, minutes=1))

    assert stopped.minutes == 0


def test_stopping_with_nothing_running(db, termed):
    assert stop(db, termed.id, now=T0) is None


def test_only_your_own_courses(db, termed):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_course(db, stranger.id, "MATH 200")

    with pytest.raises(LookupError):
        start(db, termed.id, FocusStart(course_id=theirs.id), now=T0)
    with pytest.raises(LookupError):
        start(db, termed.id, FocusStart(course_id=uuid.uuid4()), now=T0)
    assert running(db, termed.id) is None


def session(db, user, course, started, minutes):
    db.add(FocusSessionModel(id=uuid.uuid4(), user_id=user.id, course_id=course.id if course else None,
                             started_at=started, ended_at=started + timedelta(minutes=minutes), minutes=minutes))
    db.commit()


def test_the_summary_this_week_and_this_term_with_the_grade(db, termed, cpsc):
    add_grade(db, termed.id, cpsc.id, GradeCreate(name="A1", category="Assignment", score=80, max_score=100))
    session(db, termed, cpsc, T0, 60)                          # this week
    session(db, termed, cpsc, T0 - timedelta(days=10), 90)     # earlier this term
    session(db, termed, None, T0, 20)                          # no course

    found = summary(db, termed.id, now=T0 + timedelta(hours=1))

    by_code = {c.course_code: c for c in found.courses}
    assert (by_code["CPSC 310"].minutes_this_week, by_code["CPSC 310"].minutes_term) == (60, 150)
    assert by_code["CPSC 310"].grade == 80.0
    assert (by_code["No course"].minutes_this_week, by_code["No course"].grade) == (20, None)
    assert found.total_this_week == 80


def test_a_course_with_no_focus_still_shows(db, termed, cpsc):
    found = summary(db, termed.id, now=T0)

    (only,) = found.courses
    assert (only.course_code, only.minutes_term, only.grade) == ("CPSC 310", 0, None)


def test_a_running_session_is_shown_and_not_counted(db, termed, cpsc):
    start(db, termed.id, FocusStart(course_id=cpsc.id), now=T0)

    found = summary(db, termed.id, now=T0 + timedelta(minutes=20))

    assert found.running.course_code == "CPSC 310"
    assert found.total_this_week == 0


def test_another_users_sessions_never_count(db, termed, cpsc):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_course(db, stranger.id, "MATH 200")
    session(db, stranger, theirs, T0, 500)
    session(db, stranger, None, T0, 500)

    found = summary(db, termed.id, now=T0)

    assert found.total_this_week == 0 and [c.course_code for c in found.courses] == ["CPSC 310"]


@pytest.fixture
def client(db, termed):
    app.main.app.dependency_overrides[get_current_user] = lambda: termed
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, termed, cpsc, client):
    base = f"/api/tasks/{termed.id}/focus"

    assert client.post(f"{base}/start", json={"course_id": str(cpsc.id)}).status_code == 201
    assert client.get(base).json()["running"]["course_code"] == "CPSC 310"
    assert client.post(f"{base}/stop").json()["minutes"] == 0
    assert client.post(f"{base}/stop").json() is None
    assert client.post(f"{base}/start", json={"course_id": str(uuid.uuid4())}).status_code == 404
