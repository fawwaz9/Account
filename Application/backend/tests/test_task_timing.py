"""How early or late work gets finished, measured off completed_at and due_date.

The measurement is a subtraction, so most of what can go wrong here is the time
zone: `completed_at` is naive UTC and `due_date` is a plain local date, and
comparing them directly biases the whole figure toward "late".
"""
import datetime

import pytest

from app._database.models import TaskModel
from app.Tasks.services.timing_service import completion_timing

REGINA = "America/Regina"  # UTC-6 year round, so no daylight-saving wrinkle


@pytest.fixture
def regina(db, user):
    user.preferences = {"timezone": REGINA}
    db.commit()
    return user


def add_task(db, user, *, due_date, completed_utc, done=True, title="Essay"):
    """A task ticked off at a given naive-UTC instant, as utc_now would store it."""
    task = TaskModel(
        id=__import__("uuid").uuid4(), user_id=user.id, title=title,
        due_date=due_date, done=done, archived=done,
        completed_at=completed_utc, tags=[],
    )
    db.add(task)
    db.commit()
    return task


ANCHOR = datetime.date(2026, 9, 12)


def test_evening_work_on_the_due_date_is_on_time(db, regina):
    """The bug this guards: 20:00 in Regina is 02:00 the next day in UTC.

    Subtracting the raw UTC timestamp would call a task finished the evening it
    was due a day late -- and evening is when most work gets done, so the error
    would push nearly every figure in the same direction.
    """
    add_task(db, regina,
             due_date=datetime.date(2026, 9, 11),
             completed_utc=datetime.datetime(2026, 9, 12, 2, 0))

    timing = completion_timing(db, regina.id, on_day=ANCHOR)

    assert timing.past_week.counted == 1
    assert timing.past_week.mean_days == 0.0
    assert timing.past_week.on_time_percent == 100.0


def test_an_undated_task_is_excluded_but_counted_separately(db, regina):
    add_task(db, regina, due_date=None,
             completed_utc=datetime.datetime(2026, 9, 11, 15, 0))

    timing = completion_timing(db, regina.id, on_day=ANCHOR)

    assert timing.past_week.counted == 0
    assert timing.past_week.mean_days is None
    assert timing.undated_completed == 1


def test_early_and_late_cancel_in_the_mean_but_stay_in_the_split(db, regina):
    # Two days early, and two days late.
    add_task(db, regina, due_date=datetime.date(2026, 9, 12),
             completed_utc=datetime.datetime(2026, 9, 10, 15, 0), title="Early")
    add_task(db, regina, due_date=datetime.date(2026, 9, 8),
             completed_utc=datetime.datetime(2026, 9, 10, 15, 0), title="Late")

    week = completion_timing(db, regina.id, on_day=ANCHOR).past_week

    assert week.counted == 2
    assert week.mean_days == 0.0, "they cancel, which is why the split matters"
    assert week.early_count == 1 and week.early_mean_days == 2.0
    assert week.late_count == 1 and week.late_mean_days == 2.0
    assert week.on_time_percent == 50.0


def test_same_day_completion_counts_as_on_time(db, regina):
    add_task(db, regina, due_date=datetime.date(2026, 9, 10),
             completed_utc=datetime.datetime(2026, 9, 10, 15, 0))

    week = completion_timing(db, regina.id, on_day=ANCHOR).past_week

    assert week.on_time_percent == 100.0
    assert week.late_count == 0


def test_an_empty_window_reports_nothing_rather_than_zero(db, regina):
    """Null, not 0.0 -- a zero would read as a week of perfectly punctual work."""
    timing = completion_timing(db, regina.id, on_day=ANCHOR)

    assert timing.past_week.counted == 0
    assert timing.past_week.mean_days is None
    assert timing.past_week.on_time_percent is None
    assert timing.this_month.mean_days is None


def test_the_week_is_a_rolling_seven_days_including_today(db, regina):
    add_task(db, regina, due_date=datetime.date(2026, 9, 6),
             completed_utc=datetime.datetime(2026, 9, 6, 15, 0), title="In, just")
    add_task(db, regina, due_date=datetime.date(2026, 9, 5),
             completed_utc=datetime.datetime(2026, 9, 5, 15, 0), title="Out, just")

    week = completion_timing(db, regina.id, on_day=ANCHOR).past_week

    assert week.starts_on == datetime.date(2026, 9, 6)
    assert week.counted == 1


def test_the_month_is_the_calendar_month_to_date(db, regina):
    add_task(db, regina, due_date=datetime.date(2026, 8, 31),
             completed_utc=datetime.datetime(2026, 8, 31, 15, 0), title="Last month")
    add_task(db, regina, due_date=datetime.date(2026, 9, 1),
             completed_utc=datetime.datetime(2026, 9, 1, 15, 0), title="This month")

    timing = completion_timing(db, regina.id, on_day=ANCHOR)

    assert timing.this_month.starts_on == datetime.date(2026, 9, 1)
    assert timing.this_month.counted == 1
    assert timing.past_week.counted == 0, "neither is inside the rolling week"


def test_work_finished_in_the_future_is_not_counted(db, regina):
    """Guards against a clock skew quietly widening the window."""
    add_task(db, regina, due_date=datetime.date(2026, 9, 20),
             completed_utc=datetime.datetime(2026, 9, 20, 15, 0))

    timing = completion_timing(db, regina.id, on_day=ANCHOR)

    assert timing.this_month.counted == 0


def test_outstanding_work_is_not_counted(db, regina):
    add_task(db, regina, due_date=datetime.date(2026, 9, 10),
             completed_utc=None, done=False)

    assert completion_timing(db, regina.id, on_day=ANCHOR).past_week.counted == 0


def test_a_missing_user_is_not_an_empty_result(db, regina):
    import uuid
    assert completion_timing(db, uuid.uuid4(), on_day=ANCHOR) is None


def test_the_timing_route_is_declared_above_the_task_id_catch_all():
    """FastAPI matches in declaration order, so this ordering is load-bearing.

    Below `/tasks/{task_id}`, "timing" parses as a task id and the endpoint is
    unreachable. That already happened once with `/courses/resolve`, so it is
    asserted rather than left to review.
    """
    from app.main import app

    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/api/tasks/{user_id}/tasks/timing" in paths
    assert paths.index("/api/tasks/{user_id}/tasks/timing") < paths.index(
        "/api/tasks/{user_id}/tasks/{task_id}"
    )
