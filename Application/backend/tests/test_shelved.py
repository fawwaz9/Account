"""The shelf: fitness, teams and clubs are mounted, but every route answers 404.

The suite opens the shelf for every other test (conftest.py). Here it is closed
again, to the set the app ships with, captured before any fixture runs.
"""
import re
import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app.Auth.services.session_service import create_access_token
from app.shared import shelved

#: The shelf as the app ships it, read at import, before `_open_shelf` empties it.
SHIPPED_SHELF = frozenset(shelved.SHELVED)

PREFIXES = {"fitness": "/api/fitness", "teams": "/api/teams", "clubs": "/api/clubs"}


def shelved_routes() -> list[tuple[str, str]]:
    """Every (method, path) under a shelved prefix, with each path parameter filled in."""
    found = []
    for route in app.main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not any(route.path.startswith(PREFIXES[name] + "/") for name in SHIPPED_SHELF):
            continue
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route.path)
        found.extend((method, path) for method in sorted(route.methods))
    return found


@pytest.fixture
def closed_shelf(monkeypatch):
    """Close the shelf to what the app ships with."""
    monkeypatch.setattr(shelved, "SHELVED", set(SHIPPED_SHELF))


@pytest.fixture
def client(db):
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.pop(get_db, None)


def test_the_app_ships_with_fitness_teams_and_clubs_shelved():
    assert SHIPPED_SHELF == {"fitness", "teams", "clubs"}


def test_every_shelved_module_still_has_its_routes_mounted():
    """Shelved, not deleted: the walk below has something to walk in each module."""
    paths = [path for _, path in shelved_routes()]
    for name in SHIPPED_SHELF:
        assert any(path.startswith(PREFIXES[name] + "/") for path in paths), name


def test_every_shelved_route_answers_404_without_a_login(client, closed_shelf):
    routes = shelved_routes()
    assert len(routes) >= 50
    for method, path in routes:
        response = client.request(method, path, json={})
        assert response.status_code == 404, (method, path, response.status_code)
        assert response.json() == {"detail": shelved.SHELVED_DETAIL}, (method, path)


def test_every_shelved_route_answers_404_to_a_signed_in_owner(client, closed_shelf, user):
    """Even the user's own id gets nothing: the shelf comes before every check."""
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    for method, path in shelved_routes():
        path = re.sub(r"^(/api/\w+/)[0-9a-f-]{36}", rf"\g<1>{user.id}", path)
        response = client.request(method, path, json={}, headers=headers)
        assert response.status_code == 404, (method, path, response.status_code)
        assert response.json() == {"detail": shelved.SHELVED_DETAIL}, (method, path)


def test_routes_outside_the_shelf_are_untouched(client, closed_shelf):
    """Partners, the one social module that stays, still asks for a login."""
    response = client.get(f"/api/partners/{uuid.uuid4()}")
    assert response.status_code == 401


def test_an_open_shelf_reaches_the_route(client, user):
    """With the shelf open (as in the rest of the suite), the route answers as before."""
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    response = client.get(f"/api/fitness/{user.id}/exertion", headers=headers)
    assert response.status_code == 200
