"""Editing a repeating rule, and what it does to the occurrences already written.

The bug these cover: `materialise` only ever adds dates that are missing, so
every occurrence written before an edit kept the old template. With a sixty-day
window that is sixty-odd stale rows, and editing a rule looked like it did
nothing whatsoever.
"""
import datetime

import pytest

from app._database.models import TaskModel
from app.Calendar.schemas.event import Frequency, Recurrence, Weekday
from app.Tasks.schemas.recurring_task import RecurringTaskCreate, RecurringTaskUpdate
from app.Tasks.services import recurring_task_service as svc
from app.shared.dates import user_today


def daily_rule(db, user, *, starts_on=None, title="Take out the bins"):
    """A daily rule starting yesterday, so it has both past and future rows."""
    return svc.create_rule(db, user.id, RecurringTaskCreate(
        title=title, notes=None, due_time=None, estimated_minutes=None,
        course_id=None, tags=[],
        starts_on=starts_on or user_today(db, user.id) - datetime.timedelta(days=3),
        recurrence=Recurrence(freq=Frequency.DAILY, interval=1, byday=[],
                              until=None, count=None),
        active=True,
    ))


def weekly_rule(db, user, day: Weekday):
    """Weekly on one weekday, starting four weeks back."""
    return svc.create_rule(db, user.id, RecurringTaskCreate(
        title="Readings", notes=None, due_time=None, estimated_minutes=None,
        course_id=None, tags=[],
        starts_on=user_today(db, user.id) - datetime.timedelta(days=28),
        recurrence=Recurrence(freq=Frequency.WEEKLY, interval=1, byday=[day],
                              until=None, count=None),
        active=True,
    ))


def rows(db, rule):
    return db.query(TaskModel).filter(TaskModel.recurring_id == rule.id).all()


def test_renaming_reaches_every_outstanding_occurrence(db, user):
    rule = daily_rule(db, user)
    svc.materialise(db, user.id, rule)
    db.commit()
    assert len(rows(db, rule)) > 1, "fixture should write a window of occurrences"

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(title="Bins out"))

    assert {task.title for task in rows(db, rule)} == {"Bins out"}


def test_a_completed_occurrence_keeps_what_it_said(db, user):
    """History is not rewritten: last week's done chore keeps its old name."""
    rule = daily_rule(db, user)
    svc.materialise(db, user.id, rule)
    db.commit()

    finished = next(t for t in rows(db, rule)
                    if t.due_date < user_today(db, user.id))
    finished.done = True
    finished.archived = True
    finished.completed_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    finished_id = finished.id

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(title="Bins out"))

    kept = db.query(TaskModel).filter(TaskModel.id == finished_id).one()
    assert kept.title == "Take out the bins"


def test_an_overdue_occurrence_still_follows_the_rule(db, user):
    """Overdue is outstanding work, not a record, so it takes the new title."""
    rule = daily_rule(db, user)
    svc.materialise(db, user.id, rule)
    db.commit()

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(title="Bins out"))

    overdue = [t for t in rows(db, rule) if t.due_date < user_today(db, user.id)]
    assert overdue, "fixture should have written occurrences in the past"
    assert {task.title for task in overdue} == {"Bins out"}


def test_time_estimate_and_tags_all_follow(db, user):
    rule = daily_rule(db, user)
    svc.materialise(db, user.id, rule)
    db.commit()

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(
        due_time=datetime.time(20, 0), estimated_minutes=15, tags=["home"]))

    updated = rows(db, rule)
    assert {task.due_time for task in updated} == {datetime.time(20, 0)}
    assert {task.estimated_minutes for task in updated} == {15}
    assert all(task.tags == ["home"] for task in updated)


def test_moving_the_weekday_clears_the_old_future_dates(db, user):
    """Monday to Thursday must not leave the Mondays sitting beside them."""
    rule = weekly_rule(db, user, Weekday.MO)
    svc.materialise(db, user.id, rule)
    db.commit()

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(
        recurrence=Recurrence(freq=Frequency.WEEKLY, interval=1,
                              byday=[Weekday.TH], until=None, count=None)))

    future = [t for t in rows(db, rule) if t.due_date >= user_today(db, user.id)]
    assert future, "the new weekday should have been written"
    # 0 = Monday, 3 = Thursday
    assert {task.due_date.weekday() for task in future} == {3}


def test_moving_the_weekday_does_not_disturb_the_past(db, user):
    """The past is left exactly as it was -- nothing erased, nothing invented.

    Both halves matter. An old Monday was genuinely assigned, so deleting it
    would erase work the student may still mean to do; and a new Thursday in the
    past was never assigned, so back-filling one hands over an overdue task that
    never existed.
    """
    rule = weekly_rule(db, user, Weekday.MO)
    svc.materialise(db, user.id, rule)
    db.commit()
    before = [t.due_date for t in rows(db, rule) if t.due_date < user_today(db, user.id)]
    assert before, "fixture should have written occurrences in the past"

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(
        recurrence=Recurrence(freq=Frequency.WEEKLY, interval=1,
                              byday=[Weekday.TH], until=None, count=None)))

    after = [t.due_date for t in rows(db, rule) if t.due_date < user_today(db, user.id)]
    assert sorted(after) == sorted(before)


def test_a_new_rule_still_catches_up_on_the_recent_past(db, user):
    """The look-back is right on a first run and must survive the edit fix."""
    rule = weekly_rule(db, user, Weekday.MO)
    svc.materialise(db, user.id, rule)
    db.commit()

    past = [t.due_date for t in rows(db, rule) if t.due_date < user_today(db, user.id)]
    assert past, "a rule starting four weeks back should catch up recent dates"


def test_editing_twice_does_not_duplicate_anything(db, user):
    """resync runs before materialise, so the two must not fight."""
    rule = daily_rule(db, user)
    svc.materialise(db, user.id, rule)
    db.commit()
    count = len(rows(db, rule))

    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(title="One"))
    svc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(title="Two"))

    assert len(rows(db, rule)) == count
    assert {task.title for task in rows(db, rule)} == {"Two"}
