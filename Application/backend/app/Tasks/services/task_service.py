"""Tasks: what is outstanding, what is done, and what a week actually costs.

A task with a due date is also a calendar item -- the calendar reads them
through `list_tasks` with a window rather than through a table of its own, so
there is one record of a deadline rather than two that can disagree.
"""

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app._database.models import CourseModel, TaskModel, UserModel, utc_now
from app.Tasks.schemas.task import Task as TaskSchema, TaskCreate, TaskUpdate


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def course_codes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (
        db.query(CourseModel.id, CourseModel.code)
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    return {row.id: row.code for row in rows}


def attach_course_code(task: TaskModel, codes: dict[uuid.UUID, str]) -> TaskModel:
    """Label a task with its course code.

    School work is categorised by course code rather than by a tag the student
    has to remember to type, so the code has to travel with the task.
    """
    task.course_code = codes.get(task.course_id)
    return task


def sort_key(task: TaskModel):
    """Soonest first; undated tasks last, in the order they were created.

    `date.max` rather than None so undated tasks sort after every dated one
    instead of raising on the comparison.
    """
    return (task.due_date or date.max, task.due_time or datetime.min.time(), task.created_at or datetime.min)


def list_tasks(
    db: Session,
    user_id: uuid.UUID,
    *,
    include_done: bool = False,
    include_archived: bool = False,
    start: date | None = None,
    end: date | None = None,
    course_id: uuid.UUID | None = None,
):
    """Outstanding tasks by default; `start`/`end` bound `due_date` inclusively.

    A window excludes undated tasks, since the calendar asking for a week means
    the week's deadlines rather than everything ever.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(TaskModel).filter(TaskModel.user_id == user_id)

    if not include_archived:
        query = query.filter(TaskModel.archived.is_(False))
    if not include_done:
        query = query.filter(TaskModel.done.is_(False))
    if course_id is not None:
        query = query.filter(TaskModel.course_id == course_id)
    if start is not None:
        query = query.filter(TaskModel.due_date.isnot(None), TaskModel.due_date >= start)
    if end is not None:
        query = query.filter(TaskModel.due_date.isnot(None), TaskModel.due_date <= end)

    tasks = query.all()
    tasks.sort(key=sort_key)

    codes = course_codes(db, user_id)
    return [attach_course_code(task, codes) for task in tasks]


def get_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    task = (
        db.query(TaskModel)
        .filter(TaskModel.id == task_id, TaskModel.user_id == user_id)
        .first()
    )
    if task is None:
        return None

    return attach_course_code(task, course_codes(db, user_id))


def create_task(db: Session, user_id: uuid.UUID, data: TaskCreate):
    if not user_exists(db, user_id):
        return None

    if data.course_id is not None and owned_course(db, user_id, data.course_id) is None:
        raise ValueError("Course not found")

    task = TaskModel(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=data.course_id,
        title=data.title.strip(),
        notes=data.notes,
        due_date=data.due_date,
        due_time=data.due_time,
        estimated_minutes=data.estimated_minutes,
        tags=list(data.tags),
        done=False,
        archived=False,
        created_at=utc_now(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def update_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate):
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("course_id") is not None:
        if owned_course(db, user_id, update_data["course_id"]) is None:
            raise ValueError("Course not found")

    done = update_data.pop("done", None)
    if "title" in update_data and update_data["title"] is not None:
        update_data["title"] = update_data["title"].strip()

    for key, value in update_data.items():
        setattr(task, key, value)

    if done is not None:
        set_done(task, done)

    if task.due_time is not None and task.due_date is None:
        raise ValueError("A time of day needs a date to go with it")

    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def set_done(task: TaskModel, done: bool) -> None:
    """Check or uncheck a task, keeping `completed_at` in step.

    Completing also archives: a checked task's place is the record of the term,
    not the list of what is left. Unchecking brings it back out, since the
    common reason to uncheck is having checked the wrong row.
    """
    task.done = done
    if done:
        task.completed_at = utc_now()
        task.archived = True
    else:
        task.completed_at = None
        task.archived = False


def delete_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    # Detached before the delete: attaching the course code marked the instance
    # dirty, and deleting it in the same session would otherwise flush an UPDATE
    # for a row that no longer exists.
    snapshot = TaskSchema.model_validate(task)
    db.delete(task)
    db.commit()
    return snapshot
