"""Jobs, and shifts as events on the calendar.

The point of making a shift an event rather than its own table is that four
existing behaviours come for free. Most of these tests exist to prove they
actually did, because each one would fail silently.
"""
import datetime
import uuid

import pytest

from app._database.models import EventModel, JobModel
from app.Calendar.schemas.blackout import TermBlackoutCreate
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Calendar.services.blackout_service import create_blackout
from app.Calendar.services.event_service import list_occurrences
from app.Calendar.services.load_service import crunch, free_blocks
from app.Jobs.schemas.job import (
    JobCreate,
    JobKind,
    JobUpdate,
    ShiftMeeting,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.services.job_service import (
    confirm_shift,
    create_job,
    delete_job,
    get_job,
    list_jobs,
    list_shifts,
    next_pay_on,
    set_shift_schedule,
    update_job,
)

TERM_START = datetime.date(2026, 9, 7)   # a Monday
TERM_END = datetime.date(2026, 12, 11)
MID_TERM = datetime.date(2026, 10, 5)    # a Monday well inside the term


def hourly_job(db, user, name="Campus Bookstore", rate=18.5):
    return create_job(db, user.id, JobCreate(
        name=name, employer="UBC", kind=JobKind.HOURLY, hourly_rate=rate,
        started_on=TERM_START, ended_on=None, pay_starts_on=None,
        pay_schedule=None, archived=False,
    ))


def schedule(db, user, job, days=("TU", "TH"), start=(9, 0), end=(14, 0)):
    return set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(
            days=list(days),
            start_time=datetime.time(*start),
            end_time=datetime.time(*end),
            location="Front desk",
        )],
        starts_on=TERM_START,
        ends_on=TERM_END,
    ))


# --- the job itself ------------------------------------------------------

def test_an_hourly_job_needs_a_rate():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobCreate(name="Bookstore", kind=JobKind.HOURLY, hourly_rate=None)


def test_a_salaried_job_needs_a_period_amount():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobCreate(name="TA-ship", kind=JobKind.SALARIED, period_amount=None)


