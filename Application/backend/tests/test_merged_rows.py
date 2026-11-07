"""Audit H1 for courses and grades: an edit is checked as the whole row it leaves.

An update schema checks only what was sent. Before this, a blank name, an end before the
start or a graded transfer credit was committed, the PATCH answered 500 although the write
landed, and every list holding the row then failed to load. Now the row as it will stand is
checked against the rules a new one must meet, refused with a 400 that says why, and
nothing is written. Each test then reads the list again, which is what used to break.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, GradeModel
from app.Auth.dependencies import get_current_user
from conftest import make_course


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app, raise_server_exceptions=False)
    finally:
        app.main.app.dependency_overrides.clear()


def course_url(user, course):
    return f"/api/grades/{user.id}/courses/{course.id}"


def lists_cleanly(client, user, course):
    """The course list and the course page both still read."""
    assert client.get(f"/api/grades/{user.id}/courses").status_code == 200
    assert client.get(course_url(user, course)).status_code == 200


# ----------------------------------------------------------------- courses --

@pytest.mark.parametrize(("change", "says"), [
    ({"name": "   "}, "course name cannot be empty"),
    ({"code": "   "}, "course code cannot be empty"),
    ({"end_date": "2026-09-01"}, "end date cannot be before start date"),
    ({"transfer_credit": True}, "A transfer credit carries credits, not a grade"),
    ({"name": None}, "name"),
])
def test_a_course_edit_that_leaves_a_bad_row_is_refused_and_writes_nothing(db, user, client, change, says):
    course = make_course(db, user.id, "CPSC 110", final_grade=84.0,
                         start_date=date(2026, 9, 3), end_date=date(2026, 12, 5))

    response = client.patch(course_url(user, course), json=change)

    assert response.status_code in (400, 422), response.text
    assert says in response.text
    db.expire_all()
    stored = db.get(CourseModel, course.id)
    assert (stored.name, stored.code, stored.end_date, stored.transfer_credit) == (
        "CPSC 110 course", "CPSC 110", date(2026, 12, 5), False)
    lists_cleanly(client, user, course)


def test_a_start_moved_past_the_stored_end_is_caught_on_the_whole_row(db, user, client):
    """Only the start is sent; the end it now passes is the stored one."""
    course = make_course(db, user.id, "CPSC 110", start_date=date(2026, 9, 3), end_date=date(2026, 12, 5))
    response = client.patch(course_url(user, course), json={"start_date": "2027-01-10"})
    assert response.status_code == 400
    assert "end date cannot be before start date" in response.json()["detail"]
    lists_cleanly(client, user, course)


def test_renaming_onto_another_course_s_code_is_a_400_not_a_500(db, user, client):
    make_course(db, user.id, "MATH 100")
    course = make_course(db, user.id, "CPSC 110")
    response = client.patch(course_url(user, course), json={"code": "MATH 100"})
    assert response.status_code == 400
    assert response.json()["detail"] == "course code already exists"
    lists_cleanly(client, user, course)


def test_a_sound_course_edit_still_saves(db, user, client):
    course = make_course(db, user.id, "CPSC 110")
    response = client.patch(course_url(user, course), json={"name": "Computation", "code": "CPSC 110"})
    assert response.status_code == 200
    assert response.json()["name"] == "Computation"


# ------------------------------------------------------------------ grades --

def add_grade(db, course, **fields):
    grade = GradeModel(id=uuid.uuid4(), course_id=course.id, name="Lab 1", category="Assignment",
                       score=None, max_score=10.0, weight=50.0, **fields)
    db.add(grade)
    db.commit()
    return grade


@pytest.mark.parametrize(("change", "says"), [
    ({"name": "   "}, "Grade name cannot be empty"),
    ({"name": None}, "name"),
    ({"max_score": None}, "max_score"),
    ({"category": None}, "category"),
    ({"excluded": None}, "excluded"),
])
def test_a_grade_edit_that_leaves_a_bad_row_is_refused_and_writes_nothing(db, user, client, change, says):
    course = make_course(db, user.id, "CPSC 110")
    grade = add_grade(db, course)

    response = client.patch(f"{course_url(user, course)}/grades/{grade.id}", json=change)

    assert response.status_code in (400, 422), response.text
    assert says in response.text
    db.expire_all()
    stored = db.get(GradeModel, grade.id)
    assert (stored.name, stored.max_score, stored.category, stored.excluded) == ("Lab 1", 10.0, "Assignment", False)
    lists_cleanly(client, user, course)


def test_a_sound_grade_edit_still_saves(db, user, client):
    course = make_course(db, user.id, "CPSC 110")
    grade = add_grade(db, course)
    response = client.patch(f"{course_url(user, course)}/grades/{grade.id}", json={"name": "Lab one", "score": 9})
    assert response.status_code == 200
    assert (response.json()["name"], response.json()["score"]) == ("Lab one", 9.0)
