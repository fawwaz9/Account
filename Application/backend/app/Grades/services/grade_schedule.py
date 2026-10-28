"""Keeping a dated grade's task or calendar block in step with the grade.

The gradebook entry is the record: as "task" a dated grade raises a task that
checks itself off when the score lands; as "event" it draws a calendar block themed
by category. Switching removes what the other made, so a grade never has both.

Every function here flushes but never commits, since it runs inside the grade
service's transaction and a failed grade write must leave no task or event behind.
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
    """Return the task a grade raised, or None.

    Args:
        db: Open database session.
        grade_id: The dated grade.

    Returns:
        The task with this `grade_id`, or None.
    """
    return db.query(TaskModel).filter(TaskModel.grade_id == grade_id).first()


def event_for_grade(db: Session, grade_id: uuid.UUID) -> EventModel | None:
    """Return the calendar event a grade raised, or None.

    Args:
        db: Open database session.
        grade_id: The dated grade.

    Returns:
        The event with this `grade_id`, or None.
    """
    return db.query(EventModel).filter(EventModel.grade_id == grade_id).first()


def event_kind_for(grade: GradeModel) -> str:
    """Return the card kind for a grade's block: "midterm", "final" or "deadline".

    Args:
        grade: The dated grade.

    Returns:
        The event kind its category maps to; "deadline" by default.
    """
    return SCHEDULE_EVENT_KINDS.get(grade.category, DEFAULT_SCHEDULE_EVENT_KIND)


def sync_schedule_for_grade(db: Session, course: CourseModel, grade: GradeModel):
    """Create, update or remove whatever the grade's date and `schedule_as` call for.

    Args:
        db: Session inside the grade service's transaction; only flushed.
        course: The grade's course.
        grade: The grade after its changes.

    Returns:
        The task or event now standing for the grade, or None when it has no date.
    """
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
    """Delete a row, if there is one, and flush.

    Args:
        db: Open database session.
        row: A task or event row; None does nothing.
    """
    if row is not None:
        db.delete(row)
        db.flush()


def sync_task(db: Session, course: CourseModel, grade: GradeModel) -> TaskModel:
    """Create or update the task a dated grade raises, and close it once marked.

    The title, due date, due time and course follow the grade; the student's estimate,
    notes, tags and priority are left alone, and priority is seeded from the category
    only when the task is created.

    Args:
        db: Session inside the grade service's transaction; only flushed.
        course: The grade's course.
        grade: The dated grade.

    Returns:
        The grade's task.

    Note:
        A score checks the task off, but nothing here ever reopens one: finishing the
        work and the work being marked are different facts, and only the student
        reopens a task.
    """
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

    # A marked grade is finished work, so a score arriving checks the task off.
    # Guarded on `not task.done` for two reasons: re-saving an already-marked
    # grade would otherwise keep resetting `completed_at` to now and lose when
    # the work was actually done, and -- the important one -- this direction is
    # the only one there is.
    #
    # **Nothing here ever unchecks a task.** It used to derive the flag both
    # ways, `if task.done != scored`, which meant any save of a grade with an
    # empty score box tore up a completion the student had entered by hand:
    # `set_done(task, False)` nulls `completed_at` and un-archives, so the task
    # reappeared in the list and the record of when it was done was gone. Open
    # the grade to fix a typo in its name, save, and a lab you ticked off three
    # weeks ago is outstanding again.
    #
    # The root of it is that "I finished the lab" and "the lab has been marked"
    # are different facts -- yours on Tuesday, the TA's three weeks later -- and
    # deriving one from the other makes the gradebook the authority on both.
    # Once a task is checked off it stays checked off; only the student reopens
    # one, from the task editor. Clearing a score therefore leaves the task
    # closed, which is the deliberate trade: clearing a score is a statement
    # about the gradebook, not about whether the work happened.
    if grade.score is not None and not task.done:
        set_done(task, True)

    db.flush()
    return task


def forget_block_times(db: Session, grade: GradeModel) -> None:
    """Make a grade's block all-day again; called when the student removes its time.

    `sync_event` cannot tell "never had a time" from "just lost one", so the grade
    service calls this for the second case.

    Args:
        db: Session inside the grade service's transaction; only flushed.
        grade: The grade whose time was removed.
    """
    event = event_for_grade(db, grade.id)
    if event is None:
        return

    event.start_time = None
    event.end_time = None
    db.flush()


def move_start(event: EventModel, start: time, minutes: int | None = None) -> None:
    """Move a block to a new start time and set where it ends.

    Args:
        event: The calendar block.
        start: The new start time.
        minutes: How long it runs; None keeps the block's existing length, or no end
            when it had none.

    Note:
        An end that would pass midnight is dropped rather than wrapped, since an event
        has a single date.
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
"""Minutes in a day; an end at or past this is dropped."""


def _minutes(at: time) -> int:
    """Return a time of day as minutes after midnight."""
    return at.hour * 60 + at.minute


def _at(minutes: int) -> time:
    """Return minutes after midnight as a time of day."""
    return time(hour=minutes // 60, minute=minutes % 60)


def sync_event(db: Session, course: CourseModel, grade: GradeModel) -> EventModel:
    """Create or update the calendar block a dated grade raises.

    The title, date, course and kind follow the grade, and a grade with a time moves
    the start (and end, by its length); the room, notes and a time typed on the calendar
    when the grade has none are the student's and stay. A block has no done state.

    Args:
        db: Session inside the grade service's transaction; only flushed.
        course: The grade's course.
        grade: The dated grade.

    Returns:
        The grade's event.
    """
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
