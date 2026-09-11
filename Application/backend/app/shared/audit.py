"""A record of who authenticated and what got destroyed.

The app had no logging of any kind -- no access log, no failed-authentication
log, nothing recording who deleted which course. A breach left no trace to find
afterwards and there was nothing to alert on.

Two kinds of event are worth keeping, and nothing else yet:

* **Authentication** -- every attempt, successful or not, so a guessing run is
  visible after the fact rather than inferred.
* **Destruction** -- deletes, because they are the mutations that cannot be
  undone by looking at the current state.

Never log a password, a hash, or a token. Emails are logged on authentication
because an auth log that cannot say *which account* was attacked is not much use;
they are identifying data, so the log file deserves the same care as the database.
"""

import logging
from uuid import UUID

logger = logging.getLogger("app.audit")


def auth_event(
    event: str,
    *,
    outcome: str,
    email: str | None = None,
    user_id: UUID | None = None,
    client: str | None = None,
    detail: str | None = None,
) -> None:
    """One authentication attempt: `event` is what was tried, `outcome` how it went."""
    parts = [f"auth.{event}", f"outcome={outcome}"]
    if email:
        parts.append(f"email={email}")
    if user_id:
        parts.append(f"user={user_id}")
    if client:
        parts.append(f"client={client}")
    if detail:
        parts.append(f"detail={detail}")

    # A failure is the line someone will come looking for, so it gets a level
    # that survives a default log configuration.
    log = logger.warning if outcome != "success" else logger.info
    log(" ".join(parts))


def deletion(entity: str, *, user_id: UUID, target_id: object, detail: str | None = None) -> None:
    """Something irreversible was removed."""
    parts = [f"delete.{entity}", f"user={user_id}", f"target={target_id}"]
    if detail:
        parts.append(f"detail={detail}")
    logger.info(" ".join(parts))
