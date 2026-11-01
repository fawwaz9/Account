"""BYOAI: your digest, read by your own assistant (Phase 4 item 7, D4).

A new kind of credential, so the hardest tests in the phase:

* off by default; a token is shown once and only its hash is stored;
* a token reads the digest of its owner and nothing else: refused at **every**
  other route (enumerated, not listed);
* a session token is refused at the assistant routes;
* revoking, or making a new token, stops the old one at once;
* a deleted account's token is dead; malformed and session-shaped tokens are
  refused before any lookup; repeated failures are throttled;
* the MCP door answers the same digest, and nothing but its one tool.
"""
import hashlib
import re
import uuid
from datetime import time

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.main
import app.api.routes.assistant as assistant_routes
from app._database.db import get_db
from app._database.models import AssistantTokenModel, EventModel, UserModel
from app.Auth.dependencies import get_current_user
from app.Auth.services.login_throttle import SlidingWindowLimiter
from app.Auth.services.session_service import create_access_token
from app.Briefing.services import assistant_service
from app.Briefing.services.digest_service import build_digest
from app.shared.dates import user_today
from conftest import make_user
from tests.test_isolation import PUBLIC

ASSISTANT_PATHS = {"/api/assistant/digest", "/api/assistant/mcp"}


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    """Each test starts with a clean failure count."""
    monkeypatch.setattr(assistant_routes, "failed_attempts", SlidingWindowLimiter(max_attempts=30))


@pytest.fixture
def client(db):
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


@pytest.fixture
def owner(db, user):
    """A user with something on today's calendar, so the digest has content."""
    db.add(EventModel(id=uuid.uuid4(), user_id=user.id, title="Owner's lecture", kind="personal",
                      starts_on=user_today(db, user.id), start_time=time(10), end_time=time(11)))
    db.commit()
    return user


def session_headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_token(client, user):
    answer = client.post(f"/api/briefing/{user.id}/assistant-token", headers=session_headers(user))
    assert answer.status_code == 201, answer.text
    return answer.json()["token"]


# ------------------------------------------------------------ making one --

def test_off_until_made(db, owner, client):
    body = client.get(f"/api/briefing/{owner.id}/assistant-token", headers=session_headers(owner)).json()

    assert body == {"enabled": False, "prefix": None, "created_at": None, "last_used_at": None}


def test_shown_once_and_stored_only_as_a_hash(db, owner, client):
    token = make_token(client, owner)

    assert token.startswith(assistant_service.TOKEN_PREFIX) and len(token) > 40
    row = db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == owner.id).one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in {row.token_hash, row.prefix}
    status = client.get(f"/api/briefing/{owner.id}/assistant-token", headers=session_headers(owner)).json()
    assert status["enabled"] is True and status["prefix"] == token[:12]
    assert "token" not in status


def test_a_user_holds_at_most_one(db, owner, client):
    first = make_token(client, owner)
    second = make_token(client, owner)

    assert db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == owner.id).count() == 1
    assert client.get("/api/assistant/digest", headers=bearer(first)).status_code == 401
    assert client.get("/api/assistant/digest", headers=bearer(second)).status_code == 200


def test_managing_it_needs_your_own_session(db, owner, client):
    stranger = make_user(db, "stranger@example.com")
    url = f"/api/briefing/{owner.id}/assistant-token"

    assert client.post(url, headers=session_headers(stranger)).status_code == 403
    assert client.delete(url, headers=session_headers(stranger)).status_code == 403
    assert client.get(url, headers=session_headers(stranger)).status_code == 403


# ------------------------------------------------------------- using one --

def test_a_token_reads_its_owners_digest(db, owner, client):
    token = make_token(client, owner)

    answer = client.get("/api/assistant/digest", headers=bearer(token))

    assert answer.status_code == 200
    assert "Owner's lecture" in answer.json()["text"]
    db.expire_all()
    assert db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == owner.id).one().last_used_at


def test_a_token_never_reads_anyone_elses(db, owner, client):
    stranger = make_user(db, "stranger@example.com")
    db.add(EventModel(id=uuid.uuid4(), user_id=stranger.id, title="Stranger's secret", kind="personal",
                      starts_on=user_today(db, owner.id), start_time=time(9), end_time=time(10)))
    db.commit()
    token = make_token(client, owner)

    text = client.get("/api/assistant/digest", headers=bearer(token)).json()["text"]

    assert "Stranger's secret" not in text and "Owner's lecture" in text


def test_the_token_is_refused_at_every_other_route(db, owner, client):
    """Enumerated: every route in the app, every method, the owner's id in the path.

    Public routes (the health check) answer anyone, so they prove nothing either way.
    """
    token = make_token(client, owner)
    tried = 0
    for route in app.main.app.routes:
        if not isinstance(route, APIRoute) or route.path in ASSISTANT_PATHS:
            continue
        if any((method, route.path) in PUBLIC for method in route.methods):
            continue
        url = re.sub(r"{user_id}", str(owner.id), route.path)
        url = re.sub(r"{\w+}", str(uuid.uuid4()), url)
        for method in sorted(route.methods - {"HEAD"}):
            answer = client.request(method, url, headers=bearer(token), json={})
            tried += 1
            assert not 200 <= answer.status_code < 300, f"{method} {route.path} answered {answer.status_code}"
    assert tried > 200, "the walk tried too few routes to mean anything"


