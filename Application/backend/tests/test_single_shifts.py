"""Shifts entered one at a time, which is how part-time work actually arrives.

A weekly pattern is the exception here, not the rule: student shifts are rarely
the same hours twice. Both have to coexist, and the trap is that saving a
pattern used to delete every shift the job had.
"""
import datetime
import uuid

import pytest

from app._database.models import EventModel, ShiftRecordModel
from tests.conftest import make_account
from app.Jobs.schemas.job import (
    JobCreate,
    JobKind,
    ShiftCreate,
    ShiftMeeting,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.services.job_service import (
    add_shift,
    confirm_shift,
    create_job,
    list_shifts,
    remove_shift,
    set_cash_tip_account,
    set_shift_schedule,
)

TERM_START = datetime.date(2026, 9, 7)
TERM_END = datetime.date(2026, 12, 11)
MON = datetime.date(2026, 10, 5)
WED = datetime.date(2026, 10, 7)
WEEK_END = datetime.date(2026, 10, 11)
LATER = datetime.date(2026, 10, 20)


@pytest.fixture
def job(db, user):
    return create_job(db, user.id, JobCreate(
        name="Campus Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=TERM_START,
    ))


@pytest.fixture
def accounts_ready(db, user):
    """An account taking an income share, so a cash tip has somewhere to land."""
    return make_account(db, user.id, "Chequing", share=100.0)


def one_off(db, user, job, *, on, start=(9, 0), end=(14, 0)):
    return add_shift(db, user.id, job.id, ShiftCreate(
        on_date=on, start_time=datetime.time(*start),
        end_time=datetime.time(*end), location="Front desk",
    ))


def pattern(db, user, job, days=("TU",)):
    return set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=list(days), start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))


def week(db, user, on_day=LATER):
    return list_shifts(db, user.id, MON, WEEK_END, on_day=on_day)


# --- one shift at a time --------------------------------------------------

def test_a_single_shift_appears_on_its_date(db, user, job):
    one_off(db, user, job, on=MON)

    shifts = week(db, user)
    assert len(shifts) == 1
    assert shifts[0].on_date == MON
    assert shifts[0].scheduled_minutes == 300


def test_two_shifts_on_the_same_day_both_stand(db, user, job):
    """A split shift, or two jobs in a day. Nothing should merge them."""
    one_off(db, user, job, on=MON, start=(9, 0), end=(12, 0))
    one_off(db, user, job, on=MON, start=(17, 0), end=(21, 0))

    shifts = [s for s in week(db, user) if s.on_date == MON]
    assert len(shifts) == 2
    assert sorted(s.scheduled_minutes for s in shifts) == [180, 240]


def test_shifts_of_different_lengths_are_kept_as_entered(db, user, job):
    """The point of one-at-a-time entry: no two weeks are the same."""
    one_off(db, user, job, on=MON, start=(9, 0), end=(13, 0))
    one_off(db, user, job, on=WED, start=(14, 0), end=(21, 30))

    by_date = {s.on_date: s.scheduled_minutes for s in week(db, user)}
    assert by_date == {MON: 240, WED: 450}


def test_a_single_shift_carries_no_rule(db, user, job):
    one_off(db, user, job, on=MON)

    event = db.query(EventModel).filter(EventModel.job_id == job.id).one()
    assert event.recur_freq is None


def test_a_shift_cannot_end_before_it_starts(db, user, job):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ShiftCreate(on_date=MON, start_time=datetime.time(14, 0),
                    end_time=datetime.time(9, 0), location=None)


def test_adding_to_a_job_that_is_not_yours(db, user, job):
    assert add_shift(db, user.id, uuid.uuid4(), ShiftCreate(
        on_date=MON, start_time=datetime.time(9, 0),
        end_time=datetime.time(10, 0), location=None)) is None


# --- the two must coexist -------------------------------------------------

def test_saving_a_pattern_does_not_delete_one_off_shifts(db, user, job):
    """The bug this change had to fix: replace used to mean every shift."""
    one_off(db, user, job, on=MON)
    one_off(db, user, job, on=WED)

    pattern(db, user, job)

    dates = {s.on_date for s in week(db, user)}
    assert MON in dates and WED in dates, "hand-entered shifts survived"
    assert datetime.date(2026, 10, 6) in dates, "and the pattern's Tuesday is there"


