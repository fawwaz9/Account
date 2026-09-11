"""The calendar and task foundation, end to end through the services.

Three things are worth pinning down here, because each is a place where two
features have to agree:

* occurrences are materialised on read and never stored
* a course's timetable is replaced, not appended to
* a dated grade owns exactly one task, which closes when the score lands
"""
from datetime import date, time

import pytest

from app._database.models import EventModel, TaskModel
from app.Calendar.schemas.event import (
    ClassMeeting,
    Event,
    ClassScheduleCreate,
    EventCreate,
    EventKind,
    EventUpdate,
    Recurrence,
)
from app.Calendar.services.class_schedule_service import set_class_schedule
from app.Calendar.services.event_service import (
    create_event,
    delete_event,
    list_occurrences,
    skip_occurrence,
    update_event,
)
from app.Grades.schemas.grade import GradeCreate, GradeUpdate
from app.Grades.services.grade_service import (
    add_grade,
    delete_grade,
    record_grade,
    update_grade,
)
from app.Grades.utils.enums import GradeSchedule
from app.Tasks.schemas.task import TaskCreate, TaskUpdate
from app.Tasks.services.task_service import (
    create_task,
    delete_task,
    list_tasks,
    update_task,
)
from conftest import make_course, make_user

TERM_START = date(2026, 9, 8)   # a Tuesday
TERM_END = date(2026, 12, 4)


# ------------------------------------------------------------ events, dates --

def test_a_repeat_is_one_row_however_many_times_it_happens(db, user):
    """The point of the engine: storage does not grow with the term."""
    create_event(db, user.id, EventCreate(
        title="Gym", starts_on=TERM_START, start_time=time(7, 0), end_time=time(8, 0),
        recurrence=Recurrence(freq="weekly", until=TERM_END),
    ))

    assert db.query(EventModel).count() == 1

    weeks = list_occurrences(db, user.id, TERM_START, TERM_END)
    assert len(weeks) == 13
    assert db.query(EventModel).count() == 1


def test_occurrences_carry_the_course_code(db, user):
    course = make_course(db, user.id, "CPSC 221")
    create_event(db, user.id, EventCreate(
        title="CPSC 221 Midterm", kind=EventKind.MIDTERM, course_id=course.id,
        starts_on=date(2026, 10, 15), start_time=time(18, 0), end_time=time(20, 0),
    ))

    [occurrence] = list_occurrences(db, user.id, date(2026, 10, 1), date(2026, 10, 31))
    assert occurrence.course_code == "CPSC 221"
    assert occurrence.kind == EventKind.MIDTERM
    assert occurrence.repeats is False


def test_occurrences_come_back_in_order_with_all_day_items_first(db, user):
    for title, start in (("Afternoon", time(14, 0)), ("Morning", time(9, 0)), ("All day", None)):
        create_event(db, user.id, EventCreate(title=title, starts_on=TERM_START, start_time=start))

    titles = [item.title for item in list_occurrences(db, user.id, TERM_START, TERM_START)]
    assert titles == ["All day", "Morning", "Afternoon"]


def test_an_event_from_another_user_is_not_in_your_agenda(db, user):
    stranger = make_user(db, "stranger@example.com")
    create_event(db, stranger.id, EventCreate(title="Not yours", starts_on=TERM_START))

    assert list_occurrences(db, user.id, TERM_START, TERM_END) == []


def test_a_window_longer_than_the_cap_is_refused(db, user):
    with pytest.raises(ValueError, match="longer than"):
        list_occurrences(db, user.id, date(2026, 1, 1), date(2028, 1, 1))


def test_a_backwards_window_is_refused(db, user):
    with pytest.raises(ValueError, match="ends before"):
        list_occurrences(db, user.id, TERM_END, TERM_START)


