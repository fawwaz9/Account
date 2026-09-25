"""The parts of the app that exist for the deployment rather than for a user.

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


def test_health_answers_HEAD_as_well_as_GET(monkeypatch):
    """What monitors actually send.

    UptimeRobot defaults to HEAD, and FastAPI's `@app.get` registers GET only --
    unlike a plain Starlette route, which adds HEAD for you. The symptom was a
    405 against a completely healthy service, which reads as a misconfigured
    monitor rather than a missing method.
    """
    main = app_with(monkeypatch, ENABLE_DOCS=None)
    with TestClient(main.app) as client:
        assert client.head("/health").status_code == 200
        assert client.get("/health").status_code == 200


def test_health_still_refuses_methods_that_change_things(monkeypatch):
    """GET and HEAD, and nothing else. A health check is a read."""
    main = app_with(monkeypatch, ENABLE_DOCS=None)
    with TestClient(main.app) as client:
        for method in ("post", "put", "delete", "patch"):
            assert getattr(client, method)("/health").status_code == 405, method


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


# ------------------------------------------------------- schema on startup --

def startup_statements(monkeypatch, tmp_path, **env):
    """How many statements a cold start issues against a prepared database."""
    from sqlalchemy import event

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'gate.db'}")
    main = app_with(monkeypatch, **env)

    # Prepared first, so what is being counted is the *re-checking* rather than
    # the one-time creation -- which is the whole point of the gate.
    from app._database.schema import apply_schema
    apply_schema()

    from app._database.db import engine
    seen = []

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cur, statement, params, context, many):
        seen.append(statement)

    try:
        with TestClient(main.app):
            pass
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return seen


def test_startup_rechecks_the_schema_by_default(monkeypatch, tmp_path):
    """On unless told otherwise: a fresh clone must still build its own tables."""
    statements = startup_statements(monkeypatch, tmp_path, RUN_SCHEMA_ON_STARTUP=None)

    assert len(statements) > 200, "the schema check should be doing its (expensive) work"


def test_the_gate_removes_the_startup_cost(monkeypatch, tmp_path):
    """The measurement this exists for: 278 statements become none.

    Against a local file that saving is invisible. Against a network database
    on a service that scales to zero it is roughly half a second off every cold
    start, re-establishing something that was already true.
    """
    statements = startup_statements(monkeypatch, tmp_path, RUN_SCHEMA_ON_STARTUP="0")

    ddl = [s for s in statements if s.strip().upper().startswith(("CREATE", "ALTER", "PRAGMA TABLE"))]
    assert ddl == [], f"no schema work should run, got {ddl[:3]}"
    assert len(statements) < 10, f"expected only the purge, got {len(statements)} statements"


def test_the_purge_still_runs_when_the_schema_check_does_not(monkeypatch, tmp_path):
    """The two are gated separately, and this is why.

    Turning off the purge as well would quietly break the thirty-day deletion
    promise -- an account marked for deletion would simply stay forever. It is
    one query when there is nothing to do, so it stays on regardless.
    """
    statements = startup_statements(monkeypatch, tmp_path, RUN_SCHEMA_ON_STARTUP="0")

    assert any("users" in s.lower() for s in statements), (
        "the expired-account purge should still have queried users"
    )


def test_applying_the_schema_is_idempotent(monkeypatch, tmp_path):
    """It runs as a deploy step, and deploys get retried."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'twice.db'}")
    app_with(monkeypatch)
    from app._database.schema import apply_schema

    apply_schema()
    apply_schema()  # must not raise

    from app._database.db import engine
    from sqlalchemy import inspect
    assert len(inspect(engine).get_table_names()) == 23


# ---------------------------------------------------------- allowed origins --

def preflight(monkeypatch, allowed, origin):
    monkeypatch.setenv("RUN_SCHEMA_ON_STARTUP", "0")
    main = app_with(monkeypatch, ALLOWED_ORIGINS=allowed)
    return TestClient(main.app).options(
        "/api/users/me",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    ).status_code


def test_the_configured_origin_is_allowed(monkeypatch):
    assert preflight(monkeypatch, "https://account.pages.dev", "https://account.pages.dev") == 200


def test_any_other_origin_is_refused(monkeypatch):
    """What the deployment gets wrong first, and the hardest to diagnose.

    Phase 0 reproduced it: the frontend was served on 5273 while this said 5173,
    and every browser request was refused before reaching a route. It reads as
    "the API is down", and appears nowhere in the API's own logs -- only in the
    browser console.
    """
    assert preflight(monkeypatch, "http://localhost:5173", "https://account.pages.dev") == 400


def test_several_origins_survive_the_space_people_type(monkeypatch):
    """"a, b" is how a list is written, and the space made the second entry
    " b" -- an origin no browser can ever send, so silently unreachable."""
    both = "http://localhost:5173, https://account.pages.dev"
    assert preflight(monkeypatch, both, "http://localhost:5173") == 200
    assert preflight(monkeypatch, both, "https://account.pages.dev") == 200
