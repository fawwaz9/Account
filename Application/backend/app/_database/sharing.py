"""The cross-user steps of sharing (Phase 2 items 10 and 9a, D22 and D23), in one place.

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

from app._database.models import (
    MAX_TASK_MEMBERS, InviteModel, PartnershipModel, TaskInviteModel, TaskMemberModel, TaskModel, UserModel,
    utc_now,
)


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


# --------------------------------------------------------------------------
# Shared tasks (Phase 2 item 9a, D23)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskInvitePreview:
    owner_name: str
    title: str


@dataclass(frozen=True)
class SharedTask:
    """What a member may see of someone else's task, and nothing more."""
    task_id: uuid.UUID
    owner_name: str
    title: str
    notes: str | None
    due_date: date | None
    due_time: object | None
    done: bool
    completed_at: object | None
    member_names: list[str]


def _live_owner(db: Session, owner_id: uuid.UUID) -> UserModel | None:
    owner = db.get(UserModel, owner_id)
    return owner if owner is not None and owner.deleted_at is None else None


def _live_task_invite(db: Session, token_hash: str):
    return (
        db.query(TaskInviteModel)
        .filter(TaskInviteModel.token_hash == token_hash, TaskInviteModel.revoked_at.is_(None),
                TaskInviteModel.expires_at > utc_now())
        .first()
    )


def task_invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> TaskInvitePreview | None:
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_task_invite_preview(:h)"), {"h": token_hash}).first()
        return TaskInvitePreview(row.owner_name, row.title) if row else None
    invite = _live_task_invite(db, token_hash)
    task = db.get(TaskModel, invite.task_id) if invite else None
    if task is None or task.recurring_id is not None:
        return None
    owner = _live_owner(db, task.user_id)
    return TaskInvitePreview(owner.name, task.title) if owner else None


def accept_task_invite(db: Session, user_id: uuid.UUID, token_hash: str) -> str:
    """'accepted', 'invalid', 'own', 'already' or 'full'."""
    if _is_postgres(db):
        status = db.execute(text("SELECT account_accept_task_invite(:h)"), {"h": token_hash}).scalar()
        db.commit()
        return status
    invite = _live_task_invite(db, token_hash)
    task = db.get(TaskModel, invite.task_id) if invite else None
    if task is None or task.recurring_id is not None:
        return "invalid"
    if task.user_id == user_id:
        return "own"
    me, owner = _live_owner(db, user_id), _live_owner(db, task.user_id)
    if me is None or owner is None:
        return "invalid"
    members = db.query(TaskMemberModel).filter(TaskMemberModel.task_id == task.id)
    if members.filter(TaskMemberModel.member_id == user_id).first() is not None:
        return "already"
    if members.count() >= MAX_TASK_MEMBERS:
        return "full"
    db.add(TaskMemberModel(id=uuid.uuid4(), task_id=task.id, member_id=user_id, member_name=me.name,
                           owner_name=owner.name, joined_at=utc_now()))
    db.commit()
    return "accepted"


def _member_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskModel | None:
    """SQLite's stand-in for the functions' shared WHERE: a one-off task of a
    live owner, that the caller is a member of."""
    task = db.get(TaskModel, task_id)
    if task is None or task.recurring_id is not None or _live_owner(db, task.user_id) is None:
        return None
    member = db.query(TaskMemberModel).filter_by(task_id=task_id, member_id=user_id).first()
    return task if member is not None else None


def shared_tasks(db: Session, user_id: uuid.UUID) -> list[SharedTask]:
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_shared_tasks()")).all()
        return [SharedTask(r.task_id, r.owner_name, r.title, r.notes, r.due_date, r.due_time, r.done,
                           r.completed_at, list(r.member_names or [])) for r in rows]
    out = []
    for membership in db.query(TaskMemberModel).filter(TaskMemberModel.member_id == user_id):
        task = _member_task(db, user_id, membership.task_id)
        if task is None:
            continue
        names = [m.member_name for m in sorted(
            db.query(TaskMemberModel).filter(TaskMemberModel.task_id == task.id),
            key=lambda m: (m.joined_at, m.member_name))]
        out.append(SharedTask(task.id, membership.owner_name, task.title, task.notes, task.due_date,
                              task.due_time, task.done, task.completed_at, names))
    return out


def set_shared_task_done(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, done: bool) -> bool:
    if _is_postgres(db):
        changed = bool(db.execute(text("SELECT account_set_shared_task_done(:t, :d)"),
                                  {"t": task_id, "d": done}).scalar())
        db.commit()
        return changed
    task = _member_task(db, user_id, task_id)
    if task is None:
        return False
    task.done = done
    task.completed_at = utc_now() if done else None
    task.archived = done
    db.commit()
    return True


def edit_shared_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, title: str, notes: str | None) -> bool:
    if _is_postgres(db):
        changed = bool(db.execute(text("SELECT account_edit_shared_task(:t, :title, :notes)"),
                                  {"t": task_id, "title": title, "notes": notes}).scalar())
        db.commit()
        return changed
    task = _member_task(db, user_id, task_id)
    title = (title or "").strip()
    if task is None or not 1 <= len(title) <= 200 or (notes is not None and len(notes) > 2000):
        return False
    task.title, task.notes = title, notes
    db.commit()
    return True


def leave_shared_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
    if _is_postgres(db):
        left = bool(db.execute(text("SELECT account_leave_shared_task(:t)"), {"t": task_id}).scalar())
        db.commit()
        return left
    gone = db.query(TaskMemberModel).filter(
        TaskMemberModel.task_id == task_id, TaskMemberModel.member_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0