def test_an_event_cannot_be_attached_to_someone_elses_course(db, user):
    """The cross-tenant attach that audit #7 found on spend categories."""
    stranger = make_user(db, "stranger@example.com")
    their_course = make_course(db, stranger.id, "MATH 100")

    with pytest.raises(ValueError, match="Course not found"):
        create_event(db, user.id, EventCreate(
            title="Sneaky", starts_on=TERM_START, course_id=their_course.id,
        ))


# --------------------------------------------------------- skipping one day --

def test_skipping_one_date_leaves_the_rest_of_the_series(db, user):
    event = create_event(db, user.id, EventCreate(
        title="Lecture", starts_on=TERM_START,
        recurrence=Recurrence(freq="weekly", until=TERM_END),
    ))

    skip_occurrence(db, user.id, event.id, date(2026, 9, 15))
    dates = [item.on_date for item in list_occurrences(db, user.id, TERM_START, TERM_END)]

    assert date(2026, 9, 15) not in dates
    assert date(2026, 9, 22) in dates
    assert len(dates) == 12


def test_an_event_with_a_cancelled_date_can_still_be_edited(db, user):
    """A JSON column will not take date objects.

    attach_recurrence used to parse skipped_dates onto the instance for display.
    That marks a real JSON column dirty with values json.dumps cannot serialize,
    so the next commit on the session died with "Object of type date is not JSON
    serializable" -- meaning any edit to an event that had one cancelled date
    failed. Empty lists serialize fine, which is why it stayed hidden.
    """
    event = create_event(db, user.id, EventCreate(
        title="Lecture", starts_on=TERM_START,
        recurrence=Recurrence(freq="weekly", until=TERM_END),
    ))
    skip_occurrence(db, user.id, event.id, date(2026, 9, 15))

    renamed = update_event(db, user.id, event.id, EventUpdate(title="Lecture (moved)"))

    assert renamed.title == "Lecture (moved)"
    # The column keeps ISO strings, and the schema is what turns them into dates
    # on the way out -- which is precisely why the service must not write parsed
    # dates back onto it.
    assert renamed.skipped_dates == ["2026-09-15"]
    assert Event.model_validate(renamed).skipped_dates == [date(2026, 9, 15)]
    # And the cancellation survived the edit.
    dates = [item.on_date for item in list_occurrences(db, user.id, TERM_START, TERM_END)]
    assert date(2026, 9, 15) not in dates


def test_a_one_off_cannot_be_skipped(db, user):
    """There is nothing left of it afterwards, so deleting is the honest verb."""
    event = create_event(db, user.id, EventCreate(title="Dentist", starts_on=TERM_START))

    with pytest.raises(ValueError, match="happens once"):
        skip_occurrence(db, user.id, event.id, TERM_START)


def test_deleting_an_event_does_not_raise_on_the_flush(db, user):
    """A StaleDataError guard: reading an event marks it dirty before the delete."""
    event = create_event(db, user.id, EventCreate(title="Dentist", starts_on=TERM_START))

    deleted = delete_event(db, user.id, event.id)

    assert deleted.title == "Dentist"
    assert db.query(EventModel).count() == 0


def test_an_edit_cannot_leave_an_event_ending_before_it_starts(db, user):
    event = create_event(db, user.id, EventCreate(
        title="Lab", starts_on=TERM_START, start_time=time(9, 0), end_time=time(11, 0),
    ))

    with pytest.raises(ValueError, match="cannot end before"):
        update_event(db, user.id, event.id, EventUpdate(start_time=time(12, 0)))


def test_clearing_a_recurrence_leaves_a_one_off(db, user):
    event = create_event(db, user.id, EventCreate(
        title="Lecture", starts_on=TERM_START,
        recurrence=Recurrence(freq="weekly", until=TERM_END),
    ))

    updated = update_event(db, user.id, event.id, EventUpdate(recurrence=None))

    assert updated.recurrence is None
    assert len(list_occurrences(db, user.id, TERM_START, TERM_END)) == 1


