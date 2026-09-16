"""Fixed term dates, and the anchor that gives them a calendar year.

`courses.year` is the school year -- 1 to 10 -- not a calendar year. So "Fall
starts September 1" has no year to attach to on its own, and one setting
supplies it: the calendar year first year began. Every term in the app derives
from that.

Anchored on year 1 rather than on the student's current year, deliberately.
`current_school_year` is advanced every September, and an anchor hanging off it
would silently re-date every course in the app the moment it moved.
"""
import datetime

import pytest

from app.Calendar.schemas.event import ClassMeeting, ClassScheduleCreate
from app.Calendar.services.class_schedule_service import set_class_schedule, term_window
from app._database.models import CourseModel
from app.Grades.utils.terms import (
    TERM_DATES,
    calendar_year_of,
    suggest_first_year,
    term_dates,
)
from conftest import make_course

ANCHOR = 2023  # first year began in 2023, so year 3's Fall is 2025


# ----------------------------------------------------------- the anchor --

@pytest.mark.parametrize("school_year,expected", [(1, 2023), (2, 2024), (3, 2025), (10, 2032)])
def test_a_school_year_resolves_by_counting_from_the_first(school_year, expected):
    assert calendar_year_of(school_year, ANCHOR) == expected


def test_without_the_anchor_a_year_has_no_calendar_year(db):
    assert calendar_year_of(3, None) is None
    assert term_dates("Fall", 3, None) is None


def test_an_unrecognised_term_has_no_dates_rather_than_a_default(db):
    """A guess here would date a course to whatever the first entry happened to
    be -- the same silent fallback SEMESTER_ORDER's .get(..., 0) makes."""
    assert term_dates("Reading Week", 3, ANCHOR) is None


# ------------------------------------------------------------ the dates --

def test_fall_runs_september_to_december_of_the_school_years_own_year():
    assert term_dates("Fall", 3, ANCHOR) == (
        datetime.date(2025, 9, 1), datetime.date(2025, 12, 31)
    )


@pytest.mark.parametrize("semester", ["Winter", "Spring", "Summer"])
def test_every_term_after_new_year_lands_in_the_following_calendar_year(semester):
    """The offset that makes a school year read "2025-2026". Zero here would put
    Winter eight months *before* the Fall it follows."""
    fall_start, _ = term_dates("Fall", 3, ANCHOR)
    start, end = term_dates(semester, 3, ANCHOR)

    assert start.year == fall_start.year + 1
    assert end.year == start.year
    assert start > fall_start


def test_the_four_terms_do_not_overlap_and_cover_the_year():
    """Read in order, each term starts the day after the last one ended."""
    spans = [term_dates(name, 3, ANCHOR) for name in TERM_DATES]
    spans.sort()

    for (_, earlier_end), (later_start, _) in zip(spans, spans[1:]):
        assert later_start == earlier_end + datetime.timedelta(days=1)


def test_advancing_the_current_year_does_not_move_any_term(db, user):
    """What anchoring on year 1 buys. With the anchor hung off the student's
    current year, every course in the app would re-date itself each September."""
    before = term_dates("Fall", 3, ANCHOR)

    user.current_school_year = 4
    db.commit()

    assert term_dates("Fall", 3, ANCHOR) == before


# ------------------------------------------- the class timetable carve-out --

def test_the_timetable_still_runs_over_the_courses_own_dates(db, user):
    """The carve-out, and it is not cosmetic.

    A timetable generates one recurring event per meeting across the span it is
    given. Handed the term's Sep 1 - Dec 31 instead of the course's real
    Sep 9 - Dec 7, it would invent about three lectures before term started and
    three after it ended -- on the calendar, in the week's hours, and in every
    insight that counts them.
    """
    course = make_course(
        db, user.id, "CPSC 221",
        start_date=datetime.date(2025, 9, 9), end_date=datetime.date(2025, 12, 7),
    )

    starts_on, ends_on = term_window(course, ClassScheduleCreate(meetings=[]))

    assert (starts_on, ends_on) == (datetime.date(2025, 9, 9), datetime.date(2025, 12, 7))


def test_a_generated_timetable_starts_no_earlier_than_the_first_class(db, user):
    """The same rule asserted through the thing that actually writes rows."""
    course = make_course(
        db, user.id, "CPSC 221",
        start_date=datetime.date(2025, 9, 9), end_date=datetime.date(2025, 12, 7),
    )

    events = set_class_schedule(db, user.id, course.id, ClassScheduleCreate(meetings=[
        ClassMeeting(kind="lecture", days=["TU"],
                     start_time=datetime.time(9, 0), end_time=datetime.time(10, 0)),
    ]))

    assert events
    for event in events:
        assert event.starts_on >= datetime.date(2025, 9, 9), "no lecture before term"
        assert event.starts_on <= datetime.date(2025, 12, 7)


# ------------------------------------------------- suggesting the anchor --

def test_the_anchor_is_suggested_from_a_dated_course(db, user):
    """Inverting term_dates: a Fall starting in 2026 for a year-3 student means
    first year began in 2024."""
    make_course(db, user.id, "CPSC 320", year=3, semester="Fall",
                start_date=datetime.date(2026, 9, 9), end_date=datetime.date(2026, 12, 7))

    assert suggest_first_year(db.query(CourseModel).all()) == 2024


def test_a_term_after_new_year_suggests_the_same_anchor(db, user):
    """Winter of year 3 runs in 2027 under the same anchor, and the offset has
    to be undone or the suggestion lands a year out."""
    make_course(db, user.id, "CPSC 310", year=3, semester="Winter",
                start_date=datetime.date(2027, 1, 8), end_date=datetime.date(2027, 4, 10))

    assert suggest_first_year(db.query(CourseModel).all()) == 2024


def test_the_suggestion_round_trips_through_term_dates(db, user):
    """The property that makes it worth offering: feed the suggestion back in
    and the course's own term contains the course's own start date."""
    start = datetime.date(2026, 9, 9)
    make_course(db, user.id, "CPSC 320", year=3, semester="Fall",
                start_date=start, end_date=datetime.date(2026, 12, 7))

    anchor = suggest_first_year(db.query(CourseModel).all())
    term_start, term_end = term_dates("Fall", 3, anchor)
    assert term_start <= start <= term_end


def test_one_mistyped_course_cannot_outvote_the_rest(db, user):
    for code in ("A 100", "B 100", "C 100"):
        make_course(db, user.id, code, year=3, semester="Fall",
                    start_date=datetime.date(2026, 9, 9), end_date=datetime.date(2026, 12, 7))
    make_course(db, user.id, "TYPO 100", year=3, semester="Fall",
                start_date=datetime.date(2019, 9, 9), end_date=datetime.date(2019, 12, 7))

    assert suggest_first_year(db.query(CourseModel).all()) == 2024


def test_nothing_dated_suggests_nothing(db, user):
    make_course(db, user.id, "NODATE 100", year=3, semester="Fall")

    assert suggest_first_year(db.query(CourseModel).all()) is None
