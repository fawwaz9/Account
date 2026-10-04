"""Recording that someone used a module today. Phase 0, item 4.

Two kinds, both counted per user per day per module:

* **visit** -- a page of the module was opened. Sent by the client, once per
  module per day per tab, because only the client knows which page is open: the
  dashboard alone reads grades, budget and calendar data, so counting API calls
  would say everyone visits every room every day.
* **create** -- something was added in it. Recorded by the create routes
  themselves, which is what makes time-to-first-value measurable.

**Recording never breaks the thing being recorded.** It runs after the action
has committed, inside its own savepoint, and swallows its own failures. A lost
counter is a rounding error in a report; a course that failed to save because a
counter did is a broken app.
"""
import logging
import uuid

from sqlalchemy.orm import Session

from app._database.models import UsageEventModel, utc_now
from app.shared.dates import user_today

logger = logging.getLogger("app.usage")

VISIT = "visit"
CREATE = "create"


def record(db: Session, user_id: uuid.UUID, kind: str, module: str) -> None:
    """Count one ``kind`` of use of ``module`` for today. Never raises."""
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