# ---------------------------------------------------------- class timetable --

def test_a_course_generates_its_class_blocks(db, user):
    course = make_course(db, user.id, "CPSC 221", start_date=TERM_START, end_date=TERM_END)

    set_class_schedule(db, user.id, course.id, ClassScheduleCreate(meetings=[
        ClassMeeting(kind=EventKind.LECTURE, days=["TU", "TH"],
                     start_time=time(9, 30), end_time=time(11, 0), location="SWNG 222"),
        ClassMeeting(kind=EventKind.LAB, days=["FR"],
                     start_time=time(13, 0), end_time=time(15, 0)),
    ]))

    # Two rows, not two-and-a-half terms' worth of individual meetings.
    assert db.query(EventModel).count() == 2

    week = list_occurrences(db, user.id, TERM_START, date(2026, 9, 13))
    assert [(item.title, item.on_date.isoformat()) for item in week] == [
        ("CPSC 221 Lecture", "2026-09-08"),
        ("CPSC 221 Lecture", "2026-09-10"),
        ("CPSC 221 Lab", "2026-09-11"),
    ]


def test_the_timetable_stops_when_the_course_does(db, user):
    course = make_course(db, user.id, "CPSC 221", start_date=TERM_START, end_date=TERM_END)
    set_class_schedule(db, user.id, course.id, ClassScheduleCreate(meetings=[
        ClassMeeting(days=["TU"], start_time=time(9, 0), end_time=time(10, 0)),
    ]))

    assert list_occurrences(db, user.id, date(2027, 1, 1), date(2027, 1, 31)) == []


def test_resubmitting_a_timetable_replaces_it(db, user):
    """Fixing a room must not leave the old room on the calendar beside it."""
    course = make_course(db, user.id, "CPSC 221", start_date=TERM_START, end_date=TERM_END)
    schedule = ClassScheduleCreate(meetings=[
        ClassMeeting(days=["TU"], start_time=time(9, 0), end_time=time(10, 0), location="Old"),
    ])
    set_class_schedule(db, user.id, course.id, schedule)

    schedule.meetings[0].location = "New"
    set_class_schedule(db, user.id, course.id, schedule)

    events = db.query(EventModel).all()
    assert len(events) == 1
    assert events[0].location == "New"


def test_replacing_a_timetable_leaves_the_courses_midterm_alone(db, user):
    course = make_course(db, user.id, "CPSC 221", start_date=TERM_START, end_date=TERM_END)
    create_event(db, user.id, EventCreate(
        title="Midterm", kind=EventKind.MIDTERM, course_id=course.id, starts_on=date(2026, 10, 15),
    ))

    set_class_schedule(db, user.id, course.id, ClassScheduleCreate(meetings=[
        ClassMeeting(days=["TU"], start_time=time(9, 0), end_time=time(10, 0)),
    ]))

    kinds = {event.kind for event in db.query(EventModel).all()}
    assert kinds == {"lecture", "midterm"}


def test_a_course_with_no_dates_is_told_to_supply_them(db, user):
    course = make_course(db, user.id, "CPSC 221")

    with pytest.raises(ValueError, match="term dates"):
        set_class_schedule(db, user.id, course.id, ClassScheduleCreate(meetings=[
            ClassMeeting(days=["TU"], start_time=time(9, 0), end_time=time(10, 0)),
        ]))


# -------------------------------------------------------------------- tasks --

def test_tasks_come_back_soonest_first_with_undated_ones_last(db, user):
    for title, due in (("Later", date(2026, 9, 20)), ("Someday", None), ("Sooner", date(2026, 9, 9))):
        create_task(db, user.id, TaskCreate(title=title, due_date=due))

    assert [task.title for task in list_tasks(db, user.id)] == ["Sooner", "Later", "Someday"]


