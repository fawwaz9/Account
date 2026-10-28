"""The acting user a database session runs as, and the few lookups that cross users.

`act_as` records the user on the session, and a listener writes it into the
transaction-local setting `app.user_id` at the start of every transaction; the row
policies in `rls.py` read that setting through `account_current_user()`. The
cross-user lookups (sign-in by email or Google id, the email-taken check, the purge
and push scheduler queries) call `SECURITY DEFINER` functions on Postgres and run
the same query directly on SQLite, which has no row security.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import event, func, text
from sqlalchemy.orm import Session

from app._database.models import PushSubscriptionModel, ReminderModel, UserModel

#: The transaction-local setting the row policies read.
SETTING = "app.user_id"
_INFO_KEY = "acting_user_id"
"""Key under which `act_as` stores the acting user in `Session.info`."""


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


def act_as(db: Session, user_id: UUID) -> None:
    """Make the session act as a user for the current and every later transaction.

    Args:
        db: The session to identify.
        user_id: The acting user; row policies admit only that user's rows.

    Note:
        The setting is transaction-local (`set_config(..., true)`) and re-applied by
        `_carry_identity` at every transaction start, because services commit
        mid-request
        and the transaction pooler may hand each transaction a different connection.
    """
    db.info[_INFO_KEY] = user_id
    if db.in_transaction() and _is_postgres(db):
        db.execute(text("SELECT set_config(:name, :value, true)"),
                   {"name": SETTING, "value": str(user_id)})


def acting_user(db: Session) -> UUID | None:
    """Return the user the session acts as.

    Args:
        db: The session to inspect.

    Returns:
        The id passed to the last `act_as`, or None if it was never called.
    """
    return db.info.get(_INFO_KEY)


@event.listens_for(Session, "after_begin")
def _carry_identity(session: Session, _transaction, connection) -> None:
    """Write the acting user into `app.user_id` as each Postgres transaction begins."""
    user_id = session.info.get(_INFO_KEY)
    if user_id is not None and connection.dialect.name == "postgresql":
        connection.execute(text("SELECT set_config(:name, :value, true)"),
                           {"name": SETTING, "value": str(user_id)})


# --------------------------------------------------------------------------
# The cross-user questions. Each answers with an id or a boolean.
# --------------------------------------------------------------------------

def user_id_by_email(db: Session, email: str) -> UUID | None:
    """Return the id of the account registered to an email address, ignoring case.

    Args:
        db: Open database session; needs no acting user.
        email: Address to look up, compared by exact case-insensitive equality, never as
            a
            pattern.

    Returns:
        The account's id, or None when no account has the address.
    """
    if _is_postgres(db):
        return db.execute(text("SELECT account_user_id_by_email(:email)"), {"email": email}).scalar()
    return (
        db.query(UserModel.id)
        .filter(func.lower(UserModel.email) == email.lower())
        .scalar()
    )


def user_id_by_google_id(db: Session, google_id: str) -> UUID | None:
    """Return the id of the account linked to a Google subject.

    Args:
        db: Open database session; needs no acting user.
        google_id: Google's stable subject identifier for the person.

    Returns:
        The account's id, or None when no account is linked to it.
    """
    if _is_postgres(db):
        return db.execute(text("SELECT account_user_id_by_google_id(:gid)"), {"gid": google_id}).scalar()
    return db.query(UserModel.id).filter(UserModel.google_id == google_id).scalar()


def email_taken(db: Session, email: str, except_user_id: UUID | None = None) -> bool:
    """Return whether another account already uses an email address, ignoring case.

    Args:
        db: Open database session; needs no acting user.
        email: Address to check.
        except_user_id: Account to leave out, so a user keeping their own address
            passes;
            None checks every account.

    Returns:
        True if any other account has the address.
    """
    if _is_postgres(db):
        return bool(db.execute(
            text("SELECT account_email_taken(:email, :except_id)"),
            {"email": email, "except_id": except_user_id},
        ).scalar())
    query = db.query(UserModel.id).filter(func.lower(UserModel.email) == email.lower())
    if except_user_id is not None:
        query = query.filter(UserModel.id != except_user_id)
    return query.first() is not None


def expired_user_ids(db: Session, cutoff: datetime) -> list[UUID]:
    """Return the accounts whose deletion was requested on or before a cutoff.

    Args:
        db: Open database session; needs no acting user.
        cutoff: Naive UTC time; accounts with `deleted_at` at or before it are returned.

    Returns:
        The ids of the accounts due for purging; empty when there are none.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT account_expired_user_ids(:cutoff)"), {"cutoff": cutoff}).scalars()
        return list(rows)
    return [
        row.id for row in
        db.query(UserModel.id)
        .filter(UserModel.deleted_at.isnot(None), UserModel.deleted_at <= cutoff)
        .all()
    ]


def release_push_endpoint(db: Session, endpoint: str) -> None:
    """Delete the push subscription for an endpoint, whichever account holds it.

    Args:
        db: Open database session; the delete is not committed here.
        endpoint: The browser's push endpoint URL; knowing it is the proof of ownership.
    """
    if _is_postgres(db):
        db.execute(text("SELECT account_release_push_endpoint(:endpoint)"), {"endpoint": endpoint})
        return
    db.query(PushSubscriptionModel).filter(PushSubscriptionModel.endpoint == endpoint).delete(
        synchronize_session=False
    )


def users_with_unpushed_reminders(db: Session, horizon: datetime) -> list[UUID]:
    """Return the users with a device and an unpushed reminder due by a horizon.

    Args:
        db: Open database session; needs no acting user.
        horizon: Latest naive `remind_at` to include. Because `remind_at` is local wall
            time, callers pass a horizon wide enough for every time zone and recheck
            each
            user's own clock.

    Returns:
        Distinct user ids; empty when nobody has anything waiting.
    """
    if _is_postgres(db):
        rows = db.execute(
            text("SELECT account_users_with_unpushed_reminders(:horizon)"), {"horizon": horizon}
        ).scalars()
        return list(rows)
    has_device = db.query(PushSubscriptionModel.id).filter(
        PushSubscriptionModel.user_id == ReminderModel.user_id
    ).exists()
    return [
        row.user_id for row in
        db.query(ReminderModel.user_id)
        .filter(
            ReminderModel.dismissed_at.is_(None),
            ReminderModel.pushed_at.is_(None),
            ReminderModel.remind_at <= horizon,
            has_device,
        )
        .distinct()
        .all()
    ]
