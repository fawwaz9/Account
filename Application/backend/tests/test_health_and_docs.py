"""The two endpoints that exist for the deployment rather than for a user.

`/health` is what a restart policy and an uptime monitor read, and the docs
endpoints are what must not be readable by anyone who finds the hostname.

These are the first tests in this suite to go through the ASGI app rather than
calling a service directly. That is deliberate and narrow: what is being checked
here is routing and configuration -- which URLs exist, and what they answer --
and neither can be observed from a service function.
"""
import importlib
import os

import pytest
from fastapi.testclient import TestClient


def app_with(monkeypatch, **env):
    """A freshly configured app, since the docs flag is read at import.

    `FastAPI(docs_url=...)` is decided once when the object is constructed, so
    changing the variable afterwards changes nothing. Reloading the module is
    what actually re-reads it -- and is the honest way to test a setting whose
    whole nature is that it is fixed at startup.
    """
    import app.main

    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.reload(app.main)


@pytest.fixture(autouse=True)
def _restore_module():
    """Put the module back as the rest of the suite expects to find it."""
    yield
    import app.main
    importlib.reload(app.main)


# ------------------------------------------------------------------ health --

def test_health_reports_ok_when_the_database_answers(monkeypatch):
    main = app_with(monkeypatch, ENABLE_DOCS=None)
    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_503_when_the_database_cannot_be_reached(monkeypatch):
    """The whole reason it runs a query rather than returning a constant.

    A check that only proves the process is listening reports healthy while
    every real request fails -- which is exactly what a suspended database or a
    rotated password looks like.
    """
    main = app_with(monkeypatch, ENABLE_DOCS=None)

    def refuse():
        raise RuntimeError("connection refused")

    # Patched *inside* the context manager, after startup. The lifespan uses
    # SessionLocal too, so breaking it beforehand fails the app's boot rather
    # than the health check, and the test would pass for the wrong reason.
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "SessionLocal", refuse)
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


def test_health_is_not_in_the_schema(monkeypatch):
    """An infrastructure probe is not part of the API's surface."""
    main = app_with(monkeypatch, ENABLE_DOCS="1")
    with TestClient(main.app) as client:
        schema = client.get("/openapi.json").json()

    assert "/health" not in schema["paths"]


# -------------------------------------------------------------------- docs --

def test_docs_are_off_by_default(monkeypatch):
    """Unset means hidden. The variable has to be *asked for*, not remembered.

    This is the finding: all three were public, so the shape of every route was
    readable by anyone who found the hostname. Defaulting to off means a
    forgotten variable fails towards silence.
    """
    main = app_with(monkeypatch, ENABLE_DOCS=None)
    with TestClient(main.app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_docs_come_back_when_asked_for(monkeypatch):
    main = app_with(monkeypatch, ENABLE_DOCS="1")
    with TestClient(main.app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
def test_only_an_affirmative_value_enables_them(monkeypatch, value):
    """`ENABLE_DOCS=false` must not read as true, which a bare truthiness
    check on the string would do for every one of these."""
    main = app_with(monkeypatch, ENABLE_DOCS=value)
    with TestClient(main.app) as client:
        assert client.get("/docs").status_code == 404


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_the_usual_affirmatives_all_work(monkeypatch, value):
    main = app_with(monkeypatch, ENABLE_DOCS=value)
    with TestClient(main.app) as client:
        assert client.get("/docs").status_code == 200
