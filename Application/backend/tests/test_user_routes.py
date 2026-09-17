"""The user routes, through the app rather than the services behind them.

Written because an audit found a bug that every service-level test missed by
construction: the year suggestion was attached inside `attach_year_suggestion`,
tested there, and correct -- but `/me` never called it. Settings reads its user
from `/me`, so the field was always null exactly where the control that depends
on it lives, and the control could never appear.

A test that calls the function cannot catch a route that does not. This goes
through the ASGI app.
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from app.Auth.dependencies import get_current_user
from app._database.db import get_db
from conftest import make_course


@pytest.fixture
def client(db, user):
    """The app, with authentication and the session pinned to the test user."""
    import app.main

    # The fixture user defaults to the google provider with no google_id, which
    # the User schema refuses for reasons unrelated to any of this.
    user.auth_provider = "local"
    user.current_school_year = 3
    user.current_semester = "Fall"
    db.commit()

    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    with TestClient(app.main.app) as test_client:
        yield test_client
    app.main.app.dependency_overrides.clear()


def test_me_carries_the_year_suggestion(db, user, client):
    """The regression test for the bug this file exists for."""
    make_course(db, user.id, "CPSC 320", year=3, semester="Fall",
                start_date=datetime.date(2026, 9, 9),
                end_date=datetime.date(2026, 12, 7))

    body = client.get("/api/users/me").json()

    assert body["suggested_first_year"] == 2024, \
        "Settings reads its user from here; a null means the control never shows"


def test_me_carries_the_anchor_itself(db, user, client):
    user.first_year_calendar_year = 2024
    db.commit()

    assert client.get("/api/users/me").json()["first_year_calendar_year"] == 2024


def test_me_still_never_leaks_the_password_hash(db, user, client):
    """The reason the route has a response_model at all. Adding fields to that
    schema is exactly when this is worth re-asserting."""
    body = client.get("/api/users/me").json()

    assert "password_hash" in user.__dict__ or True
    assert "password_hash" not in body


def test_me_suggests_nothing_when_no_course_carries_dates(db, user, client):
    make_course(db, user.id, "NODATE 100", year=3, semester="Fall")

    assert client.get("/api/users/me").json()["suggested_first_year"] is None


# The new grades routes, for the same reason: a response_model that does not
# match what the service returns is a 500 no service test can see.

def test_the_cheapest_path_route_serialises(db, user, client):
    from app.Grades.schemas.grade import GradeCreate
    from app.Grades.services.grade_service import add_grade
    from app.Grades.utils.enums import GradeSchedule

    course = make_course(db, user.id, "CPSC 221",
                         category_weights={"Assignment": 40.0, "Final": 60.0})
    add_grade(db, user.id, course.id, GradeCreate(
        name="Final exam", category="Final", max_score=100,
        schedule_as=GradeSchedule.TASK))

    response = client.get(f"/api/grades/{user.id}/courses/{course.id}/cheapest-path")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Final exam"]
    assert body["items"][0]["leverage"] > 0
    assert set(body) >= {"target", "current", "best", "reachable",
                         "remaining_count", "estimated_count", "unestimated_count"}
    assert "best_value_grade_id" not in body, "dropped when the rate became the ranking"


def test_the_cheapest_path_route_404s_on_a_course_that_is_not_yours(db, user, client):
    from conftest import make_user

    intruder = make_user(db, "someone-else@example.com")
    theirs = make_course(db, intruder.id, "ZZZZ 100")

    response = client.get(f"/api/grades/{user.id}/courses/{theirs.id}/cheapest-path")

    assert response.status_code == 404


def test_a_course_with_links_round_trips_through_the_api(db, user, client):
    course = make_course(db, user.id, "CPSC 221")

    saved = client.patch(
        f"/api/grades/{user.id}/courses/{course.id}",
        json={"links": [{"title": "Canvas", "url": "canvas.ubc.ca"}]},
    )
    assert saved.status_code == 200
    assert saved.json()["links"] == [
        {"title": "Canvas", "url": "https://canvas.ubc.ca"}
    ], "the bare domain should have gained a scheme on the way in"

    refused = client.patch(
        f"/api/grades/{user.id}/courses/{course.id}",
        json={"links": [{"title": "Bad", "url": "javascript:alert(1)"}]},
    )
    assert refused.status_code == 422, "the scheme guard has to hold at the edge"

    body = client.get(f"/api/grades/{user.id}/courses/{course.id}").json()
    assert body["links"] == [{"title": "Canvas", "url": "https://canvas.ubc.ca"}], \
        "and the refusal must not have changed what was stored"
