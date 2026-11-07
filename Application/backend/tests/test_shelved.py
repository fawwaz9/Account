"""The shelf: fitness, teams, clubs and office hours are mounted, but every route answers 404.

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

#: Modules shelved whole, by their router's prefix.
PREFIXES = {"fitness": "/api/fitness", "teams": "/api/teams", "clubs": "/api/clubs"}
#: Modules shelved route by route, inside a router that stays open.
SINGLE_ROUTES = {"office_hours": {
    ("POST", "/api/grades/{user_id}/courses/{course_id}/office-hours"),
    ("DELETE", "/api/grades/{user_id}/office-hours/{checkin_id}"),
}}


def shelved_routes() -> list[tuple[str, str]]:
    """Every shelved (method, path), with each path parameter filled in."""
    singles = set().union(*(SINGLE_ROUTES[name] for name in SHIPPED_SHELF if name in SINGLE_ROUTES))
    found = []
    for route in app.main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        whole = any(route.path.startswith(PREFIXES[name] + "/") for name in SHIPPED_SHELF if name in PREFIXES)
        methods = sorted(route.methods) if whole else sorted(m for m in route.methods if (m, route.path) in singles)
        if not methods:
            continue
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route.path)
        found.extend((method, path) for method in methods)
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


def test_the_app_ships_with_fitness_teams_clubs_and_office_hours_shelved():
    assert SHIPPED_SHELF == {"fitness", "teams", "clubs", "office_hours"}


def test_every_shelved_module_still_has_its_routes_mounted():
    """Shelved, not deleted: the walk below has something to walk in each module."""
    paths = [path for _, path in shelved_routes()]
    for name in PREFIXES:
        assert any(path.startswith(PREFIXES[name] + "/") for path in paths), name
    assert sum("office-hours" in path for path in paths) == 2


def test_the_rest_of_the_class_figures_router_stays_open(client, closed_shelf):
    """Only the two office-hours routes are shelved; the course's figures still ask for a login."""
    response = client.get(f"/api/grades/{uuid.uuid4()}/courses/{uuid.uuid4()}/class-figures")
    assert response.status_code == 401


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
