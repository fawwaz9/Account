"""Keeping a dated grade's task or calendar block in step with the grade.

A grade with a date is two records at once: the gradebook entry waiting for a
score, and however that date surfaces elsewhere. Entering it twice is how the
two end up disagreeing, so the gradebook entry is the record and the other
follows it.

Which one it produces is the student's choice, because a date means two
different things:

* **task** -- work to do. Raises a task, which checks itself off when the score
  lands and reopens if the score is cleared.
* **event** -- something to attend. Draws a block on the calendar, themed as a
  midterm or a final where the category says so, with nothing to tick off. A
  sat exam is history, not an unfinished chore, so a score changes nothing here.

A date may also carry a time of day. It reaches a task as its due time and a
calendar block as its start; with no time the task is due by the end of the day
and the block is all-day, which is what every dated grade did before the field
existed. A calendar-bound grade may carry a length as well, which becomes the
block's end -- a length rather than an end time, so the two cannot disagree.

Switching between the two removes whatever the other had made, so a grade never
has both and the calendar never shows the same deadline twice.

Every function here mutates and flushes but never commits: they are called from
inside the grade service's own transaction, so a failed grade write must not
leave a task or an event behind.
"""

import uuid
from datetime import time

from sqlalchemy.orm import Session

from app._database.models import CourseModel, EventModel, GradeModel, TaskModel, utc_now
from app.Grades.utils.enums import (
    DEFAULT_SCHEDULE_EVENT_KIND,
    SCHEDULE_EVENT_KINDS,
    GradeSchedule,
    priority_for_category,
)
from app.Tasks.services.task_service import set_done


def task_for_grade(db: Session, grade_id: uuid.UUID) -> TaskModel | None:
    return db.query(TaskModel).filter(TaskModel.grade_id == grade_id).first()


def event_for_grade(db: Session, grade_id: uuid.UUID) -> EventModel | None:
    return db.query(EventModel).filter(EventModel.grade_id == grade_id).first()


def event_kind_for(grade: GradeModel) -> str:
    """A midterm gets a midterm card, a final a final card, the rest a deadline."""
    return SCHEDULE_EVENT_KINDS.get(grade.category, DEFAULT_SCHEDULE_EVENT_KIND)


def sync_schedule_for_grade(db: Session, course: CourseModel, grade: GradeModel):
    """Create, update, close or remove whatever this grade's date produces."""
    wants = (grade.schedule_as or GradeSchedule.TASK.value) if grade.due_date else None

    # Anything the grade no longer calls for goes, which covers both clearing the
    # date and switching from one kind of scheduling to the other.
    if wants != GradeSchedule.TASK.value:
        discard(db, task_for_grade(db, grade.id))
    if wants != GradeSchedule.EVENT.value:
        discard(db, event_for_grade(db, grade.id))

    if wants == GradeSchedule.TASK.value:
        return sync_task(db, course, grade)
    if wants == GradeSchedule.EVENT.value:
        return sync_event(db, course, grade)
    return None


def discard(db: Session, row) -> None:
    if row is not None:
        db.delete(row)
        db.flush()


def sync_task(db: Session, course: CourseModel, grade: GradeModel) -> TaskModel:
    task = task_for_grade(db, grade.id)
    if task is None:
        task = TaskModel(
            id=uuid.uuid4(),
            user_id=course.user_id,
            course_id=course.id,
            grade_id=grade.id,
            created_at=utc_now(),
            tags=[],
            # Seeded from the category, and only here. A final starts at 5 and a
            # lab at 3 because that is usually right, but re-saving the grade
            # must not undo a student who decided otherwise -- this function runs
            # on every grade write, so overwriting would silently revert the edit
            # every time a score was entered.
            priority=priority_for_category(grade.category),
        )
        db.add(task)

    task.title = grade.name
    task.due_date = grade.due_date
    # The time follows the date because they are one fact, not two. A task's
    # due time *is* the grade's due time -- there is nothing else living in
    # that field -- so leaving a stale 14:00 behind after the grade dropped it
    # would be the two records disagreeing, which is what this module exists to
    # prevent.
    task.due_time = grade.due_time
    task.course_id = course.id
    # Everything else the student set on the task -- an estimate, notes, tags,
    # the priority -- is theirs and is left alone.

    # A marked grade is finished work. Only move the flag when it disagrees, so
    # re-saving an already-marked grade does not keep resetting `completed_at`
    # to now and lose when it was actually done.
    scored = grade.score is not None
    if task.done != scored:
        set_done(task, scored)

    db.flush()
    return task


