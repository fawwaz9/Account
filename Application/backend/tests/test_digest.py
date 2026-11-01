"""The digest (Phase 4 item 6; read by item 7): one deterministic summary of a day.

Pinned: each part, from the services that already answer it; the plain-text
rendering, line by line; parts with nothing in them left out; and the two rules
that matter most for something that may leave the app through the student's own
assistant: **no money** (D8: no query touches a money table, and no figure in the
text is a dollar amount) and **no one else's rows**.
"""
import re
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.main
from app._database.db import get_db
from app._database.models import EventModel, TaskModel
from app.Auth.dependencies import get_current_user
from app.Briefing.services.digest_service import MAX_LISTED, build_digest, render
from conftest import make_account, make_course, make_user

NOW = datetime(2026, 11, 2, 8, 0)  # a Monday
TODAY = NOW.date()

#: Every table that holds money or pay. The digest may read none of them (D8).
MONEY_TABLES = {
    "accounts", "transactions", "spend_categories", "budget_targets", "account_category_limits",
    "account_category_month_limits", "account_month_values", "sinking_funds", "sinking_contributions",
    "recurring_transactions", "tuition_payments", "tuition_deductions", "jobs", "shift_records",
    "paycheques", "paycheque_deductions", "imports", "saved_plans", "salary_shares", "salary_figures",
    "merchant_categories", "job_applications", "application_steps", "application_seasons",
}


def ev(db, user, title, kind="lecture", start=time(10), end=time(11), on=TODAY, course=None, location=None):
    row = EventModel(id=uuid.uuid4(), user_id=user.id, course_id=course.id if course else None, title=title,
                     kind=kind, starts_on=on, start_time=start, end_time=end, location=location)
    db.add(row)
    db.commit()
    return row


def task(db, user, title, due, course=None, estimate=None, done=False, due_time=None):
    row = TaskModel(id=uuid.uuid4(), user_id=user.id, course_id=course.id if course else None, title=title,
                    due_date=due, due_time=due_time, estimated_minutes=estimate, done=done)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def day(db, user):
    """A Monday with a lecture, a shift, two tasks due, two overdue, a midterm on Thursday."""
    cpsc = make_course(db, user.id, "CPSC 310")
    ev(db, user, "CPSC 310 lecture", course=cpsc, start=time(10), end=time(11), location="DMP 110")
    ev(db, user, "Barista shift", kind="shift", start=time(17), end=time(21))
    ev(db, user, "Midterm 2", kind="midterm", course=cpsc, start=time(18, 30), end=time(20), on=TODAY + timedelta(days=3))
    task(db, user, "Lab 5 write-up", TODAY, course=cpsc, estimate=60)
    task(db, user, "Email TA", TODAY, due_time=time(9))
    task(db, user, "Problem set 6", TODAY - timedelta(days=2))
    task(db, user, "Reading 4", TODAY - timedelta(days=1))
    task(db, user, "Practice midterm", TODAY + timedelta(days=2), course=cpsc, estimate=90)
    task(db, user, "Already done", TODAY, done=True)
    return cpsc


def test_the_parts(db, user, day):
    digest = build_digest(db, user.id, NOW)

    assert digest.on_date == TODAY
    assert [e.title for e in digest.events] == ["CPSC 310 lecture", "Barista shift"]
    assert [t.title for t in digest.due_today] == ["Email TA", "Lab 5 write-up"]
    assert [t.title for t in digest.overdue] == ["Problem set 6", "Reading 4"] and digest.overdue_count == 2
    (exam,) = digest.exams
    assert (exam.name, exam.days_left, exam.open_tasks, exam.estimated_minutes) == ("CPSC 310 midterm", 3, 2, 150)
    assert digest.week.tasks_due >= 3


