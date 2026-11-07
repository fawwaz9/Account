"""One transaction for several writes (MCP Phase 0; audit M5 for these paths).

The agent path saves a proposal as one unit: a course and its assessments, say, together or
not at all. The services it calls take `commit=False`, which flushes their change into the
caller's transaction and commits nothing; every existing caller keeps the default, which
commits as before. A caller that rolls back after `commit=False` leaves no trace.
"""
import uuid

import pytest

from app._database.models import CourseModel, GradeModel
from app.Grades.schemas.course import CourseCreate
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services import grade_service
from app.Grades.services.course_service import create_course
from app.Grades.services.grade_service import add_grades_bulk, record_grade, set_category_sharing
from app.Grades.utils.enums import GradeCategory, Semester
from conftest import make_course


def new_course(code="STAT 302"):
    return CourseCreate(code=code, name="Statistics", year=3, semester=Semester.FALL,
                        category_weights={GradeCategory.MIDTERM: 40.0, GradeCategory.FINAL: 60.0})


def assessments():
    return [GradeCreate(name="Midterm 1", category=GradeCategory.MIDTERM, max_score=100.0),
            GradeCreate(name="Midterm 2", category=GradeCategory.MIDTERM, max_score=100.0)]


def stored_courses(db, user):
    db.expire_all()
    return db.query(CourseModel).filter(CourseModel.user_id == user.id).count()


def test_a_course_and_its_assessments_roll_back_together(db, user):
    course = create_course(db, user.id, new_course(), commit=False)
    add_grades_bulk(db, user.id, course.id, assessments(), commit=False)
    assert db.query(GradeModel).filter(GradeModel.course_id == course.id).count() == 2

    db.rollback()

    assert stored_courses(db, user) == 0
    assert db.query(GradeModel).filter(GradeModel.course_id == course.id).count() == 0


def test_a_course_and_its_assessments_commit_together(db, user):
    course = create_course(db, user.id, new_course(), commit=False)
    add_grades_bulk(db, user.id, course.id, assessments(), commit=False)
    db.commit()

    db.rollback()  # nothing left to undo
    assert stored_courses(db, user) == 1
    assert db.query(GradeModel).filter(GradeModel.course_id == course.id).count() == 2


def test_a_failure_halfway_leaves_nothing_once_the_caller_rolls_back(db, user, monkeypatch):
    course = create_course(db, user.id, new_course(), commit=False)

    def broken(*args, **kwargs):
        raise RuntimeError("the calendar sync failed")
    monkeypatch.setattr(grade_service, "sync_schedule_for_grade", broken)

    with pytest.raises(RuntimeError):
        add_grades_bulk(db, user.id, course.id, assessments(), commit=False)
    # The transaction is the caller's: the service didn't roll it back on its own.
    assert db.query(CourseModel).filter(CourseModel.id == course.id).count() == 1
    db.rollback()

    assert stored_courses(db, user) == 0


def test_the_default_still_commits_for_every_existing_caller(db, user):
    course = create_course(db, user.id, new_course())
    add_grades_bulk(db, user.id, course.id, assessments())
    db.rollback()
    assert stored_courses(db, user) == 1
    assert db.query(GradeModel).filter(GradeModel.course_id == course.id).count() == 2


def test_a_score_filled_without_committing_is_undone_by_the_caller(db, user):
    course = make_course(db, user.id, "CPSC 110")
    (grade,) = add_grades_bulk(db, user.id, course.id, [GradeCreate(
        name="Lab 1", category=GradeCategory.ASSIGNMENT, max_score=10.0)])

    record_grade(db, user.id, course.id, grade.id, 8.0, commit=False)
    db.rollback()

    db.expire_all()
    assert db.get(GradeModel, grade.id).score is None


def test_a_split_set_without_committing_is_undone_by_the_caller(db, user):
    course = create_course(db, user.id, new_course())
    first, second = add_grades_bulk(db, user.id, course.id, assessments())

    set_category_sharing(db, user.id, course.id, "Midterm", {first.id: 15.0, second.id: 25.0}, commit=False)
    db.rollback()

    db.expire_all()
    assert db.get(GradeModel, first.id).subcategory_weight is None


def test_without_committing_the_ids_and_defaults_already_exist(db, user):
    """Flushed, so the caller can record what it wrote before it commits."""
    course = create_course(db, user.id, new_course(), commit=False)
    grades = add_grades_bulk(db, user.id, course.id, assessments(), commit=False)
    assert isinstance(course.id, uuid.UUID)
    assert all(isinstance(g.id, uuid.UUID) for g in grades)
    db.rollback()
