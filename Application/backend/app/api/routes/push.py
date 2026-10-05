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
    TestResult,
)
from app.Notifications.services import push_service

router = APIRouter()
internal = APIRouter()


@router.get("/{user_id}/status", response_model=PushStatus)
def push_status(user_id: VerifiedUserId, db: DBSession):
    keys = push_service.vapid()
    return PushStatus(
        available=keys is not None,
        public_key=keys.public_key if keys else None,
        devices=push_service.devices(db, user_id),
    )


@router.post("/{user_id}/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def add_subscription(user_id: VerifiedUserId, subscription: SubscriptionCreate, db: DBSession):
    push_service.subscribe(db, user_id, subscription)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/subscriptions/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_subscription(user_id: VerifiedUserId, subscription: SubscriptionRemove, db: DBSession):
    push_service.unsubscribe(db, user_id, subscription.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/test", response_model=TestResult)
def send_test(user_id: VerifiedUserId, db: DBSession):
    sent = push_service.send_test(db, user_id)
    if sent is None:
        raise HTTPException(status_code=503, detail="Notifications are not set up on the server yet")
    return TestResult(sent=sent)


@internal.post("/reminders/dispatch", response_model=DispatchResult)
def dispatch(db: DBSession, x_cron_secret: str | None = Header(default=None)):
    """Called by the scheduler every few minutes; by nobody else.

    Does not exist without CRON_SECRET configured (404, so an unconfigured
    server does not even reveal the route), and refuses any other caller with
    403. The comparison is constant-time.
    """
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status_code=403, detail="Not authorized")
    return DispatchResult(**push_service.dispatch_due_reminders(db))
