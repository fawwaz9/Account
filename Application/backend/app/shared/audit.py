"""Audit log lines for authentication attempts and irreversible deletes.

Both write one space-separated line to the `app.audit` logger: every sign-in,
registration and password attempt with its outcome, and every delete of user data.
Passwords, hashes and tokens are never logged; email addresses are, on
authentication events, so the log needs the same care as the database.
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
    """Log one authentication attempt and how it went.

    Args:
        event: What was tried, such as "login", "register" or "google".
        outcome: "success", or the failure kind such as "invalid_credentials" or
            "throttled"; anything but "success" logs at WARNING, success at INFO.
        email: Address the attempt named, if any.
        user_id: Account involved, once known.
        client: The caller's address, from `client_of`.
        detail: Extra context, such as a verification error's message.
    """
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
    """Log that something irreversible was deleted, at INFO.

    Args:
        entity: What kind of thing was deleted, such as "task" or "course".
        user_id: Whose data it was.
        target_id: Id of the deleted row.
        detail: Extra context, such as the deleted item's title.
    """
    parts = [f"delete.{entity}", f"user={user_id}", f"target={target_id}"]
    if detail:
        parts.append(f"detail={detail}")
    logger.info(" ".join(parts))
