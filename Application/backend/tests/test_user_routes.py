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


# ------------------------------------------------------- preferences, patched --
#
# None of this was covered before. `update_user` had three service-level tests
# for preferences and all three passed a `UserPreferences` *instance*, so the
# shape the browser actually sends -- a JSON object naming a few keys -- reached
# the code only in production. The bug that followed is the one below.


def test_patching_one_preference_leaves_the_others_alone(db, user, client):
    """The live bug, at the edge: Settings reset what it did not mention.

    `UserUpdate.preferences` was typed `UserPreferences`, where every field has a
    default, so this request -- which names one key -- was parsed into a complete
    fourteen-field model and the merge wrote all fourteen. The eight the client
    never sends went back to their defaults on every save.

    Asserted on the stored column, not the response. `UserDetail.preferences` is
    a `UserPreferences`, so the response is re-validated on the way out with
    every default filled in -- it cannot show an absent key, and a test that read
    it would pass against the bug.
    """
    user.preferences = {"timezone": "America/Vancouver", "credit_target": 150}
    db.commit()

    response = client.patch(
        f"/api/users/{user.id}", json={"preferences": {"credit_target": 160}}
    )
    assert response.status_code == 200

    db.refresh(user)
    assert user.preferences["credit_target"] == 160
    assert user.preferences["timezone"] == "America/Vancouver", \
        "the key the request never mentioned must not have moved"


def test_saving_the_academic_form_does_not_reset_the_timezone(db, user, client):
    """Named for what actually happened, with the real payload.

    These six keys are exactly what SettingsPage sends. `timezone` is not among
    them, and it is the one preference in the model that changes behaviour --
    reminder firing times and the early/late figures both resolve through it.
    Before the fix this request moved America/Vancouver to America/Regina.
    """
    user.preferences = {"timezone": "America/Vancouver"}
    db.commit()

    response = client.patch(f"/api/users/{user.id}", json={"preferences": {
        "credit_target": 120,
        "gpa_scale_enabled": True,
        "default_target_grade": 85,
        "study_day_start": "08:00",
        "study_day_end": "22:00",
        "min_free_block_minutes": 30,
    }})
    assert response.status_code == 200

    db.refresh(user)
    assert user.preferences["timezone"] == "America/Vancouver"


def test_patching_no_preferences_changes_nothing(db, user, client):
    """An empty object is a request to change nothing, not to reset everything."""
    user.preferences = {"timezone": "America/Vancouver", "credit_target": 150}
    db.commit()
    before = dict(user.preferences)

    assert client.patch(
        f"/api/users/{user.id}", json={"preferences": {}}
    ).status_code == 200

    db.refresh(user)
    assert user.preferences == before


def test_an_invalid_timezone_is_refused_at_the_edge(db, user, client):
    """422, not 400, and the difference is where the check runs.

    The validator lives on the preferences model, so FastAPI runs it while
    parsing the body -- before `edit_user` is entered and therefore before its
    `except ValueError` can map anything to 400. That is the right answer for a
    malformed body; it is recorded here because the route documents 400 and 404
    and not this.

    The control matters more than the status: a patch type that dropped the
    validator would store the bad value, and `get_preferences` re-validates on
    *read* from six call sites that catch nothing. A bad write would surface as a
    500 on every page that reads a preference.
    """
    user.preferences = {"timezone": "America/Vancouver"}
    db.commit()

    response = client.patch(
        f"/api/users/{user.id}", json={"preferences": {"timezone": "Mars/Olympus"}}
    )

    assert response.status_code == 422
    db.refresh(user)
    assert user.preferences["timezone"] == "America/Vancouver", \
        "a refused request must not have written anything"


def test_a_valid_timezone_can_actually_be_saved(db, user, client):
    """The control for the test above.

    Without this, "invalid is refused" could be passing because *every* timezone
    is refused -- which is exactly what a validator that forgot to pass `None`
    through, or a field left off the patch model, would do.
    """
    assert client.patch(
        f"/api/users/{user.id}",
        json={"preferences": {"timezone": "America/Vancouver"}},
    ).status_code == 200

    db.refresh(user)
    assert user.preferences["timezone"] == "America/Vancouver"


def test_the_two_settings_tabs_do_not_overwrite_each_other(db, user, client):
    """The payloads the tabbed Settings page actually sends, in both directions.

    The route tests above cover the mechanism. This covers the feature built on
    it: Academic and Calendar are separate forms with separate Save buttons, each
    sending only its own three preference keys. That is safe only because the
    patch is a real patch -- before it, whichever tab you saved last would have
    reset the other one's fields to model defaults.

    Both directions, because a merge that works one way round and not the other
    is a thing that happens.
    """
    academic = {
        "credit_target": 150,
        "gpa_scale_enabled": False,
        "default_target_grade": 92.0,
    }
    calendar = {
        "study_day_start": "06:30",
        "study_day_end": "23:00",
        "min_free_block_minutes": 45,
    }

    assert client.patch(
        f"/api/users/{user.id}", json={"preferences": academic}
    ).status_code == 200
    assert client.patch(
        f"/api/users/{user.id}", json={"preferences": calendar}
    ).status_code == 200

    db.refresh(user)
    # Saving Calendar second must not have reverted Academic.
    assert user.preferences["credit_target"] == 150
    assert user.preferences["gpa_scale_enabled"] is False
    assert user.preferences["default_target_grade"] == 92.0
    assert user.preferences["min_free_block_minutes"] == 45

    # And the other way round.
    assert client.patch(
        f"/api/users/{user.id}", json={"preferences": academic}
    ).status_code == 200

    db.refresh(user)
    assert user.preferences["min_free_block_minutes"] == 45
    assert user.preferences["study_day_start"] == "06:30:00"
