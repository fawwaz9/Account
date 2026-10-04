"""Who a database session is acting for -- the identity row policies check.

Phase 0 moves the per-user rule from application code into Postgres: every
per-user table gets a row policy admitting only rows whose owner is the user
named in the transaction-local setting ``app.user_id``. A query that forgets
its ``user_id`` filter then returns that user's rows anyway, instead of
everyone's. See ``app/_database/rls.py`` for the policies and
``Ideas/overhaul/phase0.md`` item 2 for why.

This module is the application half:

* ``act_as(db, user_id)`` records the identity on the session. A listener puts
  it into ``app.user_id`` at the start of **every** transaction, because
  services commit mid-request and ``set_config(..., is_local => true)`` dies
  with each transaction. Local rather than session-wide on purpose: production
  runs behind Supabase's transaction pooler, where consecutive transactions can
  land on different server connections, and a session-wide setting would leak
  one request's identity into another's.

* A handful of lookups that genuinely have to look across users -- signing in
  by email, the "is this address taken" check, finding accounts due for purge.
  On Postgres they go through ``SECURITY DEFINER`` functions that return an id
  or a yes/no, never rows; the caller then acts as that user. On SQLite (local
  development and the default test run) there are no policies, and the same
  questions are asked with a plain query.

Everything here is inert until the policies exist and the API connects as the
restricted role: setting ``app.user_id`` on a database with no policies changes
nothing, which is what lets this ship ahead of the switch.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import event, func, text
from sqlalchemy.orm import Session

from app._database.models import UserModel

#: The transaction-local setting the row policies read.
SETTING = "app.user_id"
_INFO_KEY = "acting_user_id"


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def act_as(db: Session, user_id: UUID) -> None:
    """From now on, this session acts for ``user_id``.

    Takes effect for the transaction in progress, if there is one, and for every
    transaction after it.
    """
    db.info[_INFO_KEY] = user_id
    if db.in_transaction() and _is_postgres(db):
        db.execute(text("SELECT set_config(:name, :value, true)"),
                   {"name": SETTING, "value": str(user_id)})


def acting_user(db: Session) -> UUID | None:
    return db.info.get(_INFO_KEY)


@event.listens_for(Session, "after_begin")
def _carry_identity(session: Session, _transaction, connection) -> None:
    user_id = session.info.get(_INFO_KEY)
    if user_id is not None and connection.dialect.name == "postgresql":
        connection.execute(text("SELECT set_config(:name, :value, true)"),
                           {"name": SETTING, "value": str(user_id)})


# --------------------------------------------------------------------------
# The cross-user questions. Each answers with an id or a boolean.
# --------------------------------------------------------------------------

def user_id_by_email(db: Session, email: str) -> UUID | None:
    """The account registered to ``email``, compared without regard to case.

    Exact equality, not ILIKE: in a LIKE pattern ``_`` and ``%`` are wildcards,
    and email addresses contain underscores, so john_doe@ matched johnxdoe@.
    """
    if _is_postgres(db):
        return db.execute(text("SELECT account_user_id_by_email(:email)"), {"email": email}).scalar()
    return (
        db.query(UserModel.id)
        .filter(func.lower(UserModel.email) == email.lower())
        .scalar()
    )


def user_id_by_google_id(db: Session, google_id: str) -> UUID | None:
    if _is_postgres(db):
        return db.execute(text("SELECT account_user_id_by_google_id(:gid)"), {"gid": google_id}).scalar()
    return db.query(UserModel.id).filter(UserModel.google_id == google_id).scalar()


def email_taken(db: Session, email: str, except_user_id: UUID | None = None) -> bool:
    """Whether an account other than ``except_user_id`` already has ``email``."""
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
    """Accounts marked for deletion on or before ``cutoff``."""
    if _is_postgres(db):
        rows = db.execute(text("SELECT account_expired_user_ids(:cutoff)"), {"cutoff": cutoff}).scalars()
        return list(rows)
    return [
        row.id for row in
        db.query(UserModel.id)
        .filter(UserModel.deleted_at.isnot(None), UserModel.deleted_at <= cutoff)
        .all()
    ]