def test_a_job_cannot_hold_both_kinds_of_pay():
    """Two answers to \"what should this have paid\" and nothing to choose between."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobCreate(
            name="Bookstore", kind=JobKind.HOURLY,
            hourly_rate=18.5, period_amount=2400.0,
        )


def test_changing_kind_clears_the_other_kinds_field(db, user):
    """The rule the update schema cannot enforce, because a patch sees one field."""
    job = hourly_job(db, user)

    changed = update_job(db, user.id, job.id, JobUpdate(
        kind=JobKind.SALARIED, period_amount=2400.0))

    assert changed.kind == JobKind.SALARIED
    assert changed.period_amount == 2400.0
    assert changed.hourly_rate is None


def test_current_jobs_sort_above_ones_you_have_left(db, user):
    left = create_job(db, user.id, JobCreate(
        name="Old cafe", kind=JobKind.HOURLY, hourly_rate=16.0,
        started_on=datetime.date(2026, 5, 1),
    ))
    update_job(db, user.id, left.id, JobUpdate(ended_on=datetime.date(2026, 8, 1)))
    hourly_job(db, user, name="Bookstore")

    assert [job.name for job in list_jobs(db, user.id)] == ["Bookstore", "Old cafe"]


def test_a_job_with_no_pay_rule_predicts_nothing(db, user):
    job = hourly_job(db, user)
    assert get_job(db, user.id, job.id).next_pay_on is None


def test_the_next_pay_date_is_read_from_the_rule(db, user):
    """Every second Friday, expanded by the same engine as a timetable."""
    job = create_job(db, user.id, JobCreate(
        name="Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=TERM_START,
        pay_starts_on=datetime.date(2026, 9, 11),  # a Friday
        pay_schedule=Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[],
                                until=None, count=None),
    ))
    row = db.query(JobModel).filter(JobModel.id == job.id).one()

    # From the 12th, the next in the fortnightly series is the 25th.
    assert next_pay_on(row, datetime.date(2026, 9, 12)) == datetime.date(2026, 9, 25)


# --- shifts as events ----------------------------------------------------

def test_a_schedule_writes_one_event_per_pattern_row(db, user):
    job = hourly_job(db, user)
    created = schedule(db, user, job)

    assert len(created) == 1
    events = db.query(EventModel).filter(EventModel.job_id == job.id).all()
    assert len(events) == 1 and events[0].kind == "shift"


def test_resubmitting_the_schedule_replaces_rather_than_appends(db, user):
    job = hourly_job(db, user)
    schedule(db, user, job)
    schedule(db, user, job, start=(10, 0))

    events = db.query(EventModel).filter(EventModel.job_id == job.id).all()
    assert len(events) == 1
    assert events[0].start_time == datetime.time(10, 0)


def test_a_shift_appears_in_the_calendar_window(db, user):
    job = hourly_job(db, user)
    schedule(db, user, job)

    week = list_occurrences(db, user.id, MID_TERM, MID_TERM + datetime.timedelta(days=6))
    shifts = [item for item in week if item.kind == "shift"]

    # Tuesday and Thursday of that week.
    assert len(shifts) == 2
    assert all(item.job_id == job.id for item in shifts)


def test_a_shift_reduces_the_free_blocks_it_covers(db, user):
    """Work competes with study for the same hours, with no code that knows it."""
    job = hourly_job(db, user)
    tuesday = datetime.date(2026, 10, 6)

    before = free_blocks(db, user.id, tuesday, tuesday, now=datetime.datetime(2026, 9, 1, 6, 0))
    schedule(db, user, job)
    after = free_blocks(db, user.id, tuesday, tuesday, now=datetime.datetime(2026, 9, 1, 6, 0))

    assert sum(block.minutes for block in after) < sum(block.minutes for block in before)


def test_a_shift_carries_no_academic_weight(db, user):
    """CRUNCH_WEIGHTS.get(kind, 0) already excludes it; this proves it stayed so."""
    job = hourly_job(db, user)
    schedule(db, user, job)

    strip = crunch(db, user.id, TERM_START, TERM_END)
    assert all(week.weight == 0 for week in strip.weeks)


def test_a_reading_break_does_not_cancel_a_shift(db, user):
    """Blackouts skip course-linked events only. You still turn up to work."""
    job = hourly_job(db, user)
    schedule(db, user, job)
    create_blackout(db, user.id, TermBlackoutCreate(
        label="Reading break",
        starts_on=datetime.date(2026, 10, 5),
        ends_on=datetime.date(2026, 10, 9),
    ))

    week = list_occurrences(db, user.id, MID_TERM, MID_TERM + datetime.timedelta(days=6))
    assert len([item for item in week if item.kind == "shift"]) == 2


def test_a_class_meeting_refuses_to_be_a_shift(db, user):
    """The guard CLASS_KINDS actually provides.

    Written after the first version of this test turned out to be vacuous:
    adding SHIFT to CLASS_KINDS broke nothing, because what protects a shift
    from a timetable rewrite is the `course_id` match below, not the kind. What
    CLASS_KINDS really controls is what the class form will accept.
    """
    from pydantic import ValidationError

    from app.Calendar.schemas.event import ClassMeeting, EventKind

    with pytest.raises(ValidationError):
        ClassMeeting(
            kind=EventKind.SHIFT, days=["MO"],
            start_time=datetime.time(9, 0), end_time=datetime.time(10, 0),
        )


def test_replacing_a_course_timetable_leaves_shifts_alone(db, user):
    """Guarded by course_id: a shift belongs to a job and has no course."""
    from app.Calendar.schemas.event import ClassMeeting, ClassScheduleCreate, EventKind
    from app.Calendar.services.class_schedule_service import set_class_schedule
    from tests.conftest import make_course

    job = hourly_job(db, user)
    schedule(db, user, job)
    course = make_course(db, user.id, "COSC 111", start_date=TERM_START, end_date=TERM_END)

    set_class_schedule(db, user.id, course.id, ClassScheduleCreate(
        meetings=[ClassMeeting(
            kind=EventKind.LECTURE, days=["MO"],
            start_time=datetime.time(10, 0), end_time=datetime.time(11, 0),
        )],
        starts_on=TERM_START, ends_on=TERM_END,
    ))

    assert db.query(EventModel).filter(EventModel.job_id == job.id).count() == 1


def test_a_job_with_a_confirmed_shift_can_still_be_deleted(db, user):
    """It could not. The blocks were bulk-deleted while a shift record still
    pointed at one, the foreign key refused, and the route answered 500 -- for
    every job with even one confirmed shift. Found by test_noninterference.py.

    A cash tip already filed stays in the ledger, as the delete dialog says.
    """
    from app._database.models import ShiftRecordModel, TransactionModel
    from app.Jobs.schemas.job import ShiftCreate, ShiftRecordUpsert
    from app.Jobs.services.job_service import add_shift, confirm_shift, set_cash_tip_account
    from conftest import make_account

    cash = make_account(db, user.id, "Cash")
    set_cash_tip_account(db, user.id, cash.id)
    job = hourly_job(db, user)
    on = datetime.date(2026, 9, 14)
    event = add_shift(db, user.id, job.id, ShiftCreate(
        on_date=on, start_time=datetime.time(9), end_time=datetime.time(13)))
    confirm_shift(db, user.id, event, on,
                  ShiftRecordUpsert(confirmed=True, tip_amount=20.0, tip_is_cash=True))

    delete_job(db, user.id, job.id)

    assert db.query(JobModel).filter(JobModel.id == job.id).count() == 0
    assert db.query(EventModel).filter(EventModel.job_id == job.id).count() == 0
    assert db.query(ShiftRecordModel).filter(ShiftRecordModel.job_id == job.id).count() == 0
    tips = db.query(TransactionModel).filter(TransactionModel.user_id == user.id).all()
    assert [t.amount for t in tips] == [20.0]


def test_deleting_a_job_takes_its_calendar_blocks_with_it(db, user):
    job = hourly_job(db, user)
    schedule(db, user, job)

    delete_job(db, user.id, job.id)

    assert db.query(EventModel).filter(EventModel.job_id == job.id).count() == 0
