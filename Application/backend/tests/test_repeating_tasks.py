"""Repeating tasks: the recurrence engine's third consumer.

The interesting property is not the expansion -- that is tested in
test_recurrence.py -- but where this sits between the other two consumers. A
class time is never written out; a standing payment is written only once it has
happened; a repeating task is written for a window that runs a little ahead,
because each occurrence is ticked off separately and a future one costs nothing.
"""
from datetime import date, time, timedelta

import pytest

from app._database.models import RecurringTaskModel, TaskModel
from app.Calendar.schemas.event import Recurrence
from app.Tasks.schemas.recurring_task import RecurringTaskCreate, RecurringTaskUpdate
from app.Tasks.services.recurring_task_service import (
    MATERIALISE_AHEAD_DAYS,
    MATERIALISE_BEHIND_DAYS,
    create_rule,
    delete_rule,
    list_rules,
    run_due,
    skip_occurrence,
    update_rule,
)
from app.Tasks.services.task_service import list_tasks, update_task
from app.Tasks.schemas.task import TaskUpdate
from conftest import make_course, make_user

TODAY = date.today()


def weekly(**overrides):
    """A chore every Monday, anchored so occurrences land inside the window."""
    fields = {
        "title": "Readings",
        "notes": None,
        "due_time": None,
        "estimated_minutes": 90,
        "course_id": None,
        "tags": [],
        # A fortnight back, so the backward window and the forward one both hold
        # occurrences whichever weekday the suite runs on.
        "starts_on": TODAY - timedelta(days=14),
        "recurrence": Recurrence(freq="weekly", interval=1, byday=[], until=None, count=None),
        "active": True,
    }
    fields.update(overrides)
    return RecurringTaskCreate(**fields)


def occurrences_of(db, rule_id):
    return (
        db.query(TaskModel)
        .filter(TaskModel.recurring_id == rule_id)
        .order_by(TaskModel.due_date)
        .all()
    )


# ------------------------------------------------------------ materialising --

def test_setting_one_up_writes_its_occurrences_immediately(db, user):
    """Set up on Sunday for Monday, and Monday's is there on Sunday."""
    rule = create_rule(db, user.id, weekly())

    rows = occurrences_of(db, rule.id)
    assert len(rows) > 0
    assert all(task.title == "Readings" for task in rows)


def test_occurrences_are_written_ahead_but_not_forever(db, user):
    rule = create_rule(db, user.id, weekly())

    rows = occurrences_of(db, rule.id)
    latest = max(task.due_date for task in rows)
    earliest = min(task.due_date for task in rows)

    assert latest <= TODAY + timedelta(days=MATERIALISE_AHEAD_DAYS)
    # A chore missed months ago is noise, not work, so the reach back is short.
    assert earliest >= TODAY - timedelta(days=MATERIALISE_BEHIND_DAYS)


def test_running_again_writes_nothing(db, user):
    """The property that makes it safe on every page load."""
    rule = create_rule(db, user.id, weekly())
    before = len(occurrences_of(db, rule.id))

    result = run_due(db, user.id)

    assert result.created == 0
    assert len(occurrences_of(db, rule.id)) == before


def test_a_daily_chore_does_not_fill_the_table(db, user):
    rule = create_rule(db, user.id, weekly(
        recurrence=Recurrence(freq="daily", interval=1, byday=[], until=None, count=None)))

    rows = occurrences_of(db, rule.id)
    assert len(rows) <= MATERIALISE_AHEAD_DAYS + MATERIALISE_BEHIND_DAYS + 1


def test_an_inactive_rule_writes_nothing(db, user):
    rule = create_rule(db, user.id, weekly(active=False))

    assert occurrences_of(db, rule.id) == []


def test_the_template_stamps_every_occurrence(db, user):
    course = make_course(db, user.id, "CPSC 221")
    rule = create_rule(db, user.id, weekly(
        title="Lab prep", notes="Read the handout", estimated_minutes=45,
        course_id=course.id, tags=["weekly"], due_time=time(17, 0),
    ))

    for task in occurrences_of(db, rule.id):
        assert task.title == "Lab prep"
        assert task.notes == "Read the handout"
        assert task.estimated_minutes == 45
        assert task.course_id == course.id
        assert task.tags == ["weekly"]
        assert task.due_time == time(17, 0)


def test_occurrences_carry_the_course_code(db, user):
    course = make_course(db, user.id, "CPSC 221")
    create_rule(db, user.id, weekly(course_id=course.id))

    assert all(task.course_code == "CPSC 221" for task in list_tasks(db, user.id))


# ------------------------------------------ each occurrence stands alone ---

