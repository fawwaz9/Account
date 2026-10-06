"""The grade loop (Phase 1 D34): the last projection before the final, kept.

"Before the final we projected 83%; you got 82%" needs the 83% saved at the
moment it stopped being a prediction -- the final marked, or the result entered
-- because afterwards the course's grade *is* the result. These pin which
writes save it, that only the first one does, and that a course with nothing
marked has no projection to save.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, GradeModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.course import CourseUpdate
from app.Grades.schemas.grade import GradeCreate, GradeUpdate
from app.Grades.services.course_service import update_course
from app.Grades.services.grade_service import add_grade, add_grades_bulk, record_grade, update_grade
from app.shared.dates import user_today
from conftest import make_course


def mark(db, course, category, got, out_of=100.0, excluded=False):
    row = GradeModel(id=uuid.uuid4(), course_id=course.id, name=f"{category} {uuid.uuid4().hex[:4]}",
                     category=category, score=got, max_score=out_of, weight=0.0, excluded=excluded)
    db.add(row)
    db.commit()
    return row


def unmarked(db, course, category="Final"):
    return mark(db, course, category, None)


def stored(db, course):
    db.expire_all()
    return db.query(CourseModel).filter(CourseModel.id == course.id).one()


@pytest.fixture
def course(db, user):
    """Assignments 50%, final 50%; 83% on the assignments so far."""
    row = make_course(db, user.id, "CPSC 110")
    mark(db, row, "Assignment", 83.0)
    return row


def test_marking_the_final_keeps_the_grade_from_just_before(db, user, course):
    final = unmarked(db, course)
    record_grade(db, user.id, course.id, final.id, 60.0)

    row = stored(db, course)
    assert row.projected_before_final == 83.0
    assert row.projected_on == user_today(db, user.id)
    assert row.average != 83.0  # the final moved it; the projection is what it was


def test_only_the_first_end_counts(db, user, course):
    final = unmarked(db, course)
    record_grade(db, user.id, course.id, final.id, 60.0)
    record_grade(db, user.id, course.id, final.id, 95.0)  # re-marked
    update_course(db, user.id, course.id, CourseUpdate(final_grade=88.0))  # and the result entered

    assert stored(db, course).projected_before_final == 83.0


def test_a_final_unmarked_and_marked_again_keeps_the_first(db, user, course):
    """Taking the final's mark away reopens the forecast; the saved one stays."""
    final = unmarked(db, course)
    record_grade(db, user.id, course.id, final.id, 60.0)
    update_grade(db, user.id, course.id, final.id, GradeUpdate(score=None))
    mark(db, course, "Assignment", 20.0)  # the projection moves...
    record_grade(db, user.id, course.id, final.id, 60.0)  # ...and the forecast ends again
    assert stored(db, course).projected_before_final == 83.0


def test_entering_the_result_ends_it_when_the_final_was_never_marked(db, user, course):
    update_course(db, user.id, course.id, CourseUpdate(final_grade=81.0))
    assert stored(db, course).projected_before_final == 83.0


def test_a_course_with_nothing_marked_had_no_projection(db, user):
    bare = make_course(db, user.id, "MATH 100")
    update_course(db, user.id, bare.id, CourseUpdate(final_grade=75.0))
    assert stored(db, bare).projected_before_final is None


def test_a_final_marked_before_this_existed_is_never_backdated(db, user, course):
    """The forecast had already ended; any number saved now would be the result."""
    mark(db, course, "Final", 70.0)
    update_course(db, user.id, course.id, CourseUpdate(final_grade=77.0))
    assert stored(db, course).projected_before_final is None


def test_a_final_added_with_its_mark(db, user, course):
    add_grade(db, user.id, course.id, GradeCreate(name="Final exam", category="Final", score=60.0, max_score=100.0))
    assert stored(db, course).projected_before_final == 83.0


def test_a_final_marked_by_edit(db, user, course):
    final = unmarked(db, course)
    update_grade(db, user.id, course.id, final.id, GradeUpdate(score=60.0))
    assert stored(db, course).projected_before_final == 83.0


def test_a_final_in_a_bulk_entry(db, user, course):
    add_grades_bulk(db, user.id, course.id, [
        GradeCreate(name="A2", category="Assignment", score=100.0, max_score=100.0),
        GradeCreate(name="Final exam", category="Final", score=60.0, max_score=100.0),
    ])
    # Before the bulk entry, not part-way through it: the batch is one write.
    assert stored(db, course).projected_before_final == 83.0


def test_an_excluded_final_does_not_end_it(db, user, course):
    final = mark(db, course, "Final", None, excluded=True)
    record_grade(db, user.id, course.id, final.id, 40.0)
    assert stored(db, course).projected_before_final is None


def test_marking_something_else_does_not_end_it(db, user, course):
    unmarked(db, course)
    second = unmarked(db, course, "Assignment")
    record_grade(db, user.id, course.id, second.id, 100.0)
    assert stored(db, course).projected_before_final is None


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_course_says_it_and_a_client_cannot_write_it(db, user, course, client):
    url = f"/api/grades/{user.id}/courses/{course.id}"
    sent = client.patch(url, json={"final_grade": 81.0, "projected_before_final": 99.0, "projected_on": "2020-01-01"})
    assert sent.status_code == 200
    body = client.get(url).json()
    assert body["projected_before_final"] == 83.0
    assert body["projected_on"] == user_today(db, user.id).isoformat()
