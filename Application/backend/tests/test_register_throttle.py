"""`/register` had no ceiling on how often it could be called.

`/login` has been limited since audit #6, because it verifies a secret. The
register route was left open on the reasoning that there is no secret to guess
there -- which misses what it actually spends. Every accepted call writes a row
and runs a ~200ms password hash, and every refused one answers whether an
address is already taken or on the invitation list. Unbounded, the first is a
way to fill a 500MB database and pin a small instance, and the second is an
enumeration oracle.

The tests below go through the ASGI app rather than the limiter class, because
what is being checked is the route's behaviour: which requests are answered,
which are refused, and what a refusal says. The class itself is covered in
`test_session_integrity.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_route
from app.Auth.services.login_throttle import (
    REGISTRATION_MAX_ATTEMPTS,
    REGISTRATION_WINDOW_SECONDS,
    SlidingWindowLimiter,
)


@pytest.fixture
def client():
    """The app itself. Registrations here land in the temp database conftest
    points `DATABASE_URL` at, never the real one."""
    import app.main

    with TestClient(app.main.app) as test_client:
        yield test_client


@pytest.fixture
def ceiling(monkeypatch):
    """Swap in a limiter with a small ceiling, and return a function to set it.

    The real ceiling is 20 an hour. Proving the mechanism does not require
    making 21 requests, and where a request has to genuinely succeed it costs a
    real bcrypt hash -- so the tests set the ceiling they need.

    Patched on the route module rather than on `login_throttle`, because
    `auth.py` imported the name and holds its own reference.
    """
    def set_to(max_attempts):
        limiter = SlidingWindowLimiter(max_attempts=max_attempts, window_seconds=60)
        monkeypatch.setattr(auth_route, "per_client_registration", limiter)
        return limiter

    return set_to


def signup(email=None, password="correct-horse-battery"):
    address = email or f"{uuid.uuid4().hex}@example.com"
    return {"name": "Someone", "email": address, "password": password}


def uninvited(monkeypatch):
    """An invitation list nobody in these tests is on.

    A refused signup returns before `hash_password`, so a test that only needs
    to spend attempts can spend twenty of them in milliseconds.
    """
    monkeypatch.setenv("ALLOWED_SIGNUP_EMAILS", "nobody-here@example.com")


# ------------------------------------------------------------- the ceiling --

def test_a_burst_of_attempts_is_refused(client, ceiling, monkeypatch):
    uninvited(monkeypatch)
    ceiling(3)

    for _ in range(3):
        assert client.post("/api/auth/register", json=signup()).status_code == 400

    refused = client.post("/api/auth/register", json=signup())
    assert refused.status_code == 429


def test_successful_registrations_count_too(client, ceiling, monkeypatch):
    """The difference from login, and the whole reason this exists.

    Login clears a key on success, because succeeding proves the caller was
    entitled to try. Succeeding here proves nothing except that the database is
    one row larger -- so if only failures counted, the flood would be the one
    thing still unbounded.
    """
    monkeypatch.delenv("ALLOWED_SIGNUP_EMAILS", raising=False)
    ceiling(2)

    assert client.post("/api/auth/register", json=signup()).status_code == 201
    assert client.post("/api/auth/register", json=signup()).status_code == 201

    refused = client.post("/api/auth/register", json=signup())
    assert refused.status_code == 429


def test_the_refusal_says_when_to_come_back(client, ceiling, monkeypatch):
    """A 429 with no Retry-After tells a caller to guess, and they guess wrong."""
    uninvited(monkeypatch)
    ceiling(1)
    client.post("/api/auth/register", json=signup())

    refused = client.post("/api/auth/register", json=signup())

    assert refused.status_code == 429
    retry_after = int(refused.headers["Retry-After"])
    assert 0 < retry_after <= 61


def test_the_refusal_does_not_say_whether_the_address_was_usable(client, ceiling, monkeypatch):
    """Otherwise the throttle becomes the oracle it exists to close.

    A 429 that leaked "...and that address was taken anyway" would let someone
    keep enumerating through the very response meant to stop them.
    """
    uninvited(monkeypatch)
    ceiling(1)
    client.post("/api/auth/register", json=signup())

    refused = client.post("/api/auth/register", json=signup(email="taken@example.com"))

    assert "taken@example.com" not in refused.text
    assert refused.json()["detail"] == "Too many sign-up attempts. Try again later."


# ----------------------------------------------------- what it costs to ask --

def test_a_refused_attempt_never_reaches_the_database(client, ceiling, monkeypatch):
    """The point of checking first. A throttle applied after the work has been
    done bounds the row count and nothing else -- the hash still ran, the query
    still ran, and the instance is still busy."""
    uninvited(monkeypatch)
    ceiling(1)
    client.post("/api/auth/register", json=signup())

    def explode(*args, **kwargs):
        raise AssertionError("the throttled request reached create_local_user")

    monkeypatch.setattr(auth_route.user_service, "create_local_user", explode)

    assert client.post("/api/auth/register", json=signup()).status_code == 429


def test_an_attempt_that_fails_still_counts(client, ceiling, monkeypatch):
    """Recorded on the way in, not on the way out.

    If the count were incremented after a successful create, every request that
    raised -- a duplicate address, an uninvited one, an unexpected error --
    would be free, which is every request an attacker is making.
    """
    uninvited(monkeypatch)
    limiter = ceiling(5)

    for _ in range(3):
        client.post("/api/auth/register", json=signup())

    assert limiter.retry_after("testclient") is None
    client.post("/api/auth/register", json=signup())
    client.post("/api/auth/register", json=signup())
    assert limiter.retry_after("testclient") is not None


# -------------------------------------------------------- separate budgets --

def test_signing_up_does_not_use_up_the_sign_in_budget(client, ceiling, monkeypatch):
    """One shared limiter would let a registration flood lock out the people who
    already have accounts -- turning a nuisance into a denial of service against
    exactly the users it should protect."""
    uninvited(monkeypatch)
    ceiling(1)
    client.post("/api/auth/register", json=signup())
    assert client.post("/api/auth/register", json=signup()).status_code == 429

    signing_in = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "correct-horse-battery"},
    )

    assert signing_in.status_code == 401


# ------------------------------------------------------------- the defaults --

def test_the_shipped_ceiling_leaves_room_for_the_group_this_app_is_for(client):
    """A guard on the constant, not on the mechanism.

    Every key is the peer address, and behind a proxy that is one address for
    everybody -- so a ceiling tuned for a single person is a ceiling for the
    whole invited group signing up on the same evening. Tightening this without
    first keying on a trusted forwarded-for header locks them out.
    """
    assert REGISTRATION_MAX_ATTEMPTS >= 20
    assert REGISTRATION_WINDOW_SECONDS <= 60 * 60
