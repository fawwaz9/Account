"""Reminders: the things that notify rather than wait.

The delivery mechanism is the client asking what is due, so most of what can go
wrong is in the time comparison — and `remind_at` is local wall time, unlike
every other DateTime in the app, which is naive UTC.
"""
import datetime
import uuid

import pytest

from app._database.models import ReminderModel
from app.Tasks.schemas.reminder import ReminderCreate, ReminderUpdate
from app.Tasks.services.reminder_service import (
    create_reminder,
    delete_reminder,
    dismiss_reminder,
    due_reminders,
    list_reminders,
    local_now,
    update_reminder,
)
from tests.conftest import make_course

REGINA = "America/Regina"  # UTC-6 all year, so no daylight-saving wrinkle


@pytest.fixture
def regina(db, user):
    user.preferences = {"timezone": REGINA}
    db.commit()
    return user


def a_reminder(db, user, *, at, title="Email Dr Hale"):
    return create_reminder(db, user.id, ReminderCreate(
        title=title, notes=None, remind_at=at, course_id=None))


def past(db, user, minutes=30):
    return local_now(user) - datetime.timedelta(minutes=minutes)


def future(db, user, minutes=30):
    return local_now(user) + datetime.timedelta(minutes=minutes)


def test_a_reminder_whose_moment_has_passed_is_due(db, regina):
    a_reminder(db, regina, at=past(db, regina))

    due = due_reminders(db, regina.id)
    assert len(due) == 1 and due[0].due is True


def test_one_still_to_come_is_not(db, regina):
    a_reminder(db, regina, at=future(db, regina))

    assert due_reminders(db, regina.id) == []


def test_local_wall_time_is_what_is_compared(db, regina):
    """The decision that makes this table different from every other DateTime.

    18:00 in Regina is midnight UTC. A reminder set for 17:00 local has passed;
    comparing it against UTC now would say it is seven hours away.
    """
    now = local_now(regina)
    # An hour ago on the student's own clock, whatever that is in UTC.
    a_reminder(db, regina, at=now - datetime.timedelta(hours=1))

    assert len(due_reminders(db, regina.id)) == 1


def test_an_offset_aware_time_is_refused(db, regina):
    """A client sending UTC would fire at the wrong hour, silently."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReminderCreate(
            title="x", notes=None, course_id=None,
            remind_at=datetime.datetime.now(datetime.timezone.utc),
        )


def test_firing_is_stamped_once_and_not_again(db, regina):
    """A reminder shown Monday and still there Wednesday is the same reminder."""
    a_reminder(db, regina, at=past(db, regina))

    first = due_reminders(db, regina.id)[0]
    assert first.fired_at is not None

    again = due_reminders(db, regina.id)[0]
    assert again.fired_at == first.fired_at


def test_a_dismissed_reminder_does_not_come_back(db, regina):
    a_reminder(db, regina, at=past(db, regina))
    due = due_reminders(db, regina.id)

    dismiss_reminder(db, regina.id, due[0].id)

    assert due_reminders(db, regina.id) == []


def test_dismissing_keeps_the_row(db, regina):
    """What you were reminded of is a record, not something to delete."""
    a_reminder(db, regina, at=past(db, regina))
    due = due_reminders(db, regina.id)
    dismiss_reminder(db, regina.id, due[0].id)

    assert db.query(ReminderModel).count() == 1
    assert list_reminders(db, regina.id, include_dismissed=True)[0].dismissed_at is not None


def test_dismissing_twice_keeps_the_first_time(db, regina):
    a_reminder(db, regina, at=past(db, regina))
    rid = due_reminders(db, regina.id)[0].id

    first = dismiss_reminder(db, regina.id, rid).dismissed_at
    second = dismiss_reminder(db, regina.id, rid).dismissed_at

    assert first == second


def test_moving_the_time_makes_it_pending_again(db, regina):
    """Pushing one to tomorrow must not leave it looking already fired."""
    a_reminder(db, regina, at=past(db, regina))
    rid = due_reminders(db, regina.id)[0].id
    dismiss_reminder(db, regina.id, rid)

    moved = update_reminder(db, regina.id, rid, ReminderUpdate(
        remind_at=future(db, regina)))

    assert moved.fired_at is None
    assert moved.dismissed_at is None
    assert moved.due is False


def test_the_list_hides_dismissed_ones_by_default(db, regina):
    a_reminder(db, regina, at=past(db, regina), title="Done with")
    a_reminder(db, regina, at=future(db, regina), title="Still coming")
    dismiss_reminder(db, regina.id, due_reminders(db, regina.id)[0].id)

    assert [r.title for r in list_reminders(db, regina.id)] == ["Still coming"]
    assert len(list_reminders(db, regina.id, include_dismissed=True)) == 2


def test_reminders_are_ordered_by_when_they_fire(db, regina):
    a_reminder(db, regina, at=future(db, regina, 120), title="Later")
    a_reminder(db, regina, at=future(db, regina, 10), title="Sooner")

    assert [r.title for r in list_reminders(db, regina.id)] == ["Sooner", "Later"]


def test_a_reminder_can_name_a_course(db, regina):
    course = make_course(db, regina.id, "COSC 111")
    created = create_reminder(db, regina.id, ReminderCreate(
        title="Ask about the lab", notes=None,
        remind_at=future(db, regina), course_id=course.id))

    assert created.course_code == "COSC 111"


def test_a_course_that_is_not_yours_is_refused(db, regina):
    with pytest.raises(ValueError, match="Course not found"):
        create_reminder(db, regina.id, ReminderCreate(
            title="x", notes=None, remind_at=future(db, regina),
            course_id=uuid.uuid4()))


def test_deleting_removes_it(db, regina):
    a_reminder(db, regina, at=past(db, regina))
    rid = due_reminders(db, regina.id)[0].id

    delete_reminder(db, regina.id, rid)

    assert db.query(ReminderModel).count() == 0


def test_a_missing_user_is_not_an_empty_list(db, regina):
    assert due_reminders(db, uuid.uuid4()) is None
    assert list_reminders(db, uuid.uuid4()) is None


# --- the clock, pinned ---------------------------------------------------

# 23:30 UTC. In Regina (UTC-6) that is 17:30 the same day.
FIXED_UTC = datetime.datetime(2026, 10, 14, 23, 30, tzinfo=datetime.timezone.utc)
LOCAL_THEN = datetime.datetime(2026, 10, 14, 17, 30)


def test_local_now_resolves_through_the_students_timezone(db, regina):
    assert local_now(regina, FIXED_UTC) == LOCAL_THEN


def test_a_reminder_later_today_is_not_due_yet(db, regina):
    """The assertion the relative tests could not make.

    20:00 local is still to come at 17:30 local — but the same instant is 23:30
    in UTC, so anything comparing against UTC would call it due and fire it
    nearly three hours early. This is the test that fails if the comparison
    stops going through the student's own clock.
    """
    a_reminder(db, regina, at=datetime.datetime(2026, 10, 14, 20, 0))

    assert due_reminders(db, regina.id, at=FIXED_UTC) == []


def test_a_reminder_earlier_today_is_due(db, regina):
    a_reminder(db, regina, at=datetime.datetime(2026, 10, 14, 17, 0))

    assert len(due_reminders(db, regina.id, at=FIXED_UTC)) == 1
