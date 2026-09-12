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

Switching between the two removes whatever the other had made, so a grade never
has both and the calendar never shows the same deadline twice.

Every function here mutates and flushes but never commits: they are called from
inside the grade service's own transaction, so a failed grade write must not
leave a task or an event behind.
"""

import uuid

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


def sync_event(db: Session, course: CourseModel, grade: GradeModel) -> EventModel:
    event = event_for_grade(db, grade.id)
    if event is None:
        event = EventModel(
            id=uuid.uuid4(),
            user_id=course.user_id,
            course_id=course.id,
            grade_id=grade.id,
            # All-day to begin with. An exam usually has a time and a room, but
            # the gradebook does not know them, and inventing a nine o'clock
            # start would be worse than saying nothing.
            start_time=None,
            end_time=None,
            skipped_dates=[],
        )
        db.add(event)

    event.title = grade.name
    event.starts_on = grade.due_date
    event.course_id = course.id
    event.kind = event_kind_for(grade)
    # Times, room and notes are left alone for the same reason a task's estimate
    # is: once the student has filled them in on the calendar, they are theirs,
    # and re-saving the grade must not wipe them.

    # Deliberately no done state. A sat exam is history rather than an
    # unfinished chore, which is the whole reason this is not a task.

    db.flush()
    return event