def test_a_window_asks_for_deadlines_not_for_everything(db, user):
    create_task(db, user.id, TaskCreate(title="Dated", due_date=date(2026, 9, 9)))
    create_task(db, user.id, TaskCreate(title="Undated"))

    week = list_tasks(db, user.id, start=date(2026, 9, 7), end=date(2026, 9, 13))
    assert [task.title for task in week] == ["Dated"]


def test_checking_a_task_off_archives_it_and_stamps_the_time(db, user):
    task = create_task(db, user.id, TaskCreate(title="Readings"))

    done = update_task(db, user.id, task.id, TaskUpdate(done=True))

    assert done.done is True
    assert done.archived is True
    assert done.completed_at is not None
    # And it leaves the list of what is outstanding.
    assert list_tasks(db, user.id) == []
    assert len(list_tasks(db, user.id, include_done=True, include_archived=True)) == 1


def test_unchecking_a_task_brings_it_back(db, user):
    task = create_task(db, user.id, TaskCreate(title="Readings"))
    update_task(db, user.id, task.id, TaskUpdate(done=True))

    reopened = update_task(db, user.id, task.id, TaskUpdate(done=False))

    assert (reopened.done, reopened.archived, reopened.completed_at) == (False, False, None)
    assert [task.title for task in list_tasks(db, user.id)] == ["Readings"]


def test_a_course_task_is_labelled_with_its_course_code(db, user):
    course = make_course(db, user.id, "CPSC 221")
    create_task(db, user.id, TaskCreate(title="Lab 3", course_id=course.id))

    [task] = list_tasks(db, user.id)
    assert task.course_code == "CPSC 221"


def test_a_task_cannot_be_attached_to_someone_elses_course(db, user):
    stranger = make_user(db, "stranger@example.com")
    their_course = make_course(db, stranger.id, "MATH 100")

    with pytest.raises(ValueError, match="Course not found"):
        create_task(db, user.id, TaskCreate(title="Sneaky", course_id=their_course.id))


def test_deleting_a_task_does_not_raise_on_the_flush(db, user):
    task = create_task(db, user.id, TaskCreate(title="Readings"))

    deleted = delete_task(db, user.id, task.id)

    assert deleted.title == "Readings"
    assert db.query(TaskModel).count() == 0


# ------------------------------------------------------ grades raise tasks ---

def dated_grade(db, user, due=date(2026, 9, 25), score=None):
    course = make_course(db, user.id, "CPSC 221")
    grade = add_grade(db, user.id, course.id, GradeCreate(
        name="Assignment 1", category="Assignment", max_score=100, score=score, due_date=due,
    ))
    return course, grade


def test_a_dated_grade_raises_a_task(db, user):
    course, _ = dated_grade(db, user)

    [task] = list_tasks(db, user.id)
    assert task.title == "Assignment 1"
    assert task.due_date == date(2026, 9, 25)
    assert task.course_id == course.id
    assert task.course_code == "CPSC 221"


def test_an_undated_grade_raises_nothing(db, user):
    dated_grade(db, user, due=None)

    assert list_tasks(db, user.id) == []


def test_the_task_closes_when_the_score_lands(db, user):
    course, grade = dated_grade(db, user)

    record_grade(db, user.id, course.id, grade.id, 88.0)

    assert list_tasks(db, user.id) == []
    [task] = list_tasks(db, user.id, include_done=True, include_archived=True)
    assert task.done is True
    assert task.completed_at is not None


def test_a_grade_entered_already_marked_raises_a_closed_task(db, user):
    dated_grade(db, user, score=88.0)

    assert list_tasks(db, user.id) == []
    assert len(list_tasks(db, user.id, include_done=True, include_archived=True)) == 1


def test_clearing_the_score_reopens_the_task(db, user):
    course, grade = dated_grade(db, user, score=88.0)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(score=None))

    assert [task.title for task in list_tasks(db, user.id)] == ["Assignment 1"]


