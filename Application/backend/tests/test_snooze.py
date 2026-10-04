"""Snoozing a task, and keeping the reason.

The rule the whole feature rests on: `due_date` never moves. Moving it would
hide the deferral rather than record it, and would make the completion-timing
figure measure against a date the student chose instead of the one they were
given.
"""
import datetime
import uuid

import pytest

from app._database.models import TaskModel, TaskSnoozeModel
from app.shared.dates import user_today
from app.Tasks.schemas.task import SnoozeRequest, TaskCreate
from app.Tasks.services.task_service import (
    create_task,
    delete_task,
    list_tasks,
    snooze_history,
    snooze_task,
    wake_task,
)

TOMORROW = datetime.date.today() + datetime.timedelta(days=1)
NEXT_WEEK = datetime.date.today() + datetime.timedelta(days=7)
DUE = datetime.date.today() + datetime.timedelta(days=2)


def a_task(db, user, title="Lab report", due=DUE):
    return create_task(db, user.id, TaskCreate(
        title=title, notes=None, due_date=due, due_time=None,
        estimated_minutes=None, course_id=None, tags=[],
    ))


def titles(tasks):
    return [task.title for task in tasks]


def test_a_snoozed_task_leaves_the_list(db, user):
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason="waiting on marks"))

    assert titles(list_tasks(db, user.id)) == []


def test_the_due_date_does_not_move(db, user):
    """The whole point. Everything about lateness depends on it."""
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason=None))

    row = db.query(TaskModel).filter(TaskModel.id == task.id).one()
    assert row.due_date == DUE
    assert row.snoozed_until == NEXT_WEEK


def test_it_can_be_asked_for_anyway(db, user):
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason=None))

    assert titles(list_tasks(db, user.id, include_snoozed=True)) == ["Lab report"]


def test_an_expired_snooze_brings_it_back_on_its_own(db, user):
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=TOMORROW, reason=None))

    # The snooze runs out; nothing runs to make that happen.
    row = db.query(TaskModel).filter(TaskModel.id == task.id).one()
    row.snoozed_until = datetime.date.today() - datetime.timedelta(days=1)
    db.commit()

    assert titles(list_tasks(db, user.id)) == ["Lab report"]


def test_it_returns_in_its_own_place(db, user):
    """Sorted by the date it always had, not by when the snooze ended."""
    later = a_task(db, user, title="Later", due=DUE + datetime.timedelta(days=5))
    sooner = a_task(db, user, title="Sooner", due=DUE)

    snooze_task(db, user.id, sooner.id, SnoozeRequest(until=TOMORROW, reason=None))
    row = db.query(TaskModel).filter(TaskModel.id == sooner.id).one()
    row.snoozed_until = datetime.date.today() - datetime.timedelta(days=1)
    db.commit()

    assert titles(list_tasks(db, user.id)) == ["Sooner", "Later"], later.title


def test_every_snooze_is_kept(db, user):
    """Three snoozes for one reason is the finding; the latest alone cannot say it."""
    task = a_task(db, user)
    for _ in range(3):
        snooze_task(db, user.id, task.id, SnoozeRequest(
            until=NEXT_WEEK, reason="waiting on lab partner"))

    history = snooze_history(db, user.id, task.id)
    assert len(history) == 3
    assert {entry.reason for entry in history} == {"waiting on lab partner"}


def test_the_row_carries_the_count_and_the_latest_reason(db, user):
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason="first"))
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason="second"))

    listed = list_tasks(db, user.id, include_snoozed=True)[0]
    assert listed.snooze_count == 2
    assert listed.last_snooze_reason == "second"


def test_waking_a_task_keeps_the_history(db, user):
    """Undoing a snooze does not undo having made it."""
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason="waiting"))

    woken = wake_task(db, user.id, task.id)

    assert woken.snoozed_until is None
    assert titles(list_tasks(db, user.id)) == ["Lab report"]
    assert len(snooze_history(db, user.id, task.id)) == 1


def test_a_snooze_needs_a_future_date(db, user):
    task = a_task(db, user)

    # Today on the student's clock. With the machine's, on a UTC runner in the
    # evening Regina time, "today" was the student's tomorrow -- a valid future
    # date -- and the refusal this test exists to see never came.
    with pytest.raises(ValueError, match="future"):
        snooze_task(db, user.id, task.id, SnoozeRequest(
            until=user_today(db, user.id), reason=None))


def test_a_finished_task_cannot_be_snoozed(db, user):
    from app.Tasks.schemas.task import TaskUpdate
    from app.Tasks.services.task_service import update_task

    task = a_task(db, user)
    update_task(db, user.id, task.id, TaskUpdate(done=True))

    with pytest.raises(ValueError, match="already done"):
        snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason=None))


def test_a_blank_reason_is_stored_as_none(db, user):
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason="   "))

    assert snooze_history(db, user.id, task.id)[0].reason is None


def test_deleting_a_task_removes_its_snoozes(db, user):
    task = a_task(db, user)
    snooze_task(db, user.id, task.id, SnoozeRequest(until=NEXT_WEEK, reason="waiting"))

    delete_task(db, user.id, task.id)

    assert db.query(TaskSnoozeModel).count() == 0


def test_snoozing_something_that_is_not_yours(db, user):
    assert snooze_task(db, user.id, uuid.uuid4(),
                       SnoozeRequest(until=NEXT_WEEK, reason=None)) is None


def test_a_snoozed_task_still_counts_as_late_when_finished(db, user):
    """The timing figure is measured against the date you were given.

    This is what the untouched due_date buys, and it is the reason the feature
    was built this way rather than by moving the date.
    """
    from app.Tasks.services.timing_service import completion_timing

    user.preferences = {"timezone": "America/Regina"}
    db.commit()

    task = TaskModel(
        id=uuid.uuid4(), user_id=user.id, title="Essay", tags=[],
        due_date=datetime.date(2026, 9, 10),
        snoozed_until=datetime.date(2026, 9, 14),
        done=True, archived=True,
        completed_at=datetime.datetime(2026, 9, 15, 18, 0),
    )
    db.add(task)
    db.commit()

    week = completion_timing(db, user.id, on_day=datetime.date(2026, 9, 15)).past_week
    assert week.counted == 1
    assert week.mean_days == 5.0, "five days late against the original date"
