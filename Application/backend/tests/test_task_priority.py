"""Priority: seeded from a grade's category, and the student's thereafter."""
import datetime
import uuid

import pytest

from app._database.models import GradeModel, TaskModel
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Grades.services.grade_schedule import sync_schedule_for_grade
from app.Grades.utils.enums import DEFAULT_PRIORITY, GradeCategory, priority_for_category
from app.Tasks.schemas.recurring_task import RecurringTaskCreate, RecurringTaskUpdate
from app.Tasks.schemas.task import TaskCreate, TaskUpdate
from app.Tasks.services import recurring_task_service as rsvc
from app.Tasks.services.task_service import create_task, update_task
from tests.conftest import make_course


def add_grade(db, course, category, name="Item", score=None):
    grade = GradeModel(
        id=uuid.uuid4(), course_id=course.id, name=name, score=score,
        max_score=100.0, category=category, weight=10.0,
        due_date=datetime.date(2026, 10, 1), schedule_as="task", excluded=False,
    )
    db.add(grade)
    db.flush()
    return grade


@pytest.mark.parametrize("category,expected", [
    (GradeCategory.FINAL.value, 5),
    (GradeCategory.MIDTERM.value, 4),
    (GradeCategory.PROJECT.value, 4),
    (GradeCategory.ASSIGNMENT.value, 3),
    (GradeCategory.LAB.value, 3),
    (GradeCategory.QUIZ.value, 3),
    (GradeCategory.PARTICIPATION.value, 3),
    (GradeCategory.OTHER.value, 3),
    (GradeCategory.BONUS.value, 3),
])
def test_each_category_seeds_its_priority(category, expected):
    assert priority_for_category(category) == expected


def test_an_unknown_category_lands_in_the_middle(db):
    """A category added later must not silently arrive with no priority."""
    assert priority_for_category("Presentation") == DEFAULT_PRIORITY


def test_a_grade_raises_a_task_at_its_category_priority(db, user):
    course = make_course(db, user.id, "COSC 111")
    grade = add_grade(db, course, GradeCategory.FINAL.value, name="Final exam")

    sync_schedule_for_grade(db, course, grade)
    db.commit()

    task = db.query(TaskModel).filter(TaskModel.grade_id == grade.id).one()
    assert task.priority == 5


def test_re_saving_the_grade_does_not_undo_an_edited_priority(db, user):
    """sync runs on every grade write, so seeding must happen once only.

    Otherwise entering a score would silently revert the student's choice --
    the same failure as a repeating edit being overwritten.
    """
    course = make_course(db, user.id, "COSC 111")
    grade = add_grade(db, course, GradeCategory.LAB.value, name="Lab 4")
    sync_schedule_for_grade(db, course, grade)
    db.commit()

    task = db.query(TaskModel).filter(TaskModel.grade_id == grade.id).one()
    update_task(db, user.id, task.id, TaskUpdate(priority=5))

    # The score lands, which re-syncs the grade.
    grade.score = 88.0
    sync_schedule_for_grade(db, course, grade)
    db.commit()

    assert db.query(TaskModel).filter(TaskModel.grade_id == grade.id).one().priority == 5


def test_a_plain_task_defaults_to_the_middle_and_is_editable(db, user):
    task = create_task(db, user.id, TaskCreate(
        title="Renew bus pass", notes=None, due_date=None, due_time=None,
        estimated_minutes=None, course_id=None, tags=[],
    ))
    assert task.priority == DEFAULT_PRIORITY

    assert update_task(db, user.id, task.id, TaskUpdate(priority=1)).priority == 1


def test_a_task_can_be_created_at_a_chosen_priority(db, user):
    task = create_task(db, user.id, TaskCreate(
        title="Book flights", notes=None, due_date=None, due_time=None,
        estimated_minutes=None, course_id=None, tags=[], priority=5,
    ))
    assert task.priority == 5


@pytest.mark.parametrize("bad", [0, 6, -1, 99])
def test_priority_outside_one_to_five_is_rejected(bad):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TaskCreate(
            title="x", notes=None, due_date=None, due_time=None,
            estimated_minutes=None, course_id=None, tags=[], priority=bad,
        )


def test_a_repeating_rule_stamps_its_priority_on_every_occurrence(db, user):
    rule = rsvc.create_rule(db, user.id, RecurringTaskCreate(
        title="Readings", notes=None, due_time=None, estimated_minutes=None,
        course_id=None, tags=[], priority=4,
        starts_on=datetime.date.today(),
        recurrence=Recurrence(freq=Frequency.DAILY, interval=1, byday=[],
                              until=None, count=None),
        active=True,
    ))
    rsvc.materialise(db, user.id, rule)
    db.commit()

    rows = db.query(TaskModel).filter(TaskModel.recurring_id == rule.id).all()
    assert rows and {row.priority for row in rows} == {4}


def test_editing_a_rules_priority_reaches_its_outstanding_occurrences(db, user):
    rule = rsvc.create_rule(db, user.id, RecurringTaskCreate(
        title="Readings", notes=None, due_time=None, estimated_minutes=None,
        course_id=None, tags=[], priority=3,
        starts_on=datetime.date.today(),
        recurrence=Recurrence(freq=Frequency.DAILY, interval=1, byday=[],
                              until=None, count=None),
        active=True,
    ))
    rsvc.materialise(db, user.id, rule)
    db.commit()

    rsvc.update_rule(db, user.id, rule.id, RecurringTaskUpdate(priority=5))

    rows = db.query(TaskModel).filter(TaskModel.recurring_id == rule.id).all()
    assert {row.priority for row in rows} == {5}
