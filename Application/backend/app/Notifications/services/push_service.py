"""Push notifications: the user's devices, and delivering due reminders to them.

A scheduler calls `dispatch_due_reminders` every few minutes. Its only cross-user
step is the list of users with something waiting; everything after runs acting as
one user at a time, so a reminder can only reach its owner's devices. A reminder is
marked pushed once any device accepts it, retried until 12 hours past its time, and
a device the push service reports gone (404 or 410) is deleted.
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
"""A push sender: (endpoint, headers, body) to an HTTP status, or None if unsent."""


def default_sender(endpoint: str, headers: dict, body: bytes) -> int | None:
    """POST one encrypted push; return the HTTP status, or None if unsent.

    Waits up to 10 seconds; a failure is logged with the push service's host only.

    Args:
        endpoint: The device's push service URL.
        headers: Encryption and VAPID headers.
        body: The encrypted payload.

    Returns:
        The response status, or None when the request failed.
    """
    import requests  # local: only the dispatch path needs it

    try:
        return requests.post(endpoint, headers=headers, data=body, timeout=10).status_code
    except requests.RequestException as exc:
        logger.warning("push to %s failed: %s", endpoint.split("/")[2], exc)
        return None


def vapid() -> Vapid | None:
    """Return the server's VAPID identity, or None when push is not set up.

    Returns:
        The identity built from `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT`, or None.
    """
    if not settings.VAPID_PRIVATE_KEY:
        return None
    return Vapid.from_settings(settings.VAPID_PRIVATE_KEY, settings.VAPID_SUBJECT)


def devices(db: Session, user_id: uuid.UUID) -> int:
    """Return how many browsers the user has turned notifications on for.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        The number of stored push subscriptions.
    """
    return db.query(PushSubscriptionModel).filter(PushSubscriptionModel.user_id == user_id).count()


def subscribe(db: Session, user_id: uuid.UUID, data: SubscriptionCreate) -> None:
    """Turn notifications on for one browser, for this user.

    An endpoint the user already has gets its keys updated; one registered to anyone
    else is released from them first, since the browser now belongs to this user.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The browser's endpoint and keys.

    Note:
        Commits.
    """
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
    """Turn notifications off for one of the user's browsers.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        endpoint: The browser's push endpoint; anyone else's is left alone.

    Note:
        Commits.
    """
    db.query(PushSubscriptionModel).filter(
        PushSubscriptionModel.user_id == user_id, PushSubscriptionModel.endpoint == endpoint,
    ).delete(synchronize_session=False)
    db.commit()


def deliver(
    db: Session, user_id: uuid.UUID, payload: dict, keys: Vapid, sender: Sender,
    endpoint: str | None = None,
) -> tuple[int, int]:
    """Send a payload to each of a user's devices, or to one of them.

    Devices whose keys cannot be encrypted to, or that the push service reports gone,
    are deleted; accepted deliveries stamp `last_sent_at`.

    Args:
        db: Session acting as the user.
        user_id: Whose devices.
        payload: The notification as a JSON-serialisable dict.
        keys: The server's VAPID identity.
        sender: Callable that POSTs one push and returns its status, or None.
        endpoint: Limit delivery to this device, if it is the user's; None sends to all.

    Returns:
        (devices that accepted it, devices removed).

    Note:
        Commits.
    """
    body = json.dumps(payload).encode()
    accepted = removed = 0
    query = db.query(PushSubscriptionModel).filter(PushSubscriptionModel.user_id == user_id)
    if endpoint is not None:
        query = query.filter(PushSubscriptionModel.endpoint == endpoint)
    subscriptions = query.all()
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


def send_test(
    db: Session, user_id: uuid.UUID, endpoint: str | None = None, sender: Sender | None = None,
) -> int | None:
    """Send a test notification to the asking device, or to all of the user's.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        endpoint: The asking device's endpoint; None sends to every device.
        sender: Stand-in for the network in tests.

    Returns:
        How many devices accepted it, or None when push is not set up.
    """
    keys = vapid()
    if keys is None:
        return None
    accepted, _ = deliver(db, user_id, {
        "title": "Notifications are on",
        "body": "Reminders will reach this device even with the app closed.",
        "url": "/tasks",
    }, keys, sender or default_sender, endpoint)
    return accepted


def _payload(reminder: ReminderModel, course_code: str | None) -> dict:
    """Return the notification for a reminder: its title, its course code, and a tag."""
    return {
        "title": reminder.title,
        "body": course_code or "Reminder",
        "url": "/tasks",
        # The same tag replaces rather than stacks, should it ever arrive twice.
        "tag": f"reminder-{reminder.id}",
    }


def dispatch_due_reminders(db: Session, sender: Sender | None = None, at: datetime | None = None) -> dict:
    """Push every due, unpushed reminder to its owner's devices.

    `remind_at` is local wall time, so candidates are found up to 14 hours ahead of UTC
    and each user's own clock then decides what is due; reminders more than 12 hours
    past their time are no longer pushed.

    Args:
        db: A session of its own; it is made to act as each user in turn.
        sender: Stand-in for the network in tests.
        at: The moment to dispatch for, for tests; defaults to now.

    Returns:
        {"users", "pushed", "removed"}: users with something due, reminders delivered,
        and devices deleted; all 0 when push is not set up.

    Note:
        Idempotent: a reminder is pushed at most once; commits once per user.
    """
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
