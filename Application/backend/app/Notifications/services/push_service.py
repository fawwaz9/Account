"""Push notifications: devices, and delivering due reminders to them.

Phase 0 item 5. Until this, a reminder fired only while the app was open --
"a promise the app does not keep", in the vision's words. Now a scheduler calls
``dispatch_due_reminders`` every few minutes and each due reminder is pushed to
the devices its owner turned notifications on for.

**Isolation, as everywhere else.** The only cross-user step is finding *which*
users have something waiting (``identity.users_with_unpushed_reminders``, an id
list). Everything after it runs acting as one user at a time, so under row-level
security a user's reminders can only ever be read, and sent, to that user's own
devices. ``tests/test_push.py`` and ``tests/test_rls.py`` both check that a
reminder never reaches another person's device.

**Delivery rules**

* A reminder is marked ``pushed_at`` once at least one device accepted it.
  If none did because the network failed, it stays unpushed and the next run
  tries again -- but only for twelve hours after its time, after which a
  reminder is no longer worth an interruption.
* A device the push service reports gone (404 or 410) is deleted: the browser
  unsubscribed or the app was uninstalled, and it will never come back.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app._database.identity import act_as, release_push_endpoint, users_with_unpushed_reminders
from app._database.models import CourseModel, PushSubscriptionModel, ReminderModel, UserModel, utc_now
from app.config import settings
from app.Notifications.schemas.push import SubscriptionCreate
from app.Notifications.services.webpush import Vapid, request_for
from app.shared.dates import local_now

logger = logging.getLogger("app.push")

#: How long after its time a reminder is still worth pushing.
STALE_AFTER = timedelta(hours=12)
#: The furthest any time zone runs ahead of UTC (UTC+14). remind_at is local
#: wall time, so the candidate search must reach this far before each user's
#: own clock decides.
WIDEST_ZONE = timedelta(hours=14)

#: (endpoint, headers, body) -> HTTP status, or None if it could not be sent.
Sender = Callable[[str, dict, bytes], "int | None"]


def default_sender(endpoint: str, headers: dict, body: bytes) -> int | None:
    import requests  # local: only the dispatch path needs it

    try:
        return requests.post(endpoint, headers=headers, data=body, timeout=10).status_code
    except requests.RequestException as exc:
        logger.warning("push to %s failed: %s", endpoint.split("/")[2], exc)
        return None


def vapid() -> Vapid | None:
    if not settings.VAPID_PRIVATE_KEY:
        return None
    return Vapid.from_settings(settings.VAPID_PRIVATE_KEY, settings.VAPID_SUBJECT)


def devices(db: Session, user_id: uuid.UUID) -> int:
    return db.query(PushSubscriptionModel).filter(PushSubscriptionModel.user_id == user_id).count()


def subscribe(db: Session, user_id: uuid.UUID, data: SubscriptionCreate) -> None:
    """Turn notifications on for one browser, for this user."""
    own = (
        db.query(PushSubscriptionModel)
        .filter(PushSubscriptionModel.user_id == user_id, PushSubscriptionModel.endpoint == data.endpoint)
        .first()
    )
    if own is not None:
        own.p256dh, own.auth = data.keys.p256dh, data.keys.auth
        db.commit()
        return
    # The browser may still be registered to whoever used it before. It is
    # this person's browser now, so it stops receiving that person's reminders.
    release_push_endpoint(db, data.endpoint)
    db.add(PushSubscriptionModel(
        id=uuid.uuid4(), user_id=user_id, endpoint=data.endpoint,
        p256dh=data.keys.p256dh, auth=data.keys.auth,
    ))
    db.commit()


def unsubscribe(db: Session, user_id: uuid.UUID, endpoint: str) -> None:
    db.query(PushSubscriptionModel).filter(
        PushSubscriptionModel.user_id == user_id, PushSubscriptionModel.endpoint == endpoint,
    ).delete(synchronize_session=False)
    db.commit()


def deliver(db: Session, user_id: uuid.UUID, payload: dict, keys: Vapid, sender: Sender) -> tuple[int, int]:
    """Send ``payload`` to every device of ``user_id``. Returns (accepted, removed)."""
    body = json.dumps(payload).encode()
    accepted = removed = 0
    subscriptions = (
        db.query(PushSubscriptionModel).filter(PushSubscriptionModel.user_id == user_id).all()
    )
    for sub in subscriptions:
        try:
            headers, encrypted = request_for(sub.endpoint, sub.p256dh, sub.auth, body, keys)
        except (ValueError, TypeError):
            # Keys nothing can encrypt to: this device can never receive
            # anything, and one bad row must not stop the run for everyone
            # after it. Forgotten, like a device the push service calls gone.
            logger.warning("push subscription %s has unusable keys; removed", sub.id)
            db.delete(sub)
            removed += 1
            continue
        status = sender(sub.endpoint, headers, encrypted)
        if status in (404, 410):
            db.delete(sub)
            removed += 1
        elif status is not None and 200 <= status < 300:
            sub.last_sent_at = utc_now()
            accepted += 1
    db.commit()
    return accepted, removed


def send_test(db: Session, user_id: uuid.UUID, sender: Sender | None = None) -> int | None:
    """A notification to every device of this user. None when push is not set up."""
    keys = vapid()
    if keys is None:
        return None
    accepted, _ = deliver(db, user_id, {
        "title": "Notifications are on",
        "body": "Reminders will reach this device even with the app closed.",
        "url": "/tasks",
    }, keys, sender or default_sender)
    return accepted


def _payload(reminder: ReminderModel, course_code: str | None) -> dict:
    return {
        "title": reminder.title,
        "body": course_code or "Reminder",
        "url": "/tasks",
        # The same tag replaces rather than stacks, should it ever arrive twice.
        "tag": f"reminder-{reminder.id}",
    }


def dispatch_due_reminders(db: Session, sender: Sender | None = None, at: datetime | None = None) -> dict:
    """Push every due, unpushed reminder to its owner's devices. Idempotent."""
    keys = vapid()
    if keys is None:
        return {"users": 0, "pushed": 0, "removed": 0}
    send = sender or default_sender
    moment = at or datetime.now(timezone.utc)
    horizon = moment.replace(tzinfo=None) + WIDEST_ZONE

    pushed = removed = users = 0
    for user_id in users_with_unpushed_reminders(db, horizon):
        # From here on, everything this loop reads is this one user's.
        act_as(db, user_id)
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if user is None:
            continue
        now = local_now(user, moment)
        due = (
            db.query(ReminderModel)
            .filter(
                ReminderModel.user_id == user_id,
                ReminderModel.dismissed_at.is_(None),
                ReminderModel.pushed_at.is_(None),
                ReminderModel.remind_at <= now,
                ReminderModel.remind_at > now - STALE_AFTER,
            )
            .order_by(ReminderModel.remind_at)
            .all()
        )
        if not due:
            continue
        users += 1
        codes = {
            row.id: row.code for row in
            db.query(CourseModel.id, CourseModel.code).filter(CourseModel.user_id == user_id).all()
        }
        for reminder in due:
            accepted, gone = deliver(db, user_id, _payload(reminder, codes.get(reminder.course_id)), keys, send)
            removed += gone
            if accepted:
                reminder.pushed_at = utc_now()
                pushed += 1
        db.commit()
    return {"users": users, "pushed": pushed, "removed": removed}
