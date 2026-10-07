"""The cross-user steps of sharing (Phase 2 item 10, D22), in one place.

Like ``identity.py``: on Postgres each is a ``SECURITY DEFINER`` function
(``rls.FUNCTION_SQL``) answering with a name, a status word or three numbers,
never rows; on SQLite, which has no row security, the same question is asked
with a plain query written to mean exactly what the function means. The
Postgres half is proven in tests/test_rls.py; the SQLite half by the partner
tests, which run on both.

Every one of these takes the caller's id from the session's identity on
Postgres (``account_current_user()``), and from the ``user_id`` argument on
SQLite. The routes pass the verified id, so the two agree.
"""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import InviteModel, PartnershipModel, UserModel, utc_now


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


@dataclass(frozen=True)
class InvitePreview:
    inviter_name: str
    kind: str


@dataclass(frozen=True)
class PartnerFigure:
    partner_id: uuid.UUID
    week_percent: float | None
    streak_weeks: int
    figure_on: date | None


def _live_invite(db: Session, token_hash: str):
    now = utc_now()
    return (
        db.query(InviteModel)
        .filter(InviteModel.token_hash == token_hash, InviteModel.used_at.is_(None),
                InviteModel.revoked_at.is_(None), InviteModel.expires_at > now)
        .first()
    )


def invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> InvitePreview | None:
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_invite_preview(:h)"), {"h": token_hash}).first()
        return InvitePreview(row.inviter_name, row.kind) if row else None
    invite = _live_invite(db, token_hash)
    if invite is None:
        return None
    inviter = db.get(UserModel, invite.user_id)
    if inviter is None or inviter.deleted_at is not None:
        return None
    return InvitePreview(inviter.name, invite.kind)


def accept_partner_invite(db: Session, user_id: uuid.UUID, token_hash: str) -> str:
    """'accepted', 'invalid' (unknown, expired, used or revoked), 'own' or 'already'."""
    if _is_postgres(db):
        status = db.execute(text("SELECT account_accept_partner_invite(:h)"), {"h": token_hash}).scalar()
        db.commit()
        return status
    invite = _live_invite(db, token_hash)
    if invite is None or invite.kind != "partner":
        return "invalid"
    if invite.user_id == user_id:
        return "own"
    me, them = db.get(UserModel, user_id), db.get(UserModel, invite.user_id)
    if me is None or them is None or me.deleted_at is not None or them.deleted_at is not None:
        return "invalid"
    exists = db.query(PartnershipModel).filter_by(user_id=user_id, partner_id=invite.user_id).first()
    if exists is not None:
        return "already"
    now = utc_now()
    db.add_all([
        PartnershipModel(id=uuid.uuid4(), user_id=user_id, partner_id=them.id, partner_name=them.name,
                         created_at=now, streak_weeks=0),
        PartnershipModel(id=uuid.uuid4(), user_id=them.id, partner_id=user_id, partner_name=me.name,
                         created_at=now, streak_weeks=0),
    ])
    invite.used_at, invite.used_by = now, user_id
    db.commit()
    return "accepted"


def end_partnership(db: Session, user_id: uuid.UUID, partner_id: uuid.UUID) -> bool:
    if _is_postgres(db):
        ended = bool(db.execute(text("SELECT account_end_partnership(:p)"), {"p": partner_id}).scalar())
        db.commit()
        return ended
    gone = db.query(PartnershipModel).filter(
        ((PartnershipModel.user_id == user_id) & (PartnershipModel.partner_id == partner_id))
        | ((PartnershipModel.user_id == partner_id) & (PartnershipModel.partner_id == user_id))
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0


def partner_figures(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, PartnerFigure]:
    """Each partner's own figure, only where both rows point at each other."""
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_partner_figures()")).all()
    else:
        mine = {row.partner_id for row in db.query(PartnershipModel).filter_by(user_id=user_id)}
        rows = [
            row for row in db.query(PartnershipModel).filter(PartnershipModel.partner_id == user_id)
            if row.user_id in mine
        ]
        rows = [type("R", (), {"partner_id": r.user_id, "week_percent": r.week_percent,
                               "streak_weeks": r.streak_weeks, "figure_on": r.figure_on}) for r in rows]
    return {
        row.partner_id: PartnerFigure(row.partner_id, row.week_percent, row.streak_weeks or 0, row.figure_on)
        for row in rows
    }