def test_resaving_a_pattern_still_replaces_the_pattern(db, user, job):
    """Narrowing the delete must not turn replace into append."""
    pattern(db, user, job, days=["TU"])
    pattern(db, user, job, days=["TH"])

    recurring = db.query(EventModel).filter(
        EventModel.job_id == job.id, EventModel.recur_freq.isnot(None)).all()
    assert len(recurring) == 1
    assert recurring[0].recur_byday == "TH"


def test_a_pattern_and_a_one_off_can_fall_on_the_same_day(db, user, job):
    """Picking up an extra shift on a day you already work."""
    pattern(db, user, job, days=["TU"])
    tuesday = datetime.date(2026, 10, 6)
    one_off(db, user, job, on=tuesday, start=(17, 0), end=(20, 0))

    same_day = [s for s in week(db, user) if s.on_date == tuesday]
    assert len(same_day) == 2


# --- removing -------------------------------------------------------------

def test_removing_a_one_off_takes_its_record_with_it(db, user, job):
    event_id = one_off(db, user, job, on=MON)
    confirm_shift(db, user.id, event_id, MON, ShiftRecordUpsert(tip_amount=20.0))

    remove_shift(db, user.id, event_id)

    assert week(db, user) == []
    assert db.query(ShiftRecordModel).count() == 0


def test_a_pattern_shift_cannot_be_removed_this_way(db, user, job):
    """It has no row of its own; cancelling one is a skipped date on the rule."""
    created = pattern(db, user, job)

    with pytest.raises(ValueError, match="repeating pattern"):
        remove_shift(db, user.id, created[0])


def test_removing_something_that_is_not_a_shift(db, user, job):
    assert remove_shift(db, user.id, uuid.uuid4()) is None


# --- it behaves like any other shift --------------------------------------

def test_a_one_off_can_be_confirmed_like_any_other(db, user, job):
    event_id = one_off(db, user, job, on=MON)

    confirm_shift(db, user.id, event_id, MON, ShiftRecordUpsert(
        worked_start=datetime.time(9, 0), worked_end=datetime.time(15, 30)))

    shift = week(db, user)[0]
    assert shift.counted_minutes == 390
    assert shift.confirmed is True


def test_a_one_off_reduces_free_time_like_any_other(db, user, job):
    from app.Calendar.services.load_service import free_blocks

    now = datetime.datetime(2026, 9, 1, 6, 0)
    before = sum(b.minutes for b in free_blocks(db, user.id, MON, MON, now=now))
    one_off(db, user, job, on=MON)
    after = sum(b.minutes for b in free_blocks(db, user.id, MON, MON, now=now))

    assert after == before - 300


# --- deleting a shift, and what it must take with it ----------------------

def test_a_one_off_shift_says_it_does_not_repeat(db, user, job):
    one_off(db, user, job, on=MON)

    assert week(db, user)[0].repeats is False


def test_a_pattern_date_says_it_repeats(db, user, job):
    pattern(db, user, job, days=["MO"])

    assert week(db, user)[0].repeats is True


def test_deleting_a_confirmed_shift_with_a_cash_tip_removes_the_tip_from_the_ledger(
    db, user, job, accounts_ready
):
    """The mistake case: a shift confirmed with a tip, then found to be wrong.

    A bulk delete of just the ShiftRecordModel would leave the tip's ledger
    rows behind, explaining money no shift accounts for any more -- the same
    fault an orphaned tuition payment or paycheque was made of.
    """
    from app._database.models import TransactionModel

    set_cash_tip_account(db, user.id, accounts_ready.id)
    event_id = one_off(db, user, job, on=MON)
    confirm_shift(db, user.id, event_id, MON, ShiftRecordUpsert(
        tip_amount=45.0, tip_is_cash=True))
    assert db.query(TransactionModel).filter(TransactionModel.kind == "income").count() > 0

    remove_shift(db, user.id, event_id)

    assert db.query(TransactionModel).filter(TransactionModel.kind == "income").count() == 0
    assert db.query(ShiftRecordModel).count() == 0


def test_deleting_an_unconfirmed_shift_touches_no_ledger_rows(db, user, job, accounts_ready):
    """The ordinary case: nothing was ever recorded, so nothing to clean up."""
    from app._database.models import TransactionModel

    before = db.query(TransactionModel).count()
    event_id = one_off(db, user, job, on=MON)

    remove_shift(db, user.id, event_id)

    assert db.query(TransactionModel).count() == before
    assert week(db, user) == []
