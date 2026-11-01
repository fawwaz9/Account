"""Exam countdown (Phase 4 item 5): inside a week of an exam, its course's work first.

Pinned: the window (7 days, today included); midterms and finals only; an exam
over today has left; each exam carries only its own course's open work, dated
soonest first; another user's exams and tasks never appear.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import EventModel, TaskModel
from app.Auth.dependencies import get_current_user
from app.Tasks.services.countdown_service import MAX_TASKS, WINDOW_DAYS, exam_countdown
from conftest import make_course, make_user

NOW = datetime(2026, 11, 2, 9, 0)
TODAY = NOW.date()


def exam(db, user, course, in_days, kind="midterm", start=time(10), end=time(12), title=None):
    row = EventModel(id=uuid.uuid4(), user_id=user.id, course_id=course.id if course else None,
                     title=title or f"{kind} {in_days}", kind=kind,
                     starts_on=TODAY + timedelta(days=in_days), start_time=start, end_time=end)
    db.add(row)
    db.commit()
    return row


def task(db, user, course, title, due_in=None, done=False, archived=False, estimate=None, priority=3):
    row = TaskModel(id=uuid.uuid4(), user_id=user.id, course_id=course.id if course else None, title=title,
                    due_date=TODAY + timedelta(days=due_in) if due_in is not None else None,
                    done=done, archived=archived, estimated_minutes=estimate, priority=priority)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def cpsc(db, user):
    return make_course(db, user.id, "CPSC 310")


def test_an_exam_inside_the_week_brings_its_course_work(db, user, cpsc):
    exam(db, user, cpsc, 3)
    task(db, user, cpsc, "Practice midterm", due_in=2, estimate=90)
    task(db, user, cpsc, "Review notes", estimate=60)

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert (only.course_code, only.days_left, only.kind) == ("CPSC 310", 3, "midterm")
    assert [t.title for t in only.tasks] == ["Practice midterm", "Review notes"]
    assert (only.open_tasks, only.estimated_minutes) == (2, 150)


def test_the_window_is_seven_days_today_included(db, user, cpsc):
    exam(db, user, cpsc, 0, title="today")
    exam(db, user, cpsc, WINDOW_DAYS, title="last day in")
    exam(db, user, cpsc, WINDOW_DAYS + 1, title="too far")

    titles = [e.title for e in exam_countdown(db, user.id, NOW).exams]

    assert titles == ["today", "last day in"]


def test_only_midterms_and_finals(db, user, cpsc):
    exam(db, user, cpsc, 1, kind="final", title="final")
    exam(db, user, cpsc, 1, kind="lecture", title="lecture")
    exam(db, user, cpsc, 1, kind="deadline", title="deadline")

    assert [e.title for e in exam_countdown(db, user.id, NOW).exams] == ["final"]


def test_an_exam_over_today_has_left(db, user, cpsc):
    exam(db, user, cpsc, 0, start=time(7), end=time(8, 30), title="this morning")
    exam(db, user, cpsc, 0, start=time(8), end=None, title="started, no end")
    exam(db, user, cpsc, 0, start=None, end=None, title="untimed")
    exam(db, user, cpsc, 0, start=time(13), end=time(15), title="this afternoon")

    titles = [e.title for e in exam_countdown(db, user.id, NOW).exams]

    assert titles == ["this afternoon", "untimed"]


def test_only_the_exam_s_own_course_and_only_open_work(db, user, cpsc):
    math = make_course(db, user.id, "MATH 200")
    exam(db, user, cpsc, 2)
    task(db, user, cpsc, "mine")
    task(db, user, math, "other course")
    task(db, user, None, "no course")
    task(db, user, cpsc, "done", done=True)
    task(db, user, cpsc, "archived", archived=True)

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert [t.title for t in only.tasks] == ["mine"]


def test_work_due_after_the_exam_stays_out(db, user, cpsc):
    exam(db, user, cpsc, 3)
    task(db, user, cpsc, "on the day", due_in=3)
    task(db, user, cpsc, "the day after", due_in=4)
    task(db, user, cpsc, "undated")

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert [t.title for t in only.tasks] == ["on the day", "undated"]
    assert only.open_tasks == 2


def test_dated_work_first_then_the_most_important(db, user, cpsc):
    exam(db, user, cpsc, 5)
    task(db, user, cpsc, "undated, important", priority=5)
    task(db, user, cpsc, "due later", due_in=4)
    task(db, user, cpsc, "due sooner", due_in=1)
    task(db, user, cpsc, "undated, minor", priority=1)

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert [t.title for t in only.tasks] == ["due sooner", "due later", "undated, important", "undated, minor"]


def test_lists_a_few_but_counts_them_all(db, user, cpsc):
    exam(db, user, cpsc, 5)
    for n in range(MAX_TASKS + 3):
        task(db, user, cpsc, f"t{n}", due_in=n % 5, estimate=10)

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert len(only.tasks) == MAX_TASKS
    assert (only.open_tasks, only.estimated_minutes) == (MAX_TASKS + 3, 10 * (MAX_TASKS + 3))


def test_an_exam_without_a_course_comes_with_no_work(db, user):
    exam(db, user, None, 2, title="loose exam")
    task(db, user, None, "no course")

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert only.course_id is None and only.tasks == [] and only.open_tasks == 0


def test_another_user_s_exams_and_tasks_never_appear(db, user, cpsc):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_course(db, stranger.id, "CPSC 310")
    exam(db, stranger, theirs, 1, title="theirs")
    task(db, stranger, theirs, "their task")
    exam(db, user, cpsc, 2, title="mine")

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert only.title == "mine" and only.tasks == []


def test_a_stray_row_naming_my_course_is_still_not_mine(db, user, cpsc):
    """Defence in depth: the user filter holds even if a row ever pointed across."""
    stranger = make_user(db, "stray@example.com")
    task(db, stranger, cpsc, "their row on my course")
    exam(db, user, cpsc, 2)

    (only,) = exam_countdown(db, user.id, NOW).exams

    assert only.tasks == [] and only.open_tasks == 0


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, client):
    body = client.get(f"/api/tasks/{user.id}/tasks/exam-countdown").json()

    assert body == {"window_days": WINDOW_DAYS, "exams": []}
