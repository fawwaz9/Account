"""Stretches of term when classes do not run.

Two mechanisms that look alike and are not. An event's own skipped_dates cancels
one lecture on one date. A term blackout is the other case: a reading break
applies to every class at once, and entering it on each of six courses is how
one of them ends up wrong.

The scoping is the part worth pinning. This same recurrence engine drives
recurring payments and repeating tasks, and neither cares about reading break --
rent is still due, the bins still need taking out.
"""
import datetime
import uuid

import pytest

from app.Calendar.schemas.blackout import TermBlackoutCreate, TermBlackoutUpdate
from app.Calendar.schemas.event import EventCreate, Frequency, Recurrence
from app.Calendar.services.blackout_service import (
    blackout_dates, create_blackout, delete_blackout, list_blackouts, update_blackout,
)
from app.Calendar.services.event_service import (
    create_event, list_occurrences, update_event,
)
from app.Calendar.schemas.event import EventUpdate
from conftest import make_course

MON = datetime.date(2026, 9, 7)      # a Monday
TERM_END = datetime.date(2026, 12, 7)


def weekly(db, user, title, course=None, starts=MON):
    return create_event(db, user.id, EventCreate(
        title=title, starts_on=starts,
        start_time=datetime.time(10), end_time=datetime.time(11),
        course_id=course.id if course else None,
        recurrence=Recurrence(freq=Frequency.WEEKLY),
    ))


def dates_of(db, user, title, until=TERM_END):
    return [
        o.on_date for o in list_occurrences(db, user.id, MON, until)
        if o.title == title
    ]


def block(db, user, label, start, end):
    return create_blackout(db, user.id, TermBlackoutCreate(
        label=label, starts_on=start, ends_on=end))


# ------------------------------------------------------------ the ranges --

def test_a_single_day_is_a_range_of_one(db, user):
    """A stat holiday and a reading break are the same shape."""
    row = block(db, user, "Remembrance Day", datetime.date(2026, 11, 11),
                datetime.date(2026, 11, 11))
    assert row.days == 1
    assert blackout_dates(db, user.id) == {datetime.date(2026, 11, 11)}


def test_a_range_covers_both_ends(db, user):
    block(db, user, "Reading break", datetime.date(2026, 11, 9),
          datetime.date(2026, 11, 13))
    covered = blackout_dates(db, user.id)
    assert len(covered) == 5
    assert datetime.date(2026, 11, 9) in covered
    assert datetime.date(2026, 11, 13) in covered
    assert datetime.date(2026, 11, 14) not in covered


def test_a_backwards_range_is_refused(db, user):
    with pytest.raises(ValueError, match="ends before it starts"):
        TermBlackoutCreate(label="Nope", starts_on=TERM_END, ends_on=MON)


def test_an_absurd_range_is_refused(db, user):
    """Someone meaning 2026 and typing 2062 would hand the engine tens of
    thousands of dates to subtract."""
    with pytest.raises(ValueError, match="longer than"):
        block(db, user, "Typo", MON, datetime.date(2036, 1, 1))


def test_an_edit_cannot_invert_the_range(db, user):
    """A partial update can move either end, so the pair is checked after both."""
    row = block(db, user, "Reading break", datetime.date(2026, 11, 9),
                datetime.date(2026, 11, 13))
    with pytest.raises(ValueError, match="ends before it starts"):
        update_blackout(db, user.id, row.id,
                        TermBlackoutUpdate(starts_on=datetime.date(2026, 12, 1)))


# --------------------------------------------------------- what it skips --

def test_a_course_class_skips_the_blocked_week(db, user):
    course = make_course(db, user.id, "CPSC 210")
    weekly(db, user, "CPSC 210 lecture", course=course)

    before = dates_of(db, user, "CPSC 210 lecture")
    assert datetime.date(2026, 11, 9) in before

    block(db, user, "Reading break", datetime.date(2026, 11, 9),
          datetime.date(2026, 11, 13))

    after = dates_of(db, user, "CPSC 210 lecture")
    assert datetime.date(2026, 11, 9) not in after
    assert len(after) == len(before) - 1


def test_a_personal_event_is_untouched(db, user):
    """Your gym session is not a class and reading break does not cancel it."""
    weekly(db, user, "Gym")
    block(db, user, "Reading break", datetime.date(2026, 11, 9),
          datetime.date(2026, 11, 13))

    assert datetime.date(2026, 11, 9) in dates_of(db, user, "Gym")