def test_a_session_token_is_refused_at_the_assistant_routes(db, owner, client):
    make_token(client, owner)

    assert client.get("/api/assistant/digest", headers=session_headers(owner)).status_code == 401
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post("/api/assistant/mcp", json=rpc, headers=session_headers(owner)).status_code == 401


@pytest.mark.parametrize("value", [
    None, "", "Bearer", "Bearer ", "Basic abc", "Bearer acct_", "Bearer acct_not-a-real-token",
    "Bearer acct_" + "x" * 200, "Bearer notprefixed-token",
])
def test_anything_but_a_live_token_is_refused(db, owner, client, value):
    make_token(client, owner)
    headers = {} if value is None else {"Authorization": value}

    answer = client.get("/api/assistant/digest", headers=headers)

    assert answer.status_code == 401
    assert answer.headers.get("www-authenticate", "").startswith("Bearer")


@pytest.mark.parametrize("value", [
    "Bearer notprefixed-token", "Bearer " + create_access_token(uuid.uuid4(), 0), "Bearer acct_" + "x" * 200,
])
def test_malformed_and_session_shaped_tokens_never_reach_the_lookup(db, owner, client, monkeypatch, value):
    calls = []
    monkeypatch.setattr(assistant_service, "assistant_token_user", lambda *a: calls.append(a))

    assert client.get("/api/assistant/digest", headers={"Authorization": value}).status_code == 401
    assert calls == []


def test_a_live_token_under_another_scheme_is_refused(db, owner, client):
    token = make_token(client, owner)

    assert client.get("/api/assistant/digest", headers={"Authorization": f"Basic {token}"}).status_code == 401
    assert client.get("/api/assistant/digest", headers={"Authorization": f"bearer {token}"}).status_code == 200


def test_revoking_stops_it_at_once(db, owner, client):
    token = make_token(client, owner)
    assert client.get("/api/assistant/digest", headers=bearer(token)).status_code == 200

    assert client.delete(f"/api/briefing/{owner.id}/assistant-token", headers=session_headers(owner)).status_code == 204

    assert client.get("/api/assistant/digest", headers=bearer(token)).status_code == 401
    assert db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == owner.id).count() == 0


def test_a_deleted_accounts_token_is_dead(db, owner, client):
    from app._database.models import utc_now
    token = make_token(client, owner)
    db.query(UserModel).filter(UserModel.id == owner.id).update({"deleted_at": utc_now()})
    db.commit()

    assert client.get("/api/assistant/digest", headers=bearer(token)).status_code == 401


def test_repeated_failures_are_throttled(db, owner, client, monkeypatch):
    monkeypatch.setattr(assistant_routes, "failed_attempts", SlidingWindowLimiter(max_attempts=3))
    token = make_token(client, owner)
    for _ in range(3):
        assert client.get("/api/assistant/digest", headers=bearer("acct_wrong")).status_code == 401

    blocked = client.get("/api/assistant/digest", headers=bearer(token))

    assert blocked.status_code == 429 and blocked.headers.get("retry-after")


def test_a_browser_page_from_elsewhere_is_refused(db, owner, client):
    token = make_token(client, owner)

    foreign = client.get("/api/assistant/digest", headers={**bearer(token), "Origin": "https://evil.example"})
    ours = client.get("/api/assistant/digest", headers={**bearer(token), "Origin": "http://localhost:5173"})

    assert foreign.status_code == 403 and ours.status_code == 200


# ------------------------------------------------------------------- MCP --

def rpc(client, token, method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        body["id"] = id_
    if params is not None:
        body["params"] = params
    return client.post("/api/assistant/mcp", json=body, headers=bearer(token))


def test_mcp_initialize_and_list_the_one_tool(db, owner, client):
    token = make_token(client, owner)

    init = rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}).json()
    tools = rpc(client, token, "tools/list").json()

    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert [t["name"] for t in tools["result"]["tools"]] == ["get_briefing"]


def test_mcp_offers_its_newest_version_for_one_it_doesnt_speak(db, owner, client):
    token = make_token(client, owner)

    init = rpc(client, token, "initialize", {"protocolVersion": "1999-01-01"}).json()

    assert init["result"]["protocolVersion"] == assistant_routes.MCP_VERSIONS[0]


def test_mcp_tool_returns_the_same_digest(db, owner, client):
    token = make_token(client, owner)

    result = rpc(client, token, "tools/call", {"name": "get_briefing", "arguments": {}}).json()["result"]

    expected = build_digest(db, owner.id)
    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": expected.text}]
    assert result["structuredContent"]["text"] == expected.text


def test_mcp_refuses_anything_else(db, owner, client):
    token = make_token(client, owner)

    unknown_tool = rpc(client, token, "tools/call", {"name": "read_transactions"}).json()
    unknown_method = rpc(client, token, "resources/list").json()

    assert unknown_tool["error"]["code"] == -32602
    assert unknown_method["error"]["code"] == -32601


def test_mcp_notifications_and_streams(db, owner, client):
    token = make_token(client, owner)

    assert rpc(client, token, "notifications/initialized", id_=None).status_code == 202
    assert client.get("/api/assistant/mcp", headers=bearer(token)).status_code == 405
