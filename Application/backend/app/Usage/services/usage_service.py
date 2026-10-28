"""Counting module use: one counter per user, day, kind and module.

Visits come from the client, once per module per day per tab; creates are recorded by
the create routes after their own commit. Recording never breaks what it records: it
runs in its own savepoint and swallows its failures.
"""
import logging
import uuid

from sqlalchemy.orm import Session

from app._database.models import UsageEventModel, utc_now
from app.shared.dates import user_today

logger = logging.getLogger("app.usage")

VISIT = "visit"
"""A page of the module was opened."""
#: A visit that began from a push notification. Kept as its own kind rather
#: than a flag so the per-day counter stays one row per kind, and so an
#: unprompted visit later the same day is still counted as one.
PROMPTED_VISIT = "prompted_visit"
CREATE = "create"
"""Something was added in the module."""


def record(db: Session, user_id: uuid.UUID, kind: str, module: str) -> None:
    """Count one use of a module for the user's local today; never raises.

    Args:
        db: The request's session, with the action already committed.
        user_id: The user.
        kind: `VISIT`, `PROMPTED_VISIT` or `CREATE`.
        module: The module name, such as "grades".

    Note:
        Skipped, with a warning, when the session holds unsaved changes, so it never
        commits or rolls back the caller's work. Commits its own change; any failure is
        logged and rolled back.
    """
    if db.new or db.dirty or db.deleted:
        # Something unsaved is in the session. Recording now would either
        # commit it as a side effect or, on failure, roll it back -- both the
        # caller's business, not this function's. Skipping costs one count.
        logger.warning("usage not recorded: session has unsaved changes (%s %s)", kind, module)
        return
    try:
        with db.begin_nested():
            now = utc_now()
            day = user_today(db, user_id)
            row = (
                db.query(UsageEventModel)
                .filter(
                    UsageEventModel.user_id == user_id,
                    UsageEventModel.day == day,
                    UsageEventModel.kind == kind,
                    UsageEventModel.module == module,
                )
                .first()
            )
            if row is None:
                db.add(UsageEventModel(
                    id=uuid.uuid4(), user_id=user_id, day=day, kind=kind, module=module,
                    count=1, first_at=now, last_at=now,
                ))
            else:
                row.count += 1
                row.last_at = now
        db.commit()
    except Exception:  # noqa: BLE001 - see the module docstring
        db.rollback()
        logger.warning("usage not recorded (%s %s)", kind, module, exc_info=True)
