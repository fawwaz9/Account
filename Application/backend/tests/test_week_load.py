"""When you actually have time, and when the term lands on you.

Gap arithmetic is where a calendar goes quietly wrong: an off-by-one at a
boundary invents an hour that is not there, and a student schedules work into
it. Every edge here is a case that produced a wrong block while this was being
written, or would have.
"""
import datetime
import uuid

from app.Calendar.schemas.event import EventCreate, EventKind
from app.Calendar.services.event_service import create_event, list_occurrences
from app.Calendar.services.load_service import (
    busy_spans, crunch, free_blocks, week_load,
)
from app.Tasks.schemas.task import TaskCreate
from app.Tasks.services.task_service import create_task
from conftest import make_course

MON = datetime.date(2026, 9, 14)   # a Monday
TUE = datetime.date(2026, 9, 15)


def at(hour, minute=0):
    return datetime.time(hour, minute)


def klass(db, user, title, on, start, end, kind=EventKind.LECTURE):
    return create_event(db, user.id, EventCreate(
        title=title, kind=kind, starts_on=on, start_time=start, end_time=end,
    ))


def blocks_on(db, user, day):
    found = free_blocks(db, user.id, day, day)
    return [(b.starts_at, b.ends_at, b.minutes) for b in found]


# ------------------------------------------------------------ free blocks --

def test_an_empty_day_is_one_block_of_study_hours(db, user):
    """08:00-22:00 by default, not midnight to midnight."""
    assert blocks_on(db, user, MON) == [(at(8), at(22), 14 * 60)]


def test_a_class_splits_the_day_either_side(db, user):
    klass(db, user, "CPSC 210", MON, at(10), at(11))

    assert blocks_on(db, user, MON) == [
        (at(11), at(22), 11 * 60),   # longest first
        (at(8), at(10), 2 * 60),
    ]


def test_a_gap_under_the_floor_is_not_a_block(db, user):
    """Twenty minutes between lectures is walking time, not an hour of work."""
    klass(db, user, "A", MON, at(10), at(11))
    klass(db, user, "B", MON, at(11, 20), at(12))

    spans = blocks_on(db, user, MON)
    assert (at(11), at(11, 20), 20) not in spans
    assert spans == [(at(12), at(22), 10 * 60), (at(8), at(10), 2 * 60)]


def test_back_to_back_classes_leave_nothing_between_them(db, user):
    klass(db, user, "A", MON, at(10), at(11))
    klass(db, user, "B", MON, at(11), at(12))

    assert blocks_on(db, user, MON) == [(at(12), at(22), 10 * 60), (at(8), at(10), 2 * 60)]


def test_overlapping_classes_do_not_invent_a_gap(db, user):
    """The week view exists partly to show overlaps, so the maths must merge them.

    Treated as separate spans, the end of the first and the start of the second
    would look like a gap that never existed.
    """
    klass(db, user, "A", MON, at(10), at(12))
    klass(db, user, "B", MON, at(11), at(13))

    assert blocks_on(db, user, MON) == [(at(13), at(22), 9 * 60), (at(8), at(10), 2 * 60)]
    # And the merge itself, directly: two spans in, one span out.
    assert busy_spans(list_occurrences(db, user.id, MON, MON), MON) == [(at(10), at(13))]


def test_a_class_before_the_window_opens_no_block_at_midnight(db, user):
    """A 07:00 lab must not open an 00:00 block, nor a 07:00-08:00 one."""
    klass(db, user, "Early lab", MON, at(6), at(7))

    assert blocks_on(db, user, MON) == [(at(8), at(22), 14 * 60)]


def test_a_class_after_the_window_does_not_extend_the_evening(db, user):
    klass(db, user, "Night", MON, at(23), at(23, 30))

    assert blocks_on(db, user, MON) == [(at(8), at(22), 14 * 60)]


def test_a_class_straddling_the_close_clips_the_block(db, user):
    klass(db, user, "Evening", MON, at(21), at(23))

    assert blocks_on(db, user, MON) == [(at(8), at(21), 13 * 60)]


def test_an_all_day_item_blocks_no_hour(db, user):
    """It occupies no position on a clock, so it splits nothing."""
    create_event(db, user.id, EventCreate(title="Reading break", starts_on=MON))

    assert blocks_on(db, user, MON) == [(at(8), at(22), 14 * 60)]


