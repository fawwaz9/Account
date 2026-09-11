"""Keeping a task in step with the grade it came from.

An assignment with a due date is two things at once: a row in the gradebook
waiting for a score, and something to do before Friday. Entering it twice is
how the two end up disagreeing, so the gradebook entry is the record and the
task is derived from it.

The lifecycle, in full:

* a grade gains a due date -> a task appears, due then, against that course
* the grade's name or due date changes -> the task follows
* the grade's score lands            -> the task checks itself off
* the score is cleared again         -> the task reopens
* the due date is cleared, or the grade is deleted -> the task goes with it

Every function here mutates and flushes but never commits: they are called from
inside the grade service's own transaction, so a failed grade write must not
leave a task behind.
"""

import uuid

from sqlalchemy.orm import Session

from app._database.models import CourseModel, GradeModel, TaskModel, utc_now
from app.Tasks.services.task_service import set_done


def task_for_grade(db: Session, grade_id: uuid.UUID) -> TaskModel | None:
    return db.query(TaskModel).filter(TaskModel.grade_id == grade_id).first()


def sync_task_for_grade(db: Session, course: CourseModel, grade: GradeModel) -> TaskModel | None:
    """Create, update, close or remove the task belonging to one grade."""
    existing = task_for_grade(db, grade.id)

    if grade.due_date is None:
        # The task only existed because the grade had a date. Without one there
        # is nothing to be due, and leaving it would strand a task whose title
        # tracks a grade it is no longer tied to.
        if existing is not None:
            db.delete(existing)
            db.flush()
        return None

    task = existing
    if task is None:
        task = TaskModel(
            id=uuid.uuid4(),
            user_id=course.user_id,
            course_id=course.id,
            grade_id=grade.id,
            created_at=utc_now(),
            tags=[],
        )
        db.add(task)

    task.title = grade.name
    task.due_date = grade.due_date
    task.course_id = course.id
    # Everything else the student set on the task -- an estimate, notes, tags --
    # is theirs and is left alone.

    # A marked grade is finished work. Only move the flag when it disagrees, so
    # re-saving an already-marked grade does not keep resetting `completed_at`
    # to now and lose when it was actually done.
    scored = grade.score is not None
    if task.done != scored:
        set_done(task, scored)

    db.flush()
    return task
