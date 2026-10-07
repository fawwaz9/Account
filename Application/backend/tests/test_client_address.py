"""Rate limiting per caller behind Cloud Run (Phase 2 item 12a, D18).

The limiters keyed on the peer address, which behind Cloud Run is the
platform's proxy: one shared budget for everyone. The caller's address is the
X-Forwarded-For entry the trusted proxy appended -- counted from the right,
because the left end is whatever the caller chose to send.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.routes import auth as auth_route
from app.Auth.services.client_address import client_of
from app.Auth.services.login_throttle import SlidingWindowLimiter
from app.config import settings


def request_with(*forwarded: str, peer: str = "169.254.1.1") -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


# --- reading the address ------------------------------------------------------

def test_off_by_default_the_header_is_ignored():
    assert settings.TRUSTED_PROXY_HOPS == 0
    assert client_of(request_with("198.51.100.4")) == "169.254.1.1"


def test_one_hop_takes_the_entry_the_front_end_appended():
    assert client_of(request_with("198.51.100.4"), hops=1) == "198.51.100.4"


def test_what_the_caller_wrote_on_the_left_is_ignored():
    """The forgery: the caller sends a header, the front end appends after it."""
    assert client_of(request_with("203.0.113.7, 198.51.100.4"), hops=1) == "198.51.100.4"
    assert client_of(request_with("203.0.113.7", "198.51.100.4"), hops=1) == "198.51.100.4"


def test_two_hops_counts_two_in_from_the_right():
    assert client_of(request_with("203.0.113.7, 198.51.100.4, 35.191.0.9"), hops=2) == "198.51.100.4"


@pytest.mark.parametrize("forwarded", [(), ("",), (" , ",), ("not-an-address",), ("198.51.100.4; drop",)])
def test_anything_that_does_not_hold_up_falls_back_to_the_peer(forwarded):
    assert client_of(request_with(*forwarded), hops=1) == "169.254.1.1"


def test_too_few_entries_for_the_hops_falls_back_to_the_peer():
    assert client_of(request_with("198.51.100.4"), hops=2) == "169.254.1.1"


def test_an_ipv6_caller_is_read_and_normalised():
    assert client_of(request_with("2001:DB8::0:1"), hops=1) == "2001:db8::1"


# --- through the sign-in route --------------------------------------------------

@pytest.fixture
def app_client(monkeypatch):
    import app.main
    # Small, fresh limiters, so the tests spend a few attempts, not thirty.
    monkeypatch.setattr(auth_route, "per_client", SlidingWindowLimiter(max_attempts=3, window_seconds=60))
    monkeypatch.setattr(auth_route, "per_account", SlidingWindowLimiter(max_attempts=100, window_seconds=60))
    with TestClient(app.main.app) as client:
        yield client


def wrong_password(client, forwarded):
    body = {"email": f"{uuid.uuid4().hex}@example.com", "password": "not-the-password"}
    return client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": forwarded}).status_code


def test_with_the_switch_on_two_callers_get_two_budgets(app_client, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    assert [wrong_password(app_client, "198.51.100.4") for _ in range(3)] == [401, 401, 401]
    assert wrong_password(app_client, "198.51.100.4") == 429
    assert wrong_password(app_client, "198.51.100.5") == 401


def test_a_forged_header_cannot_buy_a_fresh_budget(app_client, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    for _ in range(3):
        wrong_password(app_client, "198.51.100.4")
    # A new invented address on the left every time; the front end's entry stays.
    assert wrong_password(app_client, f"203.0.113.{uuid.uuid4().int % 250}, 198.51.100.4") == 429


def test_with_the_switch_off_everyone_shares_the_peers_budget(app_client):
    """Today's behaviour, unchanged until the switch is flipped."""
    for _ in range(3):
        wrong_password(app_client, "198.51.100.4")
    assert wrong_password(app_client, "198.51.100.5") == 429
