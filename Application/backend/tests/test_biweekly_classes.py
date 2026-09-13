"""Class times that are not weekly, set per meeting.

Two halves, and the second is the one that is easy to miss. The **interval**
says how often; the **phase** says which week the cycle starts on. Without the
phase every fortnightly meeting is pinned to the odd weeks of term — and a lab
that begins in week two, which is the common case, is a week out for the whole
term while looking perfectly scheduled.
"""
import datetime

import pytest

from app.Calendar.schemas.event import (
    ClassMeeting,
    ClassScheduleCreate,
    EventKind,
)
from app.Calendar.services.class_schedule_service import set_class_schedule
from app.Calendar.services.event_service import list_occurrences
from tests.conftest import make_course

# Term runs Mon 7 Sep to Fri 11 Dec 2026.
TERM_START = datetime.date(2026, 9, 7)
TERM_END = datetime.date(2026, 12, 11)
# Mondays of the first four weeks.
WEEK_1 = datetime.date(2026, 9, 7)
WEEK_2 = datetime.date(2026, 9, 14)
WEEK_3 = datetime.date(2026, 9, 21)
WEEK_4 = datetime.date(2026, 9, 28)


@pytest.fixture
def course(db, user):
    return make_course(db, user.id, "COSC 111",
                       start_date=TERM_START, end_date=TERM_END)


def schedule(db, user, course, meetings):
    return set_class_schedule(db, user.id, course.id, ClassScheduleCreate(
        meetings=meetings, starts_on=TERM_START, ends_on=TERM_END))


def meeting(days, *, kind=EventKind.LECTURE, interval=1, first_on=None, hour=10):
    return ClassMeeting(
        kind=kind, days=days,
        start_time=datetime.time(hour, 0), end_time=datetime.time(hour + 1, 0),
        interval=interval, first_on=first_on,
    )


# Sunday 4 October: exactly four whole weeks from the term start, so a weekly
# meeting falls four times. Ending on the Monday would catch a fifth.
WINDOW_END = datetime.date(2026, 10, 4)


def dates(db, user, kind, through=WINDOW_END):
    items = list_occurrences(db, user.id, TERM_START, through)
    return sorted(item.on_date for item in items if item.kind == kind)


# --- the interval ---------------------------------------------------------

def test_weekly_is_unchanged(db, user, course):
    """The regression that matters: every existing timetable is interval 1."""
    schedule(db, user, course, [meeting(["MO"])])

    assert dates(db, user, "lecture") == [WEEK_1, WEEK_2, WEEK_3, WEEK_4]


def test_fortnightly_skips_a_week(db, user, course):
    schedule(db, user, course, [meeting(["MO"], interval=2)])

    assert dates(db, user, "lecture") == [WEEK_1, WEEK_3]


def test_every_three_weeks(db, user, course):
    schedule(db, user, course, [meeting(["MO"], interval=3)])

    assert dates(db, user, "lecture") == [WEEK_1, WEEK_4]


def test_a_multi_day_fortnightly_meeting_keeps_its_days_together(db, user, course):
    """Both days land in the same on-week rather than drifting apart."""
    schedule(db, user, course, [meeting(["MO", "WE"], interval=2)])

    assert dates(db, user, "lecture") == [
        WEEK_1, datetime.date(2026, 9, 9),      # Mon and Wed of week 1
        WEEK_3, datetime.date(2026, 9, 23),     # Mon and Wed of week 3
    ]


# --- the phase, which is the half that is easy to miss --------------------

def test_without_a_first_date_it_starts_in_week_one(db, user, course):
    schedule(db, user, course, [meeting(["MO"], interval=2)])

    assert dates(db, user, "lecture")[0] == WEEK_1


def test_a_first_date_in_week_two_moves_the_whole_cycle(db, user, course):
    """A lab beginning in week two runs the even weeks, not the odd ones."""
    schedule(db, user, course, [meeting(["MO"], interval=2, first_on=WEEK_2)])

    assert dates(db, user, "lecture") == [WEEK_2, WEEK_4]


def test_a_weekly_meeting_ignores_a_first_date(db, user, course):
    """There is no phase to choose when every week is an on-week."""
    schedule(db, user, course, [meeting(["MO"], interval=1, first_on=WEEK_2)])

    assert dates(db, user, "lecture") == [WEEK_1, WEEK_2, WEEK_3, WEEK_4]


def test_a_first_date_must_fall_on_a_day_it_runs(db, user, course):
    """Anchoring to a day it does not run would leave the first cycle short."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # Tuesday, for a meeting that runs Monday and Wednesday.
        meeting(["MO", "WE"], interval=2, first_on=datetime.date(2026, 9, 8))


def test_a_first_date_before_the_term_is_refused(db, user, course):
    with pytest.raises(ValueError, match="before the term starts"):
        schedule(db, user, course, [
            meeting(["MO"], interval=2, first_on=datetime.date(2026, 8, 31))])


def test_a_first_date_after_the_term_is_refused(db, user, course):
    with pytest.raises(ValueError, match="after the term ends"):
        schedule(db, user, course, [
            meeting(["MO"], interval=2, first_on=datetime.date(2026, 12, 28))])


# --- the point of putting it on the meeting -------------------------------

def test_one_course_can_mix_a_weekly_lecture_and_a_fortnightly_lab(db, user, course):
    """The ordinary case, and the reason interval is per meeting."""
    schedule(db, user, course, [
        meeting(["MO", "WE"], kind=EventKind.LECTURE, hour=10),
        meeting(["TU"], kind=EventKind.LAB, interval=2, first_on=datetime.date(2026, 9, 15), hour=14),
    ])

    lectures = dates(db, user, "lecture")
    labs = dates(db, user, "lab")

    assert len(lectures) == 8, "Mon and Wed of four weeks"
    # Tuesdays of weeks 2 and 4.
    assert labs == [datetime.date(2026, 9, 15), datetime.date(2026, 9, 29)]


def test_the_interval_survives_a_round_trip(db, user, course):
    """Re-opening the form must show what was saved, not a reset to weekly."""
    from app.Calendar.services.class_schedule_service import get_class_schedule

    schedule(db, user, course, [meeting(["MO"], interval=2, first_on=WEEK_2)])

    saved = get_class_schedule(db, user.id, course.id)
    assert len(saved) == 1
    assert saved[0].recurrence.interval == 2
    assert saved[0].starts_on == WEEK_2


def test_an_interval_beyond_the_ceiling_is_refused(db, user, course):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        meeting(["MO"], interval=9)