def test_blocks_come_back_longest_first(db, user):
    klass(db, user, "A", MON, at(9), at(10))
    klass(db, user, "B", MON, at(12), at(13))

    found = free_blocks(db, user.id, MON, MON)
    assert [b.minutes for b in found] == sorted([b.minutes for b in found], reverse=True)


def test_the_study_window_is_configurable(db, user):
    user.preferences = {"study_day_start": "06:00:00", "study_day_end": "12:00:00"}
    db.commit()

    assert blocks_on(db, user, MON) == [(at(6), at(12), 6 * 60)]


# -------------------------------------------------------------- week load --

def test_booked_and_estimated_are_reported_apart(db, user):
    """One number would hide which half is a guess."""
    klass(db, user, "CPSC 210", MON, at(10), at(11, 30))
    create_task(db, user.id, TaskCreate(title="Essay", due_date=MON, estimated_minutes=120))

    load = week_load(db, user.id, MON, TUE)
    assert load.booked_minutes == 90
    assert load.estimated_minutes == 120


def test_an_unestimated_task_is_counted_but_adds_no_hours(db, user):
    """Most tasks carry no estimate, so the number has to be readable honestly."""
    create_task(db, user.id, TaskCreate(title="Read chapter", due_date=MON))
    create_task(db, user.id, TaskCreate(title="Essay", due_date=MON, estimated_minutes=60))

    load = week_load(db, user.id, MON, TUE)
    assert load.task_count == 2
    assert load.unestimated_tasks == 1
    assert load.estimated_minutes == 60


def test_an_all_day_event_books_no_time(db, user):
    create_event(db, user.id, EventCreate(title="Reading break", starts_on=MON))

    load = week_load(db, user.id, MON, TUE)
    assert load.booked_minutes == 0
    assert load.event_count == 1


# ------------------------------------------------------------ crunch radar --

def test_a_final_outweighs_a_midterm_outweighs_a_deadline(db, user):
    """One exam really can outweigh three assignments, so kinds are not counted.

    Each kind gets its own account rather than one account being cleared between
    measurements -- a delete wide enough to reset the fixture is a delete wide
    enough to be wrong.
    """
    from conftest import make_user

    for name, kind, expected in (
        ("final", EventKind.FINAL, 5),
        ("midterm", EventKind.MIDTERM, 3),
        ("deadline", EventKind.DEADLINE, 1),
    ):
        owner = make_user(db, f"{name}@weights.local")
        klass(db, owner, name, MON, at(9), at(12), kind=kind)
        assert crunch(db, owner.id, MON, MON).weeks[0].weight == expected


def test_exams_and_deadlines_are_tallied_separately(db, user):
    """The raw counts travel with the weight, so the strip can be read plainly."""
    klass(db, user, "Midterm", TUE, at(9), at(11), kind=EventKind.MIDTERM)
    klass(db, user, "Essay due", TUE, at(9), at(10), kind=EventKind.DEADLINE)

    week = crunch(db, user.id, MON, TUE).weeks[0]
    assert (week.exams, week.deadlines, week.weight) == (1, 1, 4)


def test_a_lecture_carries_no_weight(db, user):
    """Classes are the background the term runs against, not what stacks up."""
    klass(db, user, "Lecture", MON, at(9), at(10))

    assert crunch(db, user.id, MON, MON).weeks[0].weight == 0


def test_a_quiet_week_still_appears_in_the_strip(db, user):
    """A gap in the strip would read as missing data, not as a quiet fortnight."""
    later = MON + datetime.timedelta(weeks=3)
    klass(db, user, "Final", later, at(9), at(12), kind=EventKind.FINAL)

    strip = crunch(db, user.id, MON, later)
    assert len(strip.weeks) == 4
    assert [w.weight for w in strip.weeks] == [0, 0, 0, 5]
    assert strip.peak == 5


def test_a_dated_task_lands_like_a_deadline(db, user):
    create_task(db, user.id, TaskCreate(title="Essay", due_date=MON))

    week = crunch(db, user.id, MON, MON).weeks[0]
    assert week.tasks == 1
    assert week.weight == 1


def test_the_current_week_is_marked(db, user):
    strip = crunch(db, user.id, MON, MON + datetime.timedelta(weeks=2), today=MON)
    assert [w.is_current for w in strip.weeks] == [True, False, False]
