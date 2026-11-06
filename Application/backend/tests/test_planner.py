"""The weekly planner (Phase 4 item 2, D7).

Pinned: every placeable task placed before it's due, soonest due first; never a
double booking and never outside the study window; long work split into blocks of
at most two hours; what doesn't fit is listed with the shortfall; each choice
explained; time already accepted counts; acceptance re-checks the calendar, takes
only your own open tasks, and marks its events as the planner's.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import EventModel, TaskModel
from app.Auth.dependencies import get_current_user
from app.Calendar.schemas.planner import AcceptBlock, AcceptPlan
from app.Calendar.services.planner_service import BREAK_MINUTES, DEFAULT_MINUTES, MAX_CHUNK, SOURCE, accept, plan_week
from conftest import make_user

NOW = datetime(2026, 11, 2, 8, 0)   # Monday, 8am
TODAY = NOW.date()


@pytest.fixture
def window(db, user):
    """Study window 09:00-17:00, blocks of 30 minutes or more."""
    user.preferences = {**(user.preferences or {}), "study_day_start": "09:00:00", "study_day_end": "17:00:00",
                        "min_free_block_minutes": 30}
    db.commit()
    return user


def task(db, user, title, due_in, estimate=None, priority=3, **fields):
    row = TaskModel(id=uuid.uuid4(), user_id=user.id, title=title, due_date=TODAY + timedelta(days=due_in),
                    estimated_minutes=estimate, priority=priority, **fields)
    db.add(row)
    db.commit()
    return row


def busy(db, user, day_offset, start, end, title="class"):
    db.add(EventModel(id=uuid.uuid4(), user_id=user.id, title=title, kind="lecture",
                      starts_on=TODAY + timedelta(days=day_offset), start_time=start, end_time=end))
    db.commit()


def overlaps(blocks):
    by_day = {}
    for b in blocks:
        by_day.setdefault(b.on_date, []).append((b.starts_at, b.ends_at))
    for spans in by_day.values():
        spans.sort()
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            return True
    return False


# ------------------------------------------------------------- placement --

def test_a_task_lands_in_the_first_free_time_before_its_due(db, window):
    t = task(db, window, "Essay", due_in=2, estimate=90)

    (block,) = plan_week(db, window.id, NOW).blocks

    assert (block.task_id, block.on_date, block.starts_at, block.ends_at) == (t.id, TODAY, time(9), time(10, 30))
    assert "first free time" in block.reason


def test_soonest_due_goes_first_then_the_most_important(db, window):
    task(db, window, "later", due_in=3, estimate=60)
    task(db, window, "a minor", due_in=1, estimate=60, priority=1)   # first alphabetically, last by priority
    task(db, window, "z major", due_in=1, estimate=60, priority=5)

    titles = [b.title for b in plan_week(db, window.id, NOW).blocks]

    assert titles == ["z major", "a minor", "later"]


def test_long_work_is_split_into_blocks_of_two_hours_at_most(db, window):
    task(db, window, "Project", due_in=3, estimate=300)

    blocks = plan_week(db, window.id, NOW).blocks

    assert sum(b.minutes for b in blocks) == 300
    assert max(b.minutes for b in blocks) <= MAX_CHUNK
    assert "More of it" in blocks[1].reason
    # A break between two blocks of the same task on the same day.
    assert (blocks[1].starts_at.hour * 60 + blocks[1].starts_at.minute) - (
        blocks[0].ends_at.hour * 60 + blocks[0].ends_at.minute) == BREAK_MINUTES


def test_never_over_an_event_and_never_outside_the_window(db, window):
    busy(db, window, 0, time(9), time(12))
    busy(db, window, 0, time(13), time(17))
    task(db, window, "Lab", due_in=0, estimate=60)

    (block,) = plan_week(db, window.id, NOW).blocks

    assert (block.starts_at, block.ends_at) == (time(12), time(13))


def test_no_two_blocks_overlap(db, window):
    for n in range(6):
        task(db, window, f"t{n}", due_in=n % 3, estimate=100)

    blocks = plan_week(db, window.id, NOW).blocks

    assert not overlaps(blocks)
    for b in blocks:
        assert time(9) <= b.starts_at and b.ends_at <= time(17)


def test_a_later_day_says_why(db, window):
    task(db, window, "urgent", due_in=0, estimate=450)      # with its breaks, all of today
    task(db, window, "report", due_in=2, estimate=60)

    report = next(b for b in plan_week(db, window.id, NOW).blocks if b.title == "report")

    assert report.on_date == TODAY + timedelta(days=1)
    assert "because the free time before it went to work due sooner" in report.reason


def test_what_doesnt_fit_is_said_not_squeezed(db, window):
    busy(db, window, 0, time(9), time(16))
    task(db, window, "Essay", due_in=0, estimate=180)       # one hour free today

    plan = plan_week(db, window.id, NOW)

    assert sum(b.minutes for b in plan.blocks) == 60
    (missed,) = plan.unplaced
    assert (missed.minutes_needed, missed.minutes_short) == (180, 120)
    assert "Only 60 of 180 minutes" in missed.reason


def test_a_due_time_cuts_off_the_due_day(db, window):
    task(db, window, "Quiz", due_in=0, estimate=120, due_time=time(10))

    plan = plan_week(db, window.id, NOW)

    assert sum(b.minutes for b in plan.blocks) == 60
    assert plan.blocks[0].ends_at == time(10)


def test_estimates_and_what_is_done(db, window):
    task(db, window, "no estimate", due_in=1)
    task(db, window, "half done", due_in=1, estimate=120, actual_minutes=60)
    task(db, window, "nearly done", due_in=1, estimate=60, actual_minutes=55)

    minutes = {b.title: b.minutes for b in plan_week(db, window.id, NOW).blocks}

    assert minutes == {"no estimate": DEFAULT_MINUTES, "half done": 60}


def test_no_block_is_shorter_than_the_shortest_free_block(db, window):
    busy(db, window, 0, time(10, 30), time(17))   # 90 minutes free today
    task(db, window, "Lab", due_in=1, estimate=100)  # 90 today, 10 left over

    blocks = plan_week(db, window.id, NOW).blocks

    assert [b.minutes for b in blocks] == [90, 30]


def test_overdue_work_takes_the_first_free_time(db, window):
    task(db, window, "late", due_in=-2, estimate=60)

    (block,) = plan_week(db, window.id, NOW).blocks

    assert block.on_date == TODAY and "overdue" in block.reason


def test_done_snoozed_far_and_other_peoples_tasks_stay_out(db, window):
    task(db, window, "done", due_in=1, estimate=60, done=True)
    task(db, window, "snoozed", due_in=1, estimate=60, snoozed_until=TODAY + timedelta(days=1))
    task(db, window, "far", due_in=20, estimate=60)
    stranger = make_user(db, "stranger@example.com")
    task(db, stranger, "theirs", due_in=1, estimate=60)

    assert plan_week(db, window.id, NOW).blocks == []


def test_time_already_accepted_counts(db, window):
    t = task(db, window, "Essay", due_in=3, estimate=120)
    db.add(EventModel(id=uuid.uuid4(), user_id=window.id, title="Essay", kind="personal", starts_on=TODAY + timedelta(days=1),
                      start_time=time(9), end_time=time(10, 30), source=SOURCE, planned_task_id=t.id))
    db.commit()

    blocks = [b for b in plan_week(db, window.id, NOW).blocks if b.task_id == t.id]

    assert sum(b.minutes for b in blocks) == 30


# ---------------------------------------------------------------- accept --

def test_accepting_writes_the_planners_events(db, window):
    t = task(db, window, "Essay", due_in=2, estimate=90)
    (block,) = plan_week(db, window.id, NOW).blocks

    result = accept(db, window.id, AcceptPlan(blocks=[AcceptBlock(task_id=t.id, on_date=block.on_date,
                                                                  starts_at=block.starts_at, ends_at=block.ends_at)]), NOW)

    assert result.created == 1
    (event,) = db.query(EventModel).filter(EventModel.source == SOURCE).all()
    assert (event.planned_task_id, event.user_id, event.start_time, event.end_time) == (t.id, window.id, time(9), time(10, 30))


def test_accepted_time_is_not_planned_again(db, window):
    t = task(db, window, "Essay", due_in=2, estimate=90)
    (block,) = plan_week(db, window.id, NOW).blocks
    accept(db, window.id, AcceptPlan(blocks=[AcceptBlock(task_id=t.id, on_date=block.on_date, starts_at=block.starts_at,
                                                         ends_at=block.ends_at)]), NOW)

    assert plan_week(db, window.id, NOW).blocks == []


def test_a_block_on_something_booked_since_is_refused(db, window):
    t = task(db, window, "Essay", due_in=2, estimate=60)
    busy(db, window, 0, time(9), time(10))

    with pytest.raises(ValueError):
        accept(db, window.id, AcceptPlan(blocks=[AcceptBlock(task_id=t.id, on_date=TODAY, starts_at=time(9),
                                                             ends_at=time(10))]), NOW)


def test_only_your_own_open_tasks(db, window):
    stranger = make_user(db, "stranger@example.com")
    theirs = task(db, stranger, "theirs", due_in=1, estimate=60)
    done = task(db, window, "done", due_in=1, estimate=60, done=True)

    for task_id in (theirs.id, done.id, uuid.uuid4()):
        with pytest.raises(LookupError):
            accept(db, window.id, AcceptPlan(blocks=[AcceptBlock(task_id=task_id, on_date=TODAY, starts_at=time(9),
                                                                 ends_at=time(10))]), NOW)
    assert db.query(EventModel).count() == 0


def test_overlapping_blocks_and_far_days_are_refused(db, window):
    t = task(db, window, "Essay", due_in=2, estimate=60)
    pair = [AcceptBlock(task_id=t.id, on_date=TODAY, starts_at=time(9), ends_at=time(10)),
            AcceptBlock(task_id=t.id, on_date=TODAY, starts_at=time(9, 30), ends_at=time(10, 30))]

    with pytest.raises(ValueError):
        accept(db, window.id, AcceptPlan(blocks=pair), NOW)
    with pytest.raises(ValueError):
        accept(db, window.id, AcceptPlan(blocks=[AcceptBlock(task_id=t.id, on_date=TODAY + timedelta(days=9),
                                                             starts_at=time(9), ends_at=time(10))]), NOW)


def test_a_block_must_end_after_it_starts():
    with pytest.raises(ValueError):
        AcceptBlock(task_id=uuid.uuid4(), on_date=TODAY, starts_at=time(10), ends_at=time(9))


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, window, client):
    body = client.get(f"/api/calendar/{window.id}/planner").json()

    assert set(body) >= {"blocks", "unplaced", "assumptions"}
    bad = {"blocks": [{"task_id": str(uuid.uuid4()), "on_date": body["starts_on"], "starts_at": "09:00", "ends_at": "10:00"}]}
    assert client.post(f"/api/calendar/{window.id}/planner/accept", json=bad).status_code == 404


# ----------------------------------------------------------- daily limit --
# D28: with 11 hours due the planner once put 9.5 of them on one Sunday. The
# student sets the ceiling in Settings; four hours until they do.

def per_day(blocks):
    totals = {}
    for b in blocks:
        totals[b.on_date] = totals.get(b.on_date, 0) + b.minutes
    return totals


def test_no_day_is_planned_past_four_hours_by_default(db, window):
    task(db, window, "Project", due_in=1, estimate=660)

    plan = plan_week(db, window.id, NOW)

    assert max(per_day(plan.blocks).values()) == 240
    (short,) = plan.unplaced
    assert short.minutes_short == 660 - 480
    assert "inside your daily limit of 4 hours" in short.reason
    assert any("At most 4 hours of planned study a day" in a for a in plan.assumptions)


def test_the_students_own_limit_is_used(db, window):
    window.preferences = {**window.preferences, "planner_daily_minutes": 90}
    db.commit()
    task(db, window, "Project", due_in=3, estimate=300)

    plan = plan_week(db, window.id, NOW)

    assert max(per_day(plan.blocks).values()) == 90
    assert sum(b.minutes for b in plan.blocks) == 300
    assert any("At most 1.5 hours" in a for a in plan.assumptions)


def test_a_limit_above_the_free_time_changes_nothing(db, window):
    """Eight free hours a day and a limit of sixteen: the old plan, block for block."""
    window.preferences = {**window.preferences, "planner_daily_minutes": 960}
    db.commit()
    task(db, window, "Project", due_in=1, estimate=660)

    plan = plan_week(db, window.id, NOW)

    assert sum(b.minutes for b in plan.blocks) == 660
    assert max(per_day(plan.blocks).values()) > 240


def test_blocks_already_accepted_count_toward_the_day(db, window):
    """Planning twice must not take a day past the limit."""
    other = task(db, window, "Reading", due_in=5, estimate=60)
    db.add(EventModel(id=uuid.uuid4(), user_id=window.id, title="Reading", kind="personal", starts_on=TODAY,
                      start_time=time(9), end_time=time(12), source=SOURCE, planned_task_id=other.id))
    db.commit()
    t = task(db, window, "Essay", due_in=0, estimate=120)

    blocks = [b for b in plan_week(db, window.id, NOW).blocks if b.task_id == t.id]

    assert sum(b.minutes for b in blocks) == 60


def test_your_own_events_do_not_count_toward_the_limit(db, window):
    """The limit is on what the planner proposes; a lecture is not planned study."""
    busy(db, window, 0, time(9), time(12))
    t = task(db, window, "Essay", due_in=0, estimate=240)

    blocks = [b for b in plan_week(db, window.id, NOW).blocks if b.task_id == t.id]

    assert sum(b.minutes for b in blocks) == 240


def test_a_short_window_still_says_free_time(db, window):
    """Out of free time rather than out of limit: the reason must not blame the limit."""
    busy(db, window, 0, time(9), time(16, 30))
    task(db, window, "Essay", due_in=0, estimate=120)

    (short,) = plan_week(db, window.id, NOW).unplaced

    assert "are free" in short.reason and "limit" not in short.reason

