"""The daily briefing push (Phase 4 item 6, D13).

Pinned: it goes out at the user's own hour, once a day, with a few hours' grace
for a missed scheduler run and none after; off means never; a failed delivery is
retried; each person's briefing reaches only their own devices and carries only
their own day; the schedule is set and cleared through its own route.
"""
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import EventModel
from app.Auth.dependencies import get_current_user
from app.config import settings
from app.Notifications.schemas.push import SubscriptionCreate, SubscriptionKeys
from app.Notifications.services import push_service
from app.Notifications.services.push_service import BRIEFING_GRACE_HOURS, dispatch_briefings, subscribe
from app.Notifications.services.webpush import generate_keys
from app._database.identity import users_with_briefing
from conftest import make_user

UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
# Noon UTC is 06:00 in the fixture user's zone (America/Regina, UTC-6).
NOON_UTC = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
LOCAL_DAY = NOON_UTC.date()


@pytest.fixture(autouse=True)
def vapid_configured(monkeypatch):
    private, _ = generate_keys()
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", private)


def device(db, user, name="phone"):
    endpoint = f"https://push.invalid/{user.email}/{name}"
    subscribe(db, user.id, SubscriptionCreate(endpoint=endpoint, keys=SubscriptionKeys(p256dh=UA_PUBLIC, auth=AUTH)))
    return endpoint


def wants_briefing(db, user, hour):
    user.preferences = {**(user.preferences or {}), "briefing_hour": hour}
    db.commit()


class Recorder:
    def __init__(self, status=201):
        self.sent, self.status = [], status

    def __call__(self, endpoint, headers, body):
        self.sent.append(endpoint)
        return self.status


@pytest.fixture
def payloads(monkeypatch):
    """What each user's briefing said, captured before encryption."""
    seen: dict = {}
    real = push_service.briefing_payload

    def capture(digest):
        payload = real(digest)
        seen.setdefault(digest.on_date, []).append(payload)
        return payload

    monkeypatch.setattr(push_service, "briefing_payload", capture)
    return seen


def test_it_goes_out_at_the_hour_once_a_day(db, user):
    phone = device(db, user)
    wants_briefing(db, user, 6)
    send = Recorder()

    assert dispatch_briefings(db, send, at=NOON_UTC) == 1
    assert dispatch_briefings(db, send, at=NOON_UTC + timedelta(minutes=5)) == 0
    assert dispatch_briefings(db, send, at=NOON_UTC + timedelta(days=1)) == 1
    assert send.sent == [phone, phone]
    db.refresh(user)
    assert user.briefing_sent_on == LOCAL_DAY + timedelta(days=1)


def test_not_before_the_hour(db, user):
    device(db, user)
    wants_briefing(db, user, 7)

    assert dispatch_briefings(db, Recorder(), at=NOON_UTC) == 0
    assert dispatch_briefings(db, Recorder(), at=NOON_UTC + timedelta(hours=1, minutes=5)) == 1


def test_a_missed_run_sends_late_but_not_stale(db, user):
    device(db, user)
    wants_briefing(db, user, 6)

    assert dispatch_briefings(db, Recorder(), at=NOON_UTC + timedelta(hours=BRIEFING_GRACE_HOURS)) == 0
    assert dispatch_briefings(db, Recorder(), at=NOON_UTC + timedelta(hours=BRIEFING_GRACE_HOURS - 1, minutes=59)) == 1


def test_the_lookup_names_only_who_asked_and_has_a_device(db, user):
    quiet = make_user(db, "quiet@example.com")
    deviceless = make_user(db, "deviceless@example.com")
    device(db, user)
    device(db, quiet)
    wants_briefing(db, user, 6)
    wants_briefing(db, deviceless, 6)

    assert users_with_briefing(db) == [user.id]


def test_off_means_never(db, user):
    device(db, user)

    assert dispatch_briefings(db, Recorder(), at=NOON_UTC) == 0


def test_no_device_no_briefing(db, user):
    wants_briefing(db, user, 6)

    assert dispatch_briefings(db, Recorder(), at=NOON_UTC) == 0


def test_a_failed_delivery_is_tried_again(db, user):
    device(db, user)
    wants_briefing(db, user, 6)

    assert dispatch_briefings(db, Recorder(status=500), at=NOON_UTC) == 0
    db.refresh(user)
    assert user.briefing_sent_on is None
    assert dispatch_briefings(db, Recorder(), at=NOON_UTC + timedelta(minutes=5)) == 1


def test_nothing_without_push_set_up(db, user, monkeypatch):
    device(db, user)
    wants_briefing(db, user, 6)
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", None)

    assert dispatch_briefings(db, Recorder(), at=NOON_UTC) == 0


def test_each_briefing_reaches_only_its_owner_with_only_their_day(db, user, payloads):
    other = make_user(db, "other@example.com")
    other.preferences = {**(other.preferences or {}), "timezone": "America/Regina"}
    db.commit()
    for who, title in ((user, "Owner's lab"), (other, "Other's shift")):
        db.add(EventModel(id=uuid.uuid4(), user_id=who.id, title=title, kind="personal", starts_on=LOCAL_DAY,
                          start_time=time(9), end_time=time(10)))
    db.commit()
    mine, theirs = device(db, user), device(db, other)
    wants_briefing(db, user, 6)
    wants_briefing(db, other, 6)
    send = Recorder()

    assert dispatch_briefings(db, send, at=NOON_UTC) == 2

    assert sorted(send.sent) == sorted([mine, theirs])
    bodies = [p["body"] for p in payloads[LOCAL_DAY]]
    assert any("Owner's lab" in b and "Other's shift" not in b for b in bodies)
    assert any("Other's shift" in b and "Owner's lab" not in b for b in bodies)


# ------------------------------------------------------------------ routes --

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_schedule_route_sets_and_clears(db, user, client):
    url = f"/api/briefing/{user.id}/schedule"

    assert client.put(url, json={"hour": 7}).json() == {"hour": 7}
    db.refresh(user)
    assert user.preferences["briefing_hour"] == 7
    assert client.put(url, json={"hour": None}).json() == {"hour": None}
    db.refresh(user)
    assert user.preferences["briefing_hour"] is None
    assert client.put(url, json={"hour": 24}).status_code == 422


def test_the_scheduler_run_reports_briefings(db, user, client, monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "test-secret")
    monkeypatch.setattr(push_service, "default_sender", Recorder())

    body = client.post("/api/internal/reminders/dispatch", headers={"X-Cron-Secret": "test-secret"}).json()

    assert body["briefings"] == 0 and "pushed" in body
