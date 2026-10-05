"""Push notifications: devices, the scheduler, and who receives what.

Phase 0 item 5. The case that matters most is the last in this file: a
reminder only ever reaches its owner's own devices, even when two people's
reminders fall due in the same scheduler run.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import PushSubscriptionModel, ReminderModel
from app.Auth.dependencies import get_current_user
from app.config import settings
from app.Notifications.schemas.push import SubscriptionCreate, SubscriptionKeys
from app.Notifications.services import push_service
from app.Notifications.services.push_service import dispatch_due_reminders, subscribe
from app.Notifications.services.webpush import b64url_encode, generate_keys
from conftest import make_user

# A real P-256 point, so encryption to it works; the device is fictional.
UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
# Noon UTC on a weekday: 06:00 in the fixture user's zone (America/Regina, UTC-6).
NOON_UTC = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def vapid_configured(monkeypatch):
    private, _ = generate_keys()
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", private)


def device(db, user, name="phone"):
    subscribe(db, user.id, SubscriptionCreate(
        endpoint=f"https://push.invalid/{user.email}/{name}",
        keys=SubscriptionKeys(p256dh=UA_PUBLIC, auth=AUTH),
    ))
    return f"https://push.invalid/{user.email}/{name}"


def reminder(db, user, title, local_time):
    row = ReminderModel(id=uuid.uuid4(), user_id=user.id, title=title, remind_at=local_time)
    db.add(row)
    db.commit()
    return row


class Recorder:
    def __init__(self, status=201):
        self.sent, self.status = [], status

    def __call__(self, endpoint, headers, body):
        self.sent.append(endpoint)
        return self.status(endpoint) if callable(self.status) else self.status


def test_a_due_reminder_is_pushed_once(db, user):
    phone = device(db, user)
    row = reminder(db, user, "Lab report", datetime(2026, 10, 7, 5, 30))  # local, before 06:00
    send = Recorder()

    first = dispatch_due_reminders(db, send, at=NOON_UTC)
    second = dispatch_due_reminders(db, send, at=NOON_UTC + timedelta(minutes=5))

    assert first == {"users": 1, "pushed": 1, "removed": 0}
    assert second["pushed"] == 0
    assert send.sent == [phone]
    db.refresh(row)
    assert row.pushed_at is not None


def test_not_before_its_time_on_the_students_own_clock(db, user):
    """08:00 local is 14:00 UTC; at noon UTC it is not due yet."""
    device(db, user)
    reminder(db, user, "Later", datetime(2026, 10, 7, 8, 0))
    assert dispatch_due_reminders(db, Recorder(), at=NOON_UTC)["pushed"] == 0
    assert dispatch_due_reminders(db, Recorder(), at=NOON_UTC + timedelta(hours=2))["pushed"] == 1


def test_a_reminder_hours_stale_is_not_an_interruption(db, user):
    device(db, user)
    reminder(db, user, "Yesterday", datetime(2026, 10, 6, 9, 0))
    assert dispatch_due_reminders(db, Recorder(), at=NOON_UTC)["pushed"] == 0


def test_dismissed_reminders_are_left_alone(db, user):
    device(db, user)
    row = reminder(db, user, "Done with", datetime(2026, 10, 7, 5, 0))
    row.dismissed_at = datetime(2026, 10, 7, 5, 1)
    db.commit()
    assert dispatch_due_reminders(db, Recorder(), at=NOON_UTC)["pushed"] == 0


def test_a_failed_send_is_retried_next_run(db, user):
    device(db, user)
    row = reminder(db, user, "Retry", datetime(2026, 10, 7, 5, 30))
    assert dispatch_due_reminders(db, Recorder(status=None), at=NOON_UTC)["pushed"] == 0
    db.refresh(row)
    assert row.pushed_at is None
    assert dispatch_due_reminders(db, Recorder(), at=NOON_UTC)["pushed"] == 1


def test_a_device_the_push_service_calls_gone_is_forgotten(db, user):
    phone = device(db, user, "phone")
    laptop = device(db, user, "laptop")
    reminder(db, user, "Gone", datetime(2026, 10, 7, 5, 30))
    send = Recorder(status=lambda endpoint: 410 if endpoint == phone else 201)

    result = dispatch_due_reminders(db, send, at=NOON_UTC)

    assert result == {"users": 1, "pushed": 1, "removed": 1}
    left = [s.endpoint for s in db.query(PushSubscriptionModel).all()]
    assert left == [laptop]


def test_nothing_is_sent_without_the_servers_key(db, user, monkeypatch):
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", None)
    device(db, user)
    reminder(db, user, "No keys", datetime(2026, 10, 7, 5, 30))
    send = Recorder()
    assert dispatch_due_reminders(db, send, at=NOON_UTC)["pushed"] == 0
    assert send.sent == []


def test_a_browser_moves_to_whoever_turned_it_on_last(db, user):
    """Two people, one shared laptop: it stops receiving the first one's reminders."""
    other = make_user(db, "other@example.com")
    endpoint = "https://push.invalid/shared-laptop"
    keys = SubscriptionKeys(p256dh=UA_PUBLIC, auth=AUTH)
    subscribe(db, user.id, SubscriptionCreate(endpoint=endpoint, keys=keys))
    subscribe(db, other.id, SubscriptionCreate(endpoint=endpoint, keys=keys))

    rows = db.query(PushSubscriptionModel).all()
    assert [(r.user_id, r.endpoint) for r in rows] == [(other.id, endpoint)]


