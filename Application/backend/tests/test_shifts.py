"""Confirming what was actually worked on one date of a repeating shift.

A repeating shift is one event row expanded on read, so nothing anywhere
represents "this Friday" until a record is written for it. `(event_id, on_date)`
is the only thing that identifies one.
"""
import datetime

import pytest

from app._database.models import ShiftRecordModel
from app.Jobs.schemas.job import (
    JobCreate,
    JobKind,
    ShiftMeeting,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.services.job_service import (
    confirm_shift,
    create_job,
    list_shifts,
    set_shift_schedule,
)

TERM_START = datetime.date(2026, 9, 7)
TERM_END = datetime.date(2026, 12, 11)
WEEK_START = datetime.date(2026, 10, 5)          # Monday
WEEK_END = datetime.date(2026, 10, 11)
TUESDAY = datetime.date(2026, 10, 6)
# A date after that week, so those shifts read as past.
AFTER = datetime.date(2026, 10, 20)
# A date before it, so they read as still to come.
BEFORE = datetime.date(2026, 9, 1)


@pytest.fixture
def shift(db, user):
    """A job working 09:00-14:00 on Tuesdays and Thursdays."""
    job = create_job(db, user.id, JobCreate(
        name="Campus Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=TERM_START,
    ))
    created = set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(
            days=["TU", "TH"],
            start_time=datetime.time(9, 0),
            end_time=datetime.time(14, 0),
        )],
        starts_on=TERM_START, ends_on=TERM_END,
    ))
    return job, created[0]


def week(db, user, on_day):
    return list_shifts(db, user.id, WEEK_START, WEEK_END, on_day=on_day)


def test_an_upcoming_shift_counts_its_scheduled_hours(db, user, shift):
    tuesday = next(s for s in week(db, user, BEFORE) if s.on_date == TUESDAY)

    assert tuesday.scheduled_minutes == 300
    assert tuesday.counted_minutes == 300
    assert tuesday.confirmed is False
    assert tuesday.assumed is False, "still in the future, so nothing is assumed"


def test_an_unconfirmed_past_shift_counts_and_says_it_is_assumed(db, user, shift):
    """It must not vanish: forgetting the admin is not the same as not working."""
    tuesday = next(s for s in week(db, user, AFTER) if s.on_date == TUESDAY)

    assert tuesday.counted_minutes == 300
    assert tuesday.confirmed is False
    assert tuesday.assumed is True


def test_confirming_different_hours_changes_what_is_counted(db, user, shift):
    _, event_id = shift
    confirm_shift(db, user.id, event_id, TUESDAY, ShiftRecordUpsert(
        worked_start=datetime.time(9, 0),
        worked_end=datetime.time(15, 30),
    ))

    tuesday = next(s for s in week(db, user, AFTER) if s.on_date == TUESDAY)
    assert tuesday.scheduled_minutes == 300
    assert tuesday.counted_minutes == 390
    assert tuesday.confirmed is True
    assert tuesday.assumed is False


def test_confirming_without_times_means_worked_as_scheduled(db, user, shift):
    _, event_id = shift
    confirm_shift(db, user.id, event_id, TUESDAY, ShiftRecordUpsert())

    tuesday = next(s for s in week(db, user, AFTER) if s.on_date == TUESDAY)
    assert tuesday.counted_minutes == 300
    assert tuesday.confirmed is True
    assert tuesday.assumed is False


def test_confirming_twice_leaves_one_record(db, user, shift):
    """An upsert, because the date names the row rather than an id doing it."""
    _, event_id = shift
    confirm_shift(db, user.id, event_id, TUESDAY, ShiftRecordUpsert(
        worked_end=datetime.time(15, 0), worked_start=datetime.time(9, 0)))
    confirm_shift(db, user.id, event_id, TUESDAY, ShiftRecordUpsert(
        worked_end=datetime.time(16, 0), worked_start=datetime.time(9, 0)))

    rows = db.query(ShiftRecordModel).filter(
        ShiftRecordModel.event_id == event_id,
        ShiftRecordModel.on_date == TUESDAY,
    ).all()
    assert len(rows) == 1
    assert rows[0].worked_end == datetime.time(16, 0)


def test_confirming_one_date_leaves_the_others_alone(db, user, shift):
    _, event_id = shift
    confirm_shift(db, user.id, event_id, TUESDAY, ShiftRecordUpsert(
        worked_start=datetime.time(9, 0), worked_end=datetime.time(15, 30)))

    thursday = next(s for s in week(db, user, AFTER)
                    if s.on_date == datetime.date(2026, 10, 8))
    assert thursday.counted_minutes == 300
    assert thursday.confirmed is False


def test_a_tip_and_a_rate_override_ride_on_the_record(db, user, shift):
    _, event_id = shift
    confirm_shift(db, user.id, event_id, TUESDAY, ShiftRecordUpsert(
        tip_amount=45.0, tip_is_cash=True, rate_override=37.0))

    tuesday = next(s for s in week(db, user, AFTER) if s.on_date == TUESDAY)
    assert tuesday.tip_amount == 45.0
    assert tuesday.tip_is_cash is True
    assert tuesday.rate_override == 37.0


def test_half_a_worked_span_is_rejected(db, user, shift):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ShiftRecordUpsert(worked_start=datetime.time(9, 0), worked_end=None)


def test_a_worked_span_cannot_end_before_it_starts(db, user, shift):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ShiftRecordUpsert(
            worked_start=datetime.time(15, 0), worked_end=datetime.time(9, 0))


def test_confirming_something_that_is_not_a_shift_is_refused(db, user, shift):
    import uuid
    assert confirm_shift(
        db, user.id, uuid.uuid4(), TUESDAY, ShiftRecordUpsert()) is None