def test_the_text_line_by_line(db, user, day):
    lines = build_digest(db, user.id, NOW).text.splitlines()

    assert lines[0] == "Monday, November 2."
    assert lines[1] == "Today: CPSC 310 lecture 10am–11am (DMP 110); Barista shift 5pm–9pm."
    assert lines[2] == "Due today: Email TA, Lab 5 write-up (CPSC 310)."
    assert lines[3] == "Overdue: 2 tasks — Problem set 6, Reading 4."
    assert lines[4] == "Exam: CPSC 310 midterm in 3 days — 2 open tasks, about 2h 30m."
    assert any(line.startswith("This week:") for line in lines)


def test_empty_parts_are_left_out(db, user):
    text = build_digest(db, user.id, NOW).text

    assert "Nothing on the calendar today." in text
    for absent in ("Due today", "Overdue", "Exam:", "At risk", "This week"):
        assert absent not in text


def test_overdue_lists_a_few_and_counts_them_all(db, user):
    for n in range(MAX_LISTED + 2):
        task(db, user, f"late {n}", TODAY - timedelta(days=10 - n))

    digest = build_digest(db, user.id, NOW)

    assert len(digest.overdue) == MAX_LISTED and digest.overdue_count == MAX_LISTED + 2
    assert f"and 2 more" in digest.text


def test_deadline_risk_appears_once_it_knows_your_pace(db, user):
    for n in range(14):
        task(db, user, f"done {n}", None, estimate=None, done=True)
    rows = db.query(TaskModel).filter(TaskModel.user_id == user.id, TaskModel.done.is_(True)).all()
    for n, row in enumerate(rows):
        row.completed_at = datetime.combine(TODAY - timedelta(days=2 * n), time(12))
        row.actual_minutes = 30
    db.commit()
    task(db, user, "Essay", TODAY + timedelta(days=1), estimate=600)

    digest = build_digest(db, user.id, NOW)

    (risk,) = digest.at_risk
    assert risk.titles == ["Essay"]
    assert "At risk: Essay (tomorrow) — about" in digest.text


def test_the_same_data_gives_the_same_words(db, user, day):
    assert build_digest(db, user.id, NOW).text == build_digest(db, user.id, NOW).text


# ---------------------------------------------------------------- no money --

def test_no_query_touches_a_money_table(db, user, day):
    """D8, proved on the queries themselves rather than on the output."""
    make_account(db, user.id, "Chequing")  # money exists to be read; the digest must not read it
    seen: list[str] = []
    bind = db.get_bind()

    def capture(_conn, _cursor, statement, *_args):
        seen.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        build_digest(db, user.id, NOW)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    assert seen, "the capture saw no queries, so it proved nothing"
    touched = {name for sql in seen for name in re.findall(r'(?:from|join)\s+"?([a-z_]+)"?', sql)}
    assert touched, "no table names were read from the queries"
    assert not touched & MONEY_TABLES, touched & MONEY_TABLES


def test_no_dollar_figure_in_the_text(db, user, day):
    assert "$" not in build_digest(db, user.id, NOW).text


# ------------------------------------------------------------ no one else's --

def test_another_users_day_never_appears(db, user, day):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_course(db, stranger.id, "MATH 200")
    ev(db, stranger, "their lecture", course=theirs)
    ev(db, stranger, "their final", kind="final", course=theirs, on=TODAY + timedelta(days=1))
    task(db, stranger, "their task", TODAY)
    task(db, stranger, "their late task", TODAY - timedelta(days=1))

    text = build_digest(db, user.id, NOW).text

    assert "their" not in text and "MATH 200" not in text


def test_a_stray_row_never_names_another_users_course(db, user):
    """Defence in depth: a task of mine pointing at a stranger's course shows no code."""
    stranger = make_user(db, "stray@example.com")
    theirs = make_course(db, stranger.id, "SECRET 999")
    task(db, user, "my task", TODAY, course=theirs)

    digest = build_digest(db, user.id, NOW)

    assert digest.due_today[0].course_code is None
    assert "SECRET" not in digest.text


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, client):
    body = client.get(f"/api/briefing/{user.id}/digest").json()

    assert body["text"].splitlines()[0].endswith(".")
    assert set(body) >= {"events", "due_today", "overdue", "exams", "at_risk", "week", "text"}