def test_recurring_payments_are_untouched(db, user):
    """Rent is still due during reading break.

    The same engine drives money, so this is the rule that stops a blackout
    reaching somewhere it was never meant to.
    """
    from app._database.models import RecurringTransactionModel
    from app.Finances.services.recurring_service import upcoming
    from conftest import make_account

    account = make_account(db, user.id, "Chequing")
    db.add(RecurringTransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
        amount=900.0, description="Rent", starts_on=MON,
        recur_freq="weekly", recur_interval=1, skipped_dates=[], active=True,
    ))
    db.commit()

    block(db, user, "Reading break", datetime.date(2026, 11, 9),
          datetime.date(2026, 11, 13))

    charges = upcoming(db, user.id, datetime.date(2026, 11, 9),
                       datetime.date(2026, 11, 13))
    assert any(c.on_date == datetime.date(2026, 11, 9) for c in charges)


def test_removing_a_blackout_brings_the_classes_back(db, user):
    course = make_course(db, user.id, "CPSC 210")
    weekly(db, user, "CPSC 210 lecture", course=course)

    row = block(db, user, "Reading break", datetime.date(2026, 11, 9),
                datetime.date(2026, 11, 13))
    assert datetime.date(2026, 11, 9) not in dates_of(db, user, "CPSC 210 lecture")

    delete_blackout(db, user.id, row.id)
    assert datetime.date(2026, 11, 9) in dates_of(db, user, "CPSC 210 lecture")


def test_one_blackout_covers_every_course(db, user):
    """The whole point: entered once, not once per class."""
    for code in ("CPSC 210", "MATH 200", "PHYS 118"):
        course = make_course(db, user.id, code)
        weekly(db, user, f"{code} lecture", course=course)

    block(db, user, "Reading break", datetime.date(2026, 11, 9),
          datetime.date(2026, 11, 13))

    for code in ("CPSC 210", "MATH 200", "PHYS 118"):
        assert datetime.date(2026, 11, 9) not in dates_of(db, user, f"{code} lecture")


def test_a_blackout_belongs_to_its_owner(db, user):
    from conftest import make_user

    stranger = make_user(db, "stranger@blackout.local")
    course = make_course(db, stranger.id, "CPSC 210")
    weekly(db, stranger, "Their lecture", course=course)

    block(db, user, "My reading break", datetime.date(2026, 11, 9),
          datetime.date(2026, 11, 13))

    theirs = [o.on_date for o in list_occurrences(db, stranger.id, MON, TERM_END)]
    assert datetime.date(2026, 11, 9) in theirs


# ------------------------------------------------- blocking at setup time --

def test_dates_can_be_blocked_when_the_event_is_created(db, user):
    """A class you already know does not run on the 14th should never appear there."""
    create_event(db, user.id, EventCreate(
        title="CPSC 210 lecture", starts_on=MON,
        start_time=datetime.time(10), end_time=datetime.time(11),
        recurrence=Recurrence(freq=Frequency.WEEKLY),
        skipped_dates=[datetime.date(2026, 9, 14)],
    ))

    found = dates_of(db, user, "CPSC 210 lecture")
    assert datetime.date(2026, 9, 14) not in found
    assert datetime.date(2026, 9, 21) in found


def test_blocked_dates_can_be_edited_without_a_serialisation_error(db, user):
    """They live in a JSON column, so date objects cannot be assigned into it.

    That exact assignment once made editing any event with a cancelled date fail
    with "Object of type date is not JSON serializable".
    """
    event = weekly(db, user, "CPSC 210 lecture")

    updated = update_event(db, user.id, event.id, EventUpdate(
        skipped_dates=[datetime.date(2026, 9, 14), datetime.date(2026, 9, 21)],
    ))

    assert updated is not None
    found = dates_of(db, user, "CPSC 210 lecture")
    assert datetime.date(2026, 9, 14) not in found
    assert datetime.date(2026, 9, 21) not in found
    assert datetime.date(2026, 9, 28) in found


def test_blocked_dates_are_replaced_not_appended(db, user):
    """SQLAlchemy does not track mutation inside a JSON value."""
    event = weekly(db, user, "CPSC 210 lecture")
    update_event(db, user.id, event.id,
                 EventUpdate(skipped_dates=[datetime.date(2026, 9, 14)]))
    update_event(db, user.id, event.id,
                 EventUpdate(skipped_dates=[datetime.date(2026, 9, 21)]))

    found = dates_of(db, user, "CPSC 210 lecture")
    assert datetime.date(2026, 9, 14) in found       # released
    assert datetime.date(2026, 9, 21) not in found   # now blocked