def test_renaming_a_grade_renames_its_task(db, user):
    course, grade = dated_grade(db, user)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(name="Assignment 1 (revised)"))

    [task] = list_tasks(db, user.id)
    assert task.title == "Assignment 1 (revised)"


def test_moving_a_deadline_moves_the_task(db, user):
    course, grade = dated_grade(db, user)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(due_date=date(2026, 10, 2)))

    [task] = list_tasks(db, user.id)
    assert task.due_date == date(2026, 10, 2)


def test_clearing_the_deadline_removes_the_task(db, user):
    course, grade = dated_grade(db, user)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(due_date=None))

    assert db.query(TaskModel).count() == 0


def test_deleting_the_grade_takes_its_task_with_it(db, user):
    course, grade = dated_grade(db, user)

    delete_grade(db, user.id, course.id, grade.id)

    assert db.query(TaskModel).count() == 0


def test_a_grade_never_raises_a_second_task(db, user):
    """Re-saving is the obvious way to end up with duplicates."""
    course, grade = dated_grade(db, user)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(name="Renamed"))
    update_grade(db, user.id, course.id, grade.id, GradeUpdate(due_date=date(2026, 10, 2)))
    record_grade(db, user.id, course.id, grade.id, 91.0)

    assert db.query(TaskModel).count() == 1


def test_re_saving_a_marked_grade_keeps_when_it_was_finished(db, user):
    course, grade = dated_grade(db, user, score=88.0)
    [task] = list_tasks(db, user.id, include_done=True, include_archived=True)
    finished_at = task.completed_at

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(name="Renamed"))

    [task] = list_tasks(db, user.id, include_done=True, include_archived=True)
    assert task.completed_at == finished_at


def test_an_estimate_you_set_survives_the_grade_being_edited(db, user):
    course, grade = dated_grade(db, user)
    [task] = list_tasks(db, user.id)
    update_task(db, user.id, task.id, TaskUpdate(estimated_minutes=180, notes="Start early"))

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(name="Renamed"))

    [task] = list_tasks(db, user.id)
    assert (task.estimated_minutes, task.notes) == (180, "Start early")


# ------------------------------------- a date means one of two things ---

def scheduled_grade(db, user, schedule, category="Assignment", due=date(2026, 9, 25), score=None):
    course = make_course(db, user.id, "CPSC 221")
    grade = add_grade(db, user.id, course.id, GradeCreate(
        name="Assignment 1", category=category, max_score=100,
        score=score, due_date=due, schedule_as=schedule,
    ))
    return course, grade


def test_a_date_raises_a_task_by_default(db, user):
    """What every dated grade did before the choice existed."""
    scheduled_grade(db, user, GradeSchedule.TASK)

    assert len(list_tasks(db, user.id)) == 1
    assert db.query(EventModel).count() == 0


def test_scheduling_as_an_event_draws_a_block_and_no_task(db, user):
    """A midterm is something you sit, not a chore that never quite closes."""
    scheduled_grade(db, user, GradeSchedule.EVENT)

    assert list_tasks(db, user.id) == []
    [event] = db.query(EventModel).all()
    assert event.title == "Assignment 1"
    assert event.starts_on == date(2026, 9, 25)


def test_a_grade_event_shows_on_the_calendar_with_its_course(db, user):
    course, _ = scheduled_grade(db, user, GradeSchedule.EVENT)

    [occurrence] = list_occurrences(db, user.id, date(2026, 9, 1), date(2026, 9, 30))

    assert occurrence.title == "Assignment 1"
    assert occurrence.course_code == "CPSC 221"
    assert occurrence.course_id == course.id


def test_a_midterm_scheduled_as_an_event_gets_a_midterm_card(db, user):
    scheduled_grade(db, user, GradeSchedule.EVENT, category="Midterm")

    [event] = db.query(EventModel).all()
    assert event.kind == EventKind.MIDTERM.value


