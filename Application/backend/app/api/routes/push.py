"""Push notification routes under `/api/push`, and the scheduler's reminder dispatch.

`internal` holds `POST /api/internal/reminders/dispatch`, which only the scheduler
may call.
"""

import hmac

from fastapi import APIRouter, Header, HTTPException, Response, status

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.config import settings
from app.Notifications.schemas.push import (
    DispatchResult,
    PushStatus,
    SubscriptionCreate,
    SubscriptionRemove,
    TestRequest,
    TestResult,
)
from app.Notifications.services import push_service

router = APIRouter()
internal = APIRouter()
"""Routes mounted under `/api/internal`, for the scheduler."""


@router.get("/{user_id}/status", response_model=PushStatus)
def push_status(user_id: VerifiedUserId, db: DBSession):
    """Return whether push works here, its public key, and the caller's devices.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        `available`, the VAPID `public_key` to subscribe with (null when unavailable),
        and the number of `devices`.
    """
    keys = push_service.vapid()
    return PushStatus(
        available=keys is not None,
        public_key=keys.public_key if keys else None,
        devices=push_service.devices(db, user_id),
    )


@router.post("/{user_id}/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def add_subscription(user_id: VerifiedUserId, subscription: SubscriptionCreate, db: DBSession):
    """Turn notifications on for this browser, taking it from any other account.

    Args:
        user_id: The verified caller's id.
        subscription: The browser's endpoint and keys.
        db: Request-scoped database session.

    Returns:
        204 No Content.
    """
    push_service.subscribe(db, user_id, subscription)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/subscriptions/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_subscription(user_id: VerifiedUserId, subscription: SubscriptionRemove, db: DBSession):
    """Turn notifications off for one of the caller's browsers.

    Args:
        user_id: The verified caller's id.
        subscription: The browser's endpoint.
        db: Request-scoped database session.

    Returns:
        204 No Content, whether or not it was subscribed.
    """
    push_service.unsubscribe(db, user_id, subscription.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/test", response_model=TestResult)
def send_test(user_id: VerifiedUserId, db: DBSession, request: TestRequest | None = None):
    """Send a test notification to the asking device, or to every device without a body.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        request: Optional body naming the asking device's endpoint.

    Returns:
        How many devices accepted it.

    Raises:
        HTTPException: 503 when push is not set up on the server.
    """
    sent = push_service.send_test(db, user_id, request.endpoint if request else None)
    if sent is None:
        raise HTTPException(status_code=503, detail="Notifications are not set up on the server yet")
    return TestResult(sent=sent)


@internal.post("/reminders/dispatch", response_model=DispatchResult)
def dispatch(db: DBSession, x_cron_secret: str | None = Header(default=None)):
    """Push every due reminder to its owner's devices; for the scheduler only.

    Args:
        db: Request-scoped database session; it acts as each user in turn.
        x_cron_secret: The `X-Cron-Secret` header, compared in constant time with
            `CRON_SECRET`.

    Returns:
        Users with something due, reminders pushed, and devices removed.

    Raises:
        HTTPException: 404 when `CRON_SECRET` is not configured; 403 when the header is
            missing or wrong.
    """
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status_code=403, detail="Not authorized")
    return DispatchResult(**push_service.dispatch_due_reminders(db))