def test_ticking_one_occurrence_leaves_the_others(db, user):
    """The whole reason these are rows rather than expanded on read."""
    rule = create_rule(db, user.id, weekly())
    rows = occurrences_of(db, rule.id)
    outstanding = [task for task in rows if not task.done]

    update_task(db, user.id, outstanding[0].id, TaskUpdate(done=True))

    still_open = [task for task in occurrences_of(db, rule.id) if not task.done]
    assert len(still_open) == len(outstanding) - 1


def test_a_repeating_chore_counts_toward_the_weeks_hours(db, user):
    create_rule(db, user.id, weekly(estimated_minutes=90))

    week = list_tasks(db, user.id, start=TODAY, end=TODAY + timedelta(days=7))
    assert all(task.estimated_minutes == 90 for task in week)


# ----------------------------------------------------------------- editing --

def test_editing_the_rule_does_not_rewrite_work_already_recorded(db, user):
    """Last week's completed chore is a record of what was done, not a template."""
    rule = create_rule(db, user.id, weekly())
    first = occurrences_of(db, rule.id)[0]
    update_task(db, user.id, first.id, TaskUpdate(done=True))

    update_rule(db, user.id, rule.id, RecurringTaskUpdate(title="Readings (new book)"))

    done = [task for task in occurrences_of(db, rule.id) if task.done]
    assert done[0].title == "Readings"


def test_pausing_stops_new_occurrences(db, user):
    rule = create_rule(db, user.id, weekly())
    before = len(occurrences_of(db, rule.id))

    update_rule(db, user.id, rule.id, RecurringTaskUpdate(active=False))
    run_due(db, user.id)

    assert len(occurrences_of(db, rule.id)) == before


def test_skipping_one_occurrence_removes_that_row_only(db, user):
    rule = create_rule(db, user.id, weekly())
    rows = occurrences_of(db, rule.id)
    target = next(task.due_date for task in rows if task.due_date > TODAY)

    skip_occurrence(db, user.id, rule.id, target)

    remaining = [task.due_date for task in occurrences_of(db, rule.id)]
    assert target not in remaining
    assert len(remaining) == len(rows) - 1


def test_a_skipped_occurrence_does_not_come_back_on_the_next_run(db, user):
    rule = create_rule(db, user.id, weekly())
    target = next(t.due_date for t in occurrences_of(db, rule.id) if t.due_date > TODAY)
    skip_occurrence(db, user.id, rule.id, target)

    run_due(db, user.id)

    assert target not in [task.due_date for task in occurrences_of(db, rule.id)]


def test_skipping_does_not_remove_one_already_done(db, user):
    """It is a record of work done; cancelling the plan cannot undo the doing."""
    rule = create_rule(db, user.id, weekly())
    first = occurrences_of(db, rule.id)[0]
    update_task(db, user.id, first.id, TaskUpdate(done=True))

    skip_occurrence(db, user.id, rule.id, first.due_date)

    assert any(task.id == first.id for task in occurrences_of(db, rule.id))


# ---------------------------------------------------------------- stopping --

def test_stopping_keeps_what_was_done_and_clears_what_was_not(db, user):
    rule = create_rule(db, user.id, weekly())
    rows = occurrences_of(db, rule.id)
    update_task(db, user.id, rows[0].id, TaskUpdate(done=True))

    delete_rule(db, user.id, rule.id)

    assert db.query(RecurringTaskModel).count() == 0
    surviving = db.query(TaskModel).all()
    assert len(surviving) == 1
    assert surviving[0].done is True
    # The link goes with the rule, but the record of the work does not.
    assert surviving[0].recurring_id is None


def test_stopping_can_keep_the_outstanding_ones(db, user):
    rule = create_rule(db, user.id, weekly())
    before = len(occurrences_of(db, rule.id))

    delete_rule(db, user.id, rule.id, drop_pending=False)

    assert db.query(TaskModel).count() == before


# -------------------------------------------------------------- validation --

def test_the_next_occurrence_is_reported(db, user):
    create_rule(db, user.id, weekly())

    [rule] = list_rules(db, user.id)

    assert rule.next_due_on is not None
    assert rule.next_due_on >= TODAY


def test_a_repeat_cannot_end_before_it_starts(db, user):
    with pytest.raises(ValueError, match="cannot end before"):
        weekly(recurrence=Recurrence(
            freq="weekly", interval=1, byday=[],
            until=TODAY - timedelta(days=30), count=None,
        ))


def test_another_users_course_cannot_be_used(db, user):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_course(db, stranger.id, "MATH 100")

    with pytest.raises(ValueError, match="Course not found"):
        create_rule(db, user.id, weekly(course_id=theirs.id))


def test_another_users_repeating_tasks_are_not_visible(db, user):
    stranger = make_user(db, "stranger@example.com")
    create_rule(db, stranger.id, weekly(title="Not yours"))

    assert list_rules(db, user.id) == []
