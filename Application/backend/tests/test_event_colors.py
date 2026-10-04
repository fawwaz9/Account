"""Event colours, saved and read through the app rather than the schema.

Preferences have already shipped one bug that only the route could show -- a
partial patch dumped as a full one, so every Settings save reset the time zone.
So these go through PATCH /users/{id} and GET /users/me, and assert on the stored
column as well as the response.
"""
import pytest
from fastapi.testclient import TestClient

from app.Auth.dependencies import get_current_user
from app._database.db import get_db


@pytest.fixture
def client(db, user):
    import app.main

    user.auth_provider = "local"
    db.commit()

    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    with TestClient(app.main.app) as test_client:
        yield test_client
    app.main.app.dependency_overrides.clear()


def patch(client, user, preferences):
    return client.patch(f"/api/users/{user.id}", json={"preferences": preferences})


def test_colours_round_trip_lowercased(db, user, client):
    response = patch(client, user, {"event_colors": {"lecture": "#AABBCC", "final": "#112233"}})
    assert response.status_code == 200

    db.refresh(user)
    assert user.preferences["event_colors"] == {"lecture": "#aabbcc", "final": "#112233"}
    assert client.get("/api/users/me").json()["preferences"]["event_colors"] == {
        "lecture": "#aabbcc", "final": "#112233",
    }


def test_no_colours_reads_as_an_empty_map_not_a_missing_key(db, user, client):
    # The frontend falls back per kind; it should never meet `undefined` here.
    assert client.get("/api/users/me").json()["preferences"]["event_colors"] == {}


@pytest.mark.parametrize("bad", [
    {"lecture": "#fff"},          # short form: the picker never emits it
    {"lecture": "red"},           # a name
    {"lecture": "#12345g"},       # not hex
    {"lecture": "#aabbcc; x"},    # it goes into a CSS property
    {"seminar": "#aabbcc"},       # not a kind -- kinds are a fixed enum
])
def test_a_bad_colour_or_kind_is_refused_and_nothing_is_stored(db, user, client, bad):
    user.preferences = {"event_colors": {"lab": "#010203"}}
    db.commit()

    response = patch(client, user, {"event_colors": bad})

    assert response.status_code == 422
    db.refresh(user)
    assert user.preferences["event_colors"] == {"lab": "#010203"}, \
        "a refused request must not have written anything"


def test_saving_the_time_zone_leaves_colours_alone(db, user, client):
    """The partial-patch bug, for the newest key."""
    user.preferences = {"event_colors": {"lab": "#010203"}, "timezone": "America/Regina"}
    db.commit()

    assert patch(client, user, {"timezone": "America/Vancouver"}).status_code == 200

    db.refresh(user)
    assert user.preferences["event_colors"] == {"lab": "#010203"}
    assert user.preferences["timezone"] == "America/Vancouver"


def test_saving_colours_leaves_the_time_zone_alone(db, user, client):
    user.preferences = {"timezone": "America/Vancouver"}
    db.commit()

    assert patch(client, user, {"event_colors": {"lab": "#010203"}}).status_code == 200

    db.refresh(user)
    assert user.preferences["timezone"] == "America/Vancouver"


def test_sending_the_map_replaces_it_so_a_reset_kind_is_gone(db, user, client):
    # Settings sends the whole map; a kind put back to its default is absent.
    user.preferences = {"event_colors": {"lab": "#010203", "lecture": "#040506"}}
    db.commit()

    assert patch(client, user, {"event_colors": {"lecture": "#040506"}}).status_code == 200

    db.refresh(user)
    assert user.preferences["event_colors"] == {"lecture": "#040506"}


def test_an_empty_map_resets_every_kind(db, user, client):
    user.preferences = {"event_colors": {"lab": "#010203"}}
    db.commit()

    assert patch(client, user, {"event_colors": {}}).status_code == 200

    db.refresh(user)
    assert user.preferences["event_colors"] == {}
