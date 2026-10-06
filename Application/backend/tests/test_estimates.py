"""The task loop (Phase 1 D35, D36): actual time, the timer, and the ratio."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import TaskModel, utc_now
from app.Auth.dependencies import get_current_user
from app.Calendar.services.load_service import week_load
from app.Tasks.schemas.task import TaskCreate, TaskUpdate
from app.Tasks.services import estimates_service
from app.Tasks.services.estimates_service import RATIO_MIN_TASKS, TIMER_TRUST_HOURS, estimate_ratio
from app.Tasks.services.task_service import create_task, start_task_timer, stop_task_timer, update_task
from app.shared.dates import user_today
from conftest import make_user


def task(db, user, estimate=None, **fields):
    made = create_task(db, user.id, TaskCreate(title="Essay", estimated_minutes=estimate, **fields))
    return db.query(TaskModel).filter(TaskModel.id == made.id).one()


def finished(db, user, estimate, actual, days_ago=1):
    row = task(db, user, estimate)
    row.actual_minutes, row.done = actual, True
    row.completed_at = utc_now() - timedelta(days=days_ago)
    db.commit()
    return row


@pytest.fixture
def clock(monkeypatch):
    """Moves the timer's clock; starts at a fixed moment."""
    now = {"at": datetime(2026, 10, 6, 12, 0)}
    monkeypatch.setattr(estimates_service, "utc_now", lambda: now["at"])
    return now


# --- the timer -------------------------------------------------------------

def test_the_timer_adds_what_it_measured_and_adds_up(db, user, clock):
    row = task(db, user, 60)
    start_task_timer(db, user.id, row.id)
    clock["at"] += timedelta(minutes=25, seconds=10)
    stopped = stop_task_timer(db, user.id, row.id)
    assert (stopped.added_minutes, stopped.discarded) == (26, False)  # rounded up
    assert stopped.task.timer_started_at is None

    start_task_timer(db, user.id, row.id)
    clock["at"] += timedelta(minutes=30)
    assert stop_task_timer(db, user.id, row.id).task.actual_minutes == 56


def test_a_forgotten_timer_records_nothing(db, user, clock):
    row = task(db, user, 60)
    start_task_timer(db, user.id, row.id)
    clock["at"] += timedelta(hours=TIMER_TRUST_HOURS, minutes=1)
    stopped = stop_task_timer(db, user.id, row.id)
    assert (stopped.added_minutes, stopped.discarded) == (0, True)
    assert stopped.task.actual_minutes is None
    assert stopped.task.timer_started_at is None


def test_starting_a_running_timer_keeps_its_start(db, user, clock):
    row = task(db, user)
    start_task_timer(db, user.id, row.id)
    clock["at"] += timedelta(minutes=10)
    start_task_timer(db, user.id, row.id)
    clock["at"] += timedelta(minutes=10)
    assert stop_task_timer(db, user.id, row.id).added_minutes == 20


def test_stopping_with_no_timer_changes_nothing(db, user):
    row = task(db, user)
    stopped = stop_task_timer(db, user.id, row.id)
    assert (stopped.added_minutes, stopped.discarded, stopped.task.actual_minutes) == (0, False, None)


def test_ticking_off_keeps_the_running_timers_minutes(db, user, clock):
    row = task(db, user, 60)
    start_task_timer(db, user.id, row.id)
    clock["at"] += timedelta(minutes=40)
    done = update_task(db, user.id, row.id, TaskUpdate(done=True))
    assert (done.actual_minutes, done.timer_started_at) == (40, None)


def test_a_finished_task_cannot_start_a_timer(db, user):
    row = task(db, user)
    update_task(db, user.id, row.id, TaskUpdate(done=True))
    with pytest.raises(ValueError, match="finished"):
        start_task_timer(db, user.id, row.id)


def test_the_answer_to_how_long_is_kept_and_can_be_cleared(db, user):
    row = task(db, user, 60)
    assert update_task(db, user.id, row.id, TaskUpdate(done=True, actual_minutes=90)).actual_minutes == 90
    assert update_task(db, user.id, row.id, TaskUpdate(actual_minutes=None)).actual_minutes is None


# --- the ratio -------------------------------------------------------------

def test_no_ratio_until_enough_tasks(db, user):
    for _ in range(RATIO_MIN_TASKS - 1):
        finished(db, user, 60, 90)
    ratio = estimate_ratio(db, user.id)
    assert (ratio.ratio, ratio.tasks, ratio.needed) == (None, RATIO_MIN_TASKS - 1, RATIO_MIN_TASKS)


def test_the_ratio_is_totals_not_a_mean_of_ratios(db, user):
    finished(db, user, 5, 15)  # 3x on its own
    for _ in range(4):
        finished(db, user, 300, 300)
    # (15 + 1200) / (5 + 1200) = 1.0083, where a mean of ratios would be 1.4
    assert estimate_ratio(db, user.id).ratio == 1.01


def test_only_this_users_recent_finished_tasks_with_both_numbers_count(db, user):
    for _ in range(RATIO_MIN_TASKS):
        finished(db, user, 60, 120)
    finished(db, user, 60, 600, days_ago=91)  # too old
    finished(db, user, 60, None)  # never said
    unfinished = task(db, user, 60)
    unfinished.actual_minutes = 600
    db.commit()
    other = make_user(db, "other@example.com")
    for _ in range(RATIO_MIN_TASKS):
        finished(db, other, 60, 6)

    ratio = estimate_ratio(db, user.id)
    assert (ratio.ratio, ratio.tasks) == (2.0, RATIO_MIN_TASKS)


def prefer(db, user, on: bool):
    user.preferences = {**(user.preferences or {}), "use_estimate_ratio": on}
    db.commit()


def test_the_forecast_uses_it_only_when_asked(db, user):
    for _ in range(RATIO_MIN_TASKS):
        finished(db, user, 60, 90)
    today = user_today(db, user.id)
    task(db, user, 120, due_date=today)

    load = week_load(db, user.id, today, today + timedelta(days=6))
    assert (load.estimated_minutes, load.typed_estimated_minutes, load.estimate_ratio) == (120, 120, None)
    assert estimate_ratio(db, user.id).applied is False

    prefer(db, user, True)
    load = week_load(db, user.id, today, today + timedelta(days=6))
    assert (load.estimated_minutes, load.typed_estimated_minutes, load.estimate_ratio) == (180, 120, 1.5)
    assert estimate_ratio(db, user.id).applied is True


def test_asking_for_it_does_nothing_without_enough_tasks(db, user):
    prefer(db, user, True)
    today = user_today(db, user.id)
    task(db, user, 120, due_date=today)
    load = week_load(db, user.id, today, today + timedelta(days=6))
    assert (load.estimated_minutes, load.estimate_ratio) == (120, None)


# --- the routes ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, client):
    row = task(db, user, 60)
    base = f"/api/tasks/{user.id}/tasks"
    assert client.get(f"{base}/estimates").json()["ratio"] is None
    started = client.post(f"{base}/{row.id}/timer/start")
    assert started.status_code == 200 and started.json()["timer_started_at"] is not None
    stopped = client.post(f"{base}/{row.id}/timer/stop")
    assert stopped.status_code == 200 and stopped.json()["task"]["timer_started_at"] is None
    client.patch(f"{base}/{row.id}", json={"done": True})
    assert client.post(f"{base}/{row.id}/timer/start").status_code == 400
    assert client.patch(f"{base}/{row.id}", json={"actual_minutes": 0}).status_code == 422
    assert client.post(f"{base}/{row.id}/timer/stop".replace(str(row.id), "00000000-0000-0000-0000-000000000000")).status_code == 404