def test_a_reminder_only_ever_reaches_its_owners_devices(db, user):
    other = make_user(db, "other@example.com")
    mine = device(db, user)
    theirs = device(db, other)
    reminder(db, user, "zzmine private", datetime(2026, 10, 7, 5, 30))
    reminder(db, other, "zztheirs private", datetime(2026, 10, 7, 5, 30))
    deliveries = []

    def capture(endpoint, headers, body):
        deliveries.append(endpoint)
        return 201

    result = dispatch_due_reminders(db, capture, at=NOON_UTC)

    assert result["pushed"] == 2
    assert sorted(deliveries) == sorted([mine, theirs])
    assert deliveries.count(mine) == 1 and deliveries.count(theirs) == 1


# ------------------------------------------------------------------ routes --

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_status_says_whether_push_is_set_up(user, client, monkeypatch):
    body = client.get(f"/api/push/{user.id}/status").json()
    assert body["available"] is True and body["public_key"] and body["devices"] == 0
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", None)
    assert client.get(f"/api/push/{user.id}/status").json()["available"] is False


def test_turning_a_device_on_and_off(db, user, client):
    sub = {"endpoint": "https://push.invalid/me/phone", "keys": {"p256dh": UA_PUBLIC, "auth": AUTH}}
    assert client.post(f"/api/push/{user.id}/subscriptions", json=sub).status_code == 204
    assert client.get(f"/api/push/{user.id}/status").json()["devices"] == 1
    assert client.post(f"/api/push/{user.id}/subscriptions/remove",
                       json={"endpoint": sub["endpoint"]}).status_code == 204
    assert client.get(f"/api/push/{user.id}/status").json()["devices"] == 0


def test_only_https_endpoints_are_accepted(user, client):
    """The server POSTs to this address; it may not be pointed anywhere else."""
    for bad in ("http://push.invalid/x", "file:///etc/passwd", "https"):
        response = client.post(f"/api/push/{user.id}/subscriptions",
                               json={"endpoint": bad, "keys": {"p256dh": UA_PUBLIC, "auth": AUTH}})
        assert response.status_code == 422, bad


def test_the_test_button(db, user, client, _no_push_network):
    device(db, user)
    assert client.post(f"/api/push/{user.id}/test").json() == {"sent": 1}
    assert [endpoint for endpoint, _h, _b in _no_push_network] == [f"https://push.invalid/{user.email}/phone"]


def test_a_test_goes_only_to_the_device_that_asked(db, user, client, _no_push_network):
    """Pressed on the laptop, it arrives on the laptop -- not the phone too."""
    device(db, user, "phone")
    laptop = device(db, user, "laptop")
    assert client.post(f"/api/push/{user.id}/test", json={"endpoint": laptop}).json() == {"sent": 1}
    assert [endpoint for endpoint, _h, _b in _no_push_network] == [laptop]


def test_a_test_cannot_be_aimed_at_another_users_device(db, user, client, _no_push_network):
    other = make_user(db, email="other@example.com")
    theirs = device(db, other, "phone")
    assert client.post(f"/api/push/{user.id}/test", json={"endpoint": theirs}).json() == {"sent": 0}
    assert _no_push_network == []


def test_the_scheduler_door(db, user, monkeypatch):
    route = "/api/internal/reminders/dispatch"
    plain = TestClient(app.main.app)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        assert plain.post(route).status_code == 404  # no secret configured: no route
        monkeypatch.setattr(settings, "CRON_SECRET", "s" * 40)
        assert plain.post(route).status_code == 403
        assert plain.post(route, headers={"X-Cron-Secret": "wrong" * 8}).status_code == 403
        ok = plain.post(route, headers={"X-Cron-Secret": "s" * 40})
        assert ok.status_code == 200 and set(ok.json()) == {"users", "pushed", "removed"}
    finally:
        app.main.app.dependency_overrides.clear()


def test_a_device_with_unusable_keys_does_not_stop_the_run(db, user):
    """One bad row is forgotten; everyone after it still gets their reminders."""
    other = make_user(db, "other@example.com")
    db.add(PushSubscriptionModel(id=uuid.uuid4(), user_id=user.id, endpoint="https://push.invalid/broken",
                                 p256dh="B" + "A" * 86, auth=AUTH))
    db.commit()
    good = device(db, other)
    reminder(db, user, "mine", datetime(2026, 10, 7, 5, 30))
    reminder(db, other, "theirs", datetime(2026, 10, 7, 5, 30))
    send = Recorder()

    result = dispatch_due_reminders(db, send, at=NOON_UTC)

    assert send.sent == [good]
    assert result["removed"] == 1 and result["pushed"] == 1


def test_a_key_that_is_not_a_curve_point_is_refused(user, client):
    response = client.post(f"/api/push/{user.id}/subscriptions", json={
        "endpoint": "https://push.invalid/x", "keys": {"p256dh": "B" + "A" * 86, "auth": AUTH}})
    assert response.status_code == 422