def test_a_final_scheduled_as_an_event_gets_a_final_card(db, user):
    scheduled_grade(db, user, GradeSchedule.EVENT, category="Final")

    [event] = db.query(EventModel).all()
    assert event.kind == EventKind.FINAL.value


def test_anything_else_scheduled_as_an_event_reads_as_a_deadline(db, user):
    scheduled_grade(db, user, GradeSchedule.EVENT, category="Lab")

    [event] = db.query(EventModel).all()
    assert event.kind == EventKind.DEADLINE.value


def test_a_score_does_not_close_a_grade_event(db, user):
    """A sat exam is history, not an unfinished chore -- that is the point."""
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT, category="Midterm")

    record_grade(db, user.id, course.id, grade.id, 78.0)

    assert db.query(EventModel).count() == 1
    assert list_tasks(db, user.id, include_done=True, include_archived=True) == []


def test_switching_from_task_to_event_leaves_no_task_behind(db, user):
    """Or the deadline would show twice: once to tick off, once to attend."""
    course, grade = scheduled_grade(db, user, GradeSchedule.TASK)

    update_grade(db, user.id, course.id, grade.id,
                 GradeUpdate(schedule_as=GradeSchedule.EVENT))

    assert list_tasks(db, user.id) == []
    assert db.query(TaskModel).count() == 0
    assert db.query(EventModel).count() == 1


def test_switching_from_event_to_task_removes_the_block(db, user):
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT)

    update_grade(db, user.id, course.id, grade.id,
                 GradeUpdate(schedule_as=GradeSchedule.TASK))

    assert db.query(EventModel).count() == 0
    assert [task.title for task in list_tasks(db, user.id)] == ["Assignment 1"]


def test_clearing_the_date_removes_the_event_too(db, user):
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(due_date=None))

    assert db.query(EventModel).count() == 0


def test_moving_the_date_moves_the_event(db, user):
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT)

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(due_date=date(2026, 10, 2)))

    [event] = db.query(EventModel).all()
    assert event.starts_on == date(2026, 10, 2)


def test_changing_the_category_rethemes_the_event(db, user):
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT, category="Assignment")

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(category="Final"))

    [event] = db.query(EventModel).all()
    assert event.kind == EventKind.FINAL.value


def test_deleting_the_grade_takes_its_event_with_it(db, user):
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT)

    delete_grade(db, user.id, course.id, grade.id)

    assert db.query(EventModel).count() == 0


def test_a_time_you_set_on_the_block_survives_the_grade_being_edited(db, user):
    """The gradebook does not know when the exam starts; once you say, it is yours."""
    course, grade = scheduled_grade(db, user, GradeSchedule.EVENT, category="Midterm")
    [event] = db.query(EventModel).all()
    update_event(db, user.id, event.id, EventUpdate(
        start_time=time(18, 0), end_time=time(20, 0), location="SRC A",
    ))

    update_grade(db, user.id, course.id, grade.id, GradeUpdate(name="Midterm 1"))

    [event] = db.query(EventModel).all()
    assert event.title == "Midterm 1"
    assert (event.start_time, event.end_time, event.location) == (time(18, 0), time(20, 0), "SRC A")


def test_an_undated_grade_schedules_nothing_whichever_is_chosen(db, user):
    scheduled_grade(db, user, GradeSchedule.EVENT, due=None)

    assert db.query(EventModel).count() == 0
    assert db.query(TaskModel).count() == 0


def test_a_grade_never_produces_both(db, user):
    """The invariant the switching rules exist to keep."""
    course, grade = scheduled_grade(db, user, GradeSchedule.TASK)

    for schedule in (GradeSchedule.EVENT, GradeSchedule.TASK, GradeSchedule.EVENT):
        update_grade(db, user.id, course.id, grade.id, GradeUpdate(schedule_as=schedule))
        assert db.query(TaskModel).count() + db.query(EventModel).count() == 1
