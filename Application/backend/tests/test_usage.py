"""Usage counts: what they record, and that recording can never break anything.

Phase 0 item 4. The counters are what make the vision's gates readable, but
they are worth nothing next to the action they count -- a course that failed
to save because a counter did is a broken app. Most of this file is about that.
"""
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, UsageEventModel
from app.Auth.dependencies import get_current_user
from app.Usage.services import usage_service
from app.Usage.services.usage_service import CREATE, VISIT, record
from app.Users.services.user_service import delete_user, purge_expired_users
from conftest import make_course


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def counts(db, user):
    return {(r.kind, r.module): r.count for r in db.query(UsageEventModel)
            .filter(UsageEventModel.user_id == user.id).all()}


def test_a_visit_is_counted_once_per_day_and_module(db, user, client):
    for _ in range(3):
        assert client.post(f"/api/usage/{user.id}/visits", json={"module": "grades"}).status_code == 204
    client.post(f"/api/usage/{user.id}/visits", json={"module": "budget"})

    assert counts(db, user) == {(VISIT, "grades"): 3, (VISIT, "budget"): 1}
    assert db.query(UsageEventModel).count() == 2


def test_only_known_modules_are_accepted(user, client):
    assert client.post(f"/api/usage/{user.id}/visits", json={"module": "admin"}).status_code == 422


def test_adding_a_course_counts_as_a_create_in_grades(db, user, client):
    response = client.post(f"/api/grades/{user.id}/courses", json={
        "code": "CPSC 210", "name": "Software Construction", "semester": "Fall", "year": 2,
        "credits": 4, "category_weights": {"Final": 100},
    })
    assert response.status_code == 200, response.text
    assert counts(db, user) == {(CREATE, "grades"): 1}


def test_a_broken_counter_does_not_break_the_action(db, user, client):
    """The course saves and the client gets it, whatever the counter does."""
    with mock.patch.object(usage_service, "user_today", side_effect=RuntimeError("counter down")):
        response = client.post(f"/api/grades/{user.id}/courses", json={
            "code": "CPSC 213", "name": "Systems", "semester": "Fall", "year": 2,
            "credits": 4, "category_weights": {"Final": 100},
        })

    assert response.status_code == 200, response.text
    assert response.json()["code"] == "CPSC 213"
    db.expire_all()
    assert db.query(CourseModel).filter(CourseModel.code == "CPSC 213").count() == 1
    assert counts(db, user) == {}


def test_a_broken_visit_still_answers_204(user, client):
    with mock.patch.object(usage_service, "user_today", side_effect=RuntimeError("down")):
        assert client.post(f"/api/usage/{user.id}/visits", json={"module": "tasks"}).status_code == 204


def test_recording_leaves_unsaved_work_alone(db, user):
    """Never commits someone else's pending changes, and never rolls them back."""
    course = make_course(db, user.id, "CPSC 110")
    course.name = "renamed but not saved"

    record(db, user.id, VISIT, "grades")

    assert course in db.dirty
    assert counts(db, user) == {}
    db.rollback()
    db.expire_all()
    assert db.get(CourseModel, course.id).name == "CPSC 110 course"


def test_usage_leaves_with_the_account(db, user):
    record(db, user.id, VISIT, "grades")
    delete_user(db, user.id)
    purge_expired_users(db, on_day=__import__("datetime").date(2099, 1, 1))
    assert db.query(UsageEventModel).count() == 0


def test_a_visit_from_a_notification_is_counted_as_prompted(db, user, client):
    """The universe test needs a room visited unprompted (§13.2); a visit a
    notification caused is kept apart, and an unprompted one later the same
    day still counts as its own."""
    client.post(f"/api/usage/{user.id}/visits", json={"module": "tasks", "prompted": True})
    client.post(f"/api/usage/{user.id}/visits", json={"module": "tasks"})
    kinds = sorted(
        row.kind for row in db.query(UsageEventModel).filter(UsageEventModel.user_id == user.id)
    )
    assert kinds == ["prompted_visit", "visit"]
