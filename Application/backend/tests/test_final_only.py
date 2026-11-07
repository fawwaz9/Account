"""Final-grade-only courses (owner, 2026-11-07): a past course entered as just its final.

Derived on every read, never stored: a final grade above 0, no weight a mark could count
toward, and no marks. Its card opens Edit Course instead of an empty page, and it counts
like any finished course.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import GradeModel
from app.Auth.dependencies import get_current_user
from conftest import make_course

NO_WEIGHTS = {}


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def listed(client, user):
    return {c["code"]: c for c in client.get(f"/api/grades/{user.id}/courses").json()}


def test_a_final_with_nothing_behind_it_is_final_only(db, user, client):
    make_course(db, user.id, "CPSC 110", final_grade=84.0, category_weights=NO_WEIGHTS)
    course = listed(client, user)["CPSC 110"]
    assert course["final_only"] is True
    assert course["letter_grade"] != ""


def test_weights_marks_or_no_final_make_a_full_course(db, user, client):
    make_course(db, user.id, "MATH 100", final_grade=80.0)  # Assignment 50, Final 50
    make_course(db, user.id, "ENGL 110", final_grade=0.0, category_weights=NO_WEIGHTS)
    marked = make_course(db, user.id, "PHYS 117", final_grade=75.0, category_weights={"Bonus": 5.0})
    db.add(GradeModel(id=uuid.uuid4(), course_id=marked.id, name="Lab", category="Bonus",
                      score=4.0, max_score=5.0))
    db.commit()

    courses = listed(client, user)
    assert courses["MATH 100"]["final_only"] is False, "weights a mark could count toward"
    assert courses["ENGL 110"]["final_only"] is False, "no final recorded"
    assert courses["PHYS 117"]["final_only"] is False, "a mark is behind it"


def test_bonus_weight_alone_still_counts_as_final_only(db, user, client):
    """Bonus sits outside the 100 a course is marked out of, so it isn't an outline."""
    make_course(db, user.id, "CPSC 121", final_grade=77.0, category_weights={"Bonus": 5.0})
    assert listed(client, user)["CPSC 121"]["final_only"] is True


def test_adding_weights_later_makes_it_a_full_course(db, user, client):
    course = make_course(db, user.id, "CPSC 110", final_grade=84.0, category_weights=NO_WEIGHTS)
    response = client.patch(f"/api/grades/{user.id}/courses/{course.id}/category-weights",
                            json={"category_weights": {"Assignment": 40.0, "Final": 60.0}})
    assert response.status_code == 200, response.text
    assert listed(client, user)["CPSC 110"]["final_only"] is False


def test_it_cannot_be_set_by_a_client(db, user, client):
    course = make_course(db, user.id, "MATH 100", final_grade=80.0)
    client.patch(f"/api/grades/{user.id}/courses/{course.id}", json={"final_only": True})
    assert listed(client, user)["MATH 100"]["final_only"] is False


def test_it_counts_in_the_cumulative_like_any_finished_course(db, user, client):
    user.current_school_year, user.current_semester = 2, "Fall"
    db.commit()
    make_course(db, user.id, "CPSC 110", year=1, final_grade=80.0, category_weights=NO_WEIGHTS)
    make_course(db, user.id, "MATH 100", year=1, final_grade=90.0, category_weights=NO_WEIGHTS)
    summary = client.get(f"/api/grades/{user.id}/grades/dashboard").json()
    assert summary["cumulative_average"] == pytest.approx(85.0)