def forget_block_times(db: Session, grade: GradeModel) -> None:
    """Put this grade's block back to all-day.

    Called only when the student *removes* a time the grade had, which is the
    one case `sync_event` cannot recognise on its own -- it sees the grade's
    final state, where "never had a time" and "just lost one" are the same
    thing, and those two call for opposite treatment. Never having one leaves a
    time typed on the calendar alone; taking one away means it should go.
    """
    event = event_for_grade(db, grade.id)
    if event is None:
        return

    event.start_time = None
    event.end_time = None
    db.flush()


def move_start(event: EventModel, start: time, minutes: int | None = None) -> None:
    """Move a block to a new start time, and say how long it runs.

    With `minutes`, the end is derived: the grade carries a length, and a length
    plus a start cannot contradict each other the way two stored times can.

    Without one, the block keeps whatever length it already had. Setting the
    start on its own is the trap that makes this a function rather than an
    assignment: an exam the student marked 09:00-11:00 on the calendar, re-timed
    to 14:00 on the grade, would end three hours before it began. The API
    refuses that pair outright, so the row would be one nothing could edit
    afterwards. Keeping the length is also what the student meant -- they said
    the exam runs two hours, not that it ends at 11.

    An end that would run past midnight is dropped rather than wrapped: an event
    has one date, so 23:00 + 2h has nowhere to go, and an open-ended block is
    honest where a block ending at 01:00 on its own start date is not.
    """
    was = event.start_time
    event.start_time = start

    if minutes is None:
        if event.end_time is None or was is None:
            return
        minutes = _minutes(event.end_time) - _minutes(was)

    ends_at = _minutes(start) + minutes
    event.end_time = None if ends_at >= MINUTES_IN_DAY else _at(ends_at)


MINUTES_IN_DAY = 24 * 60


def _minutes(at: time) -> int:
    return at.hour * 60 + at.minute


def _at(minutes: int) -> time:
    return time(hour=minutes // 60, minute=minutes % 60)


def sync_event(db: Session, course: CourseModel, grade: GradeModel) -> EventModel:
    event = event_for_grade(db, grade.id)
    if event is None:
        event = EventModel(
            id=uuid.uuid4(),
            user_id=course.user_id,
            course_id=course.id,
            grade_id=grade.id,
            # All-day unless the grade carries a time. An exam usually has a
            # time and a room; the gradebook now knows the first of those when
            # the student entered it, and inventing a nine o'clock start when
            # they did not would still be worse than saying nothing.
            start_time=grade.due_time,
            end_time=None,
            skipped_dates=[],
        )
        db.add(event)

    event.title = grade.name
    event.starts_on = grade.due_date
    event.course_id = course.id
    event.kind = event_kind_for(grade)
    # Room and notes are left alone for the same reason a task's estimate is:
    # once the student has filled them in on the calendar, they are theirs, and
    # re-saving the grade must not wipe them.
    #
    # The times are the half-and-half case, and that is why this is not the
    # plain assignment the task side gets. A block has a start *and* an end and
    # the gradebook only ever knows the start, so a grade with a time moves the
    # start and a grade without one changes nothing -- clearing a start while
    # leaving an end behind would make the block incoherent, and a time typed
    # on the calendar before grades could carry one is still the only record of
    # when that exam is.
    if grade.due_time is not None:
        move_start(event, grade.due_time, grade.duration_minutes)

    # Deliberately no done state. A sat exam is history rather than an
    # unfinished chore, which is the whole reason this is not a task.

    db.flush()
    return event
