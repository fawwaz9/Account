"""Deadline risk (Phase 4 item 3, §4): velocity against required velocity.

Pinned: the arithmetic, by hand; the cold start, which says nothing until there
is enough history; what counts toward velocity (actual, else estimate; nothing
for a task with neither); overdue work counting toward every later deadline; the
estimate ratio only when asked for; and that another user's tasks never move it.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import TaskModel
from app.Auth.dependencies import get_current_user
from app.Tasks.services.risk_service import NEEDED_DAYS, NEEDED_TASKS, deadline_risk, velocity
from conftest import make_user

TODAY = date(2026, 11, 2)


def task(db, user, **fields):
    row = TaskModel(id=uuid.uuid4(), user_id=user.id, title=fields.pop("title", f"t {uuid.uuid4().hex[:4]}"),
                    **fields)
    db.add(row)
    db.commit()
    return row


def finished(db, user, days_ago, actual=None, estimate=None):
    done_on = datetime.combine(TODAY - timedelta(days=days_ago), time(12))
    return task(db, user, done=True, completed_at=done_on, actual_minutes=actual, estimated_minutes=estimate)


def due(db, user, in_days, estimate, priority=3, title=None):
    return task(db, user, due_date=TODAY + timedelta(days=in_days), estimated_minutes=estimate,
                priority=priority, title=title or f"due {in_days} {uuid.uuid4().hex[:4]}")


@pytest.fixture
def history(db, user):
    """28 days of history: 14 tasks of 60 minutes, so 840 / 28 = 30 minutes a day."""
    for n in range(14):
        finished(db, user, days_ago=2 * n, actual=60)
    # The first task ever, which sets the history to the full window.
    finished(db, user, days_ago=40, actual=600)


# ---------------------------------------------------------------- velocity --

def test_velocity_is_minutes_finished_over_the_window(db, user, history):
    pace, days, counted = velocity(db, user.id, TODAY)

    assert (pace, days, counted) == (30.0, 28, 14)


def test_velocity_counts_actual_else_estimate_else_nothing(db, user):
    finished(db, user, days_ago=9, actual=90, estimate=30)
    finished(db, user, days_ago=5, estimate=45)
    finished(db, user, days_ago=3)

    pace, days, counted = velocity(db, user.id, TODAY)

    assert (days, counted) == (10, 2)
    assert pace == round((90 + 45) / 10, 1)


def test_a_young_history_divides_by_its_own_length(db, user):
    finished(db, user, days_ago=9, actual=100)

    pace, days, _ = velocity(db, user.id, TODAY)

    assert (pace, days) == (10.0, 10)


def test_an_evening_s_work_counts_on_the_user_s_own_day(db, user):
    """Naive UTC 02:00 on the 2nd is 19:00 on the 1st in Vancouver."""
    user.preferences = {**(user.preferences or {}), "timezone": "America/Vancouver"}
    db.commit()
    task(db, user, done=True, completed_at=datetime(2026, 11, 2, 2, 0), actual_minutes=60)

    pace, days, counted = velocity(db, user.id, date(2026, 11, 1))

    assert (days, counted) == (1, 1)


# --------------------------------------------------------------- cold start --

def test_silent_until_enough_days(db, user):
    for n in range(NEEDED_TASKS):
        finished(db, user, days_ago=n, actual=60)
    due(db, user, 1, estimate=600)

    risk = deadline_risk(db, user.id, TODAY)

    assert not risk.ready
    assert risk.deadlines == [] and risk.velocity_minutes_per_day is None
    assert (risk.history_days, risk.needed_days) == (NEEDED_TASKS, NEEDED_DAYS)


def test_silent_until_enough_tasks(db, user):
    for n in range(NEEDED_TASKS - 1):
        finished(db, user, days_ago=20 - n, actual=60)

    risk = deadline_risk(db, user.id, TODAY)

    assert not risk.ready and risk.counted_tasks == NEEDED_TASKS - 1


# --------------------------------------------------------------- the reading --

def test_a_deadline_needing_more_than_your_pace_is_at_risk(db, user, history):
    due(db, user, 1, estimate=120)  # 120 over 2 days = 60/day against 30/day

    risk = deadline_risk(db, user.id, TODAY)

    (only,) = risk.deadlines
    assert (only.days_left, only.minutes_by_then, only.required_minutes_per_day) == (2, 120, 60.0)
    assert only.at_risk and only.shortfall_minutes == 60


def test_a_deadline_within_your_pace_is_not(db, user, history):
    due(db, user, 2, estimate=60)  # 60 over 3 days = 20/day

    (only,) = deadline_risk(db, user.id, TODAY).deadlines

    assert not only.at_risk and only.shortfall_minutes == 0


def test_work_accumulates_toward_later_deadlines(db, user, history):
    due(db, user, 0, estimate=20)
    due(db, user, 2, estimate=200)

    first, second = deadline_risk(db, user.id, TODAY).deadlines

    assert (first.minutes_by_then, first.at_risk) == (20, False)
    assert (second.minutes_by_then, second.days_left) == (220, 3)
    assert second.at_risk and second.shortfall_minutes == 220 - 30 * 3


def test_overdue_work_counts_toward_every_deadline_but_is_not_one(db, user, history):
    due(db, user, -3, estimate=100)
    due(db, user, 2, estimate=0)

    (only,) = deadline_risk(db, user.id, TODAY).deadlines

    assert only.due_date == TODAY + timedelta(days=2)
    assert only.minutes_by_then == 100


def test_a_day_adding_no_estimated_work_is_not_a_new_risk(db, user, history):
    due(db, user, 1, estimate=300)
    due(db, user, 2, estimate=None, title="Email TA")

    first, second = deadline_risk(db, user.id, TODAY).deadlines

    assert first.at_risk and first.own_minutes == 300
    assert second.minutes_by_then == 300 and second.own_minutes == 0
    assert not second.at_risk and second.shortfall_minutes == 0


def test_only_today_tomorrow_and_the_day_after_are_read(db, user, history):
    """Owner, 2026-11-07: at-risk applies to work due in the next 3 days only (was 21)."""
    due(db, user, 2, estimate=10, title="the day after")
    due(db, user, 3, estimate=9999, title="three days out")
    due(db, user, 20, estimate=9999, title="weeks out")

    risk = deadline_risk(db, user.id, TODAY)

    assert risk.horizon_days == 3
    assert [d.titles for d in risk.deadlines] == [["the day after"]]
    assert not risk.deadlines[0].at_risk


def test_work_further_out_raises_no_warning_however_large(db, user, history):
    due(db, user, 3, estimate=99999)
    assert deadline_risk(db, user.id, TODAY).deadlines == []


def test_beyond_the_horizon_and_finished_and_archived_work_are_left_out(db, user, history):
    due(db, user, 30, estimate=9999)
    task(db, user, due_date=TODAY + timedelta(days=2), estimated_minutes=9999, done=True,
         completed_at=datetime.combine(TODAY, time(9)))
    task(db, user, due_date=TODAY + timedelta(days=2), estimated_minutes=9999, archived=True)

    assert deadline_risk(db, user.id, TODAY).deadlines == []


def test_unestimated_tasks_are_counted_and_said(db, user, history):
    due(db, user, 2, estimate=None)
    due(db, user, 2, estimate=30)

    risk = deadline_risk(db, user.id, TODAY)

    assert risk.unestimated_open == 1
    assert risk.deadlines[0].minutes_by_then == 30


def test_titles_put_the_most_important_first(db, user, history):
    due(db, user, 2, estimate=10, priority=1, title="low")
    due(db, user, 2, estimate=10, priority=5, title="high")

    assert deadline_risk(db, user.id, TODAY).deadlines[0].titles == ["high", "low"]


def test_the_estimate_ratio_scales_only_when_asked_for(db, user, history):
    # The fixture's tasks carry no estimates, so add five with both numbers: 2x.
    for n in range(5):
        finished(db, user, days_ago=1 + n, actual=20, estimate=10)
    due(db, user, 2, estimate=100)

    plain = deadline_risk(db, user.id, TODAY)
    user.preferences = {**(user.preferences or {}), "use_estimate_ratio": True}
    db.commit()
    scaled = deadline_risk(db, user.id, TODAY)

    assert plain.estimate_ratio is None and plain.deadlines[0].minutes_by_then == 100
    assert scaled.estimate_ratio == 2.0 and scaled.deadlines[0].minutes_by_then == 200


def test_another_users_tasks_never_move_it(db, user, history):
    stranger = make_user(db, "stranger@example.com")
    for n in range(20):
        finished(db, stranger, days_ago=n, actual=999)
    due(db, stranger, 1, estimate=9999)
    due(db, user, 2, estimate=120)

    risk = deadline_risk(db, user.id, TODAY)

    assert risk.velocity_minutes_per_day == 30.0
    assert [d.minutes_by_then for d in risk.deadlines] == [120]


# --------------------------------------------------------------------- route --

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, history, client):
    body = client.get(f"/api/tasks/{user.id}/tasks/risk").json()

    assert body["ready"] is True and body["needed_days"] == NEEDED_DAYS
    assert "deadlines" in body
