"""Shared tasks (Phase 2 item 9a, D23).

The owner's half reads and writes only the owner's own rows: their task, the
members hung under it, and its link -- all inside the ordinary row policy.
The member's half goes entirely through ``sharing``, whose functions are the
only way to reach a task someone else owns.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app._database import sharing
from app._database.models import (
    INVITE_DAYS, MAX_TASK_MEMBERS, TaskInviteModel, TaskMemberModel, TaskModel, utc_now,
)
from app.Tasks.schemas.sharing import (
    NewTaskLink, SharedTask, SharedTaskUpdate, TaskInvitePreview, TaskLink, TaskMember, TaskSharing,
)


class NotShareable(ValueError):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _own_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskModel | None:
    return db.query(TaskModel).filter(TaskModel.id == task_id, TaskModel.user_id == user_id).first()


def _live_links(db: Session, task_id: uuid.UUID):
    return db.query(TaskInviteModel).filter(
        TaskInviteModel.task_id == task_id, TaskInviteModel.revoked_at.is_(None),
        TaskInviteModel.expires_at > utc_now(),
    )


# ---------------------------------------------------------------- the owner --

def sharing_of(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskSharing | None:
    task = _own_task(db, user_id, task_id)
    if task is None:
        return None
    members = (
        db.query(TaskMemberModel).filter(TaskMemberModel.task_id == task.id)
        .order_by(TaskMemberModel.joined_at).all()
    )
    link = _live_links(db, task.id).order_by(TaskInviteModel.created_at.desc()).first()
    return TaskSharing(
        members=[TaskMember(id=m.id, name=m.member_name, joined_at=m.joined_at) for m in members],
        link=TaskLink(expires_at=link.expires_at) if link else None,
        shareable=task.recurring_id is None,
        max_members=MAX_TASK_MEMBERS,
    )


def new_link(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> NewTaskLink | None:
    """A fresh link, cancelling any live one: one link per task at a time."""
    task = _own_task(db, user_id, task_id)
    if task is None:
        return None
    if task.recurring_id is not None:
        raise NotShareable("A repeating task can't be shared. Share a one-off task instead.")
    now = utc_now()
    for old in _live_links(db, task.id):
        old.revoked_at = now
    token = secrets.token_urlsafe(24)
    link = TaskInviteModel(id=uuid.uuid4(), task_id=task.id, token_hash=token_hash(token),
                           created_at=now, expires_at=now + timedelta(days=INVITE_DAYS))
    db.add(link)
    db.commit()
    return NewTaskLink(token=token, expires_at=link.expires_at)


def cancel_link(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
    """False only when the task is not yours. No live link is not an error."""
    task = _own_task(db, user_id, task_id)
    if task is None:
        return False
    now = utc_now()
    for old in _live_links(db, task.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    """Take someone off your task. `member_id` is the membership's own id."""
    task = _own_task(db, user_id, task_id)
    if task is None:
        return False
    member = db.query(TaskMemberModel).filter(
        TaskMemberModel.id == member_id, TaskMemberModel.task_id == task.id,
    ).first()
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True


# --------------------------------------------------------------- the member --

def _out(row: sharing.SharedTask) -> SharedTask:
    return SharedTask(
        task_id=row.task_id, owner_name=row.owner_name, title=row.title, notes=row.notes,
        due_date=row.due_date, due_time=row.due_time, done=row.done, completed_at=row.completed_at,
        member_names=row.member_names,
    )


def shared_with_me(db: Session, user_id: uuid.UUID) -> list[SharedTask]:
    rows = sharing.shared_tasks(db, user_id)
    rows.sort(key=lambda r: (r.done, r.due_date is None, r.due_date or 0, r.due_time is None,
                             r.due_time or 0, r.title.lower()))
    return [_out(r) for r in rows]


def _one(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> sharing.SharedTask | None:
    return next((r for r in sharing.shared_tasks(db, user_id) if r.task_id == task_id), None)


def update_shared(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: SharedTaskUpdate) -> SharedTask | None:
    """None when you are not on the task: indistinguishable from no task."""
    current = _one(db, user_id, task_id)
    if current is None:
        return None
    fields = data.model_dump(exclude_unset=True)
    if "title" in fields or "notes" in fields:
        title = fields["title"].strip() if fields.get("title") is not None else current.title
        notes = fields["notes"] if "notes" in fields else current.notes
        if not sharing.edit_shared_task(db, user_id, task_id, title, notes):
            return None
    if fields.get("done") is not None:
        if not sharing.set_shared_task_done(db, user_id, task_id, fields["done"]):
            return None
    updated = _one(db, user_id, task_id)
    return _out(updated) if updated else None


def leave(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
    return sharing.leave_shared_task(db, user_id, task_id)


def preview(db: Session, user_id: uuid.UUID, token: str) -> TaskInvitePreview | None:
    found = sharing.task_invite_preview(db, user_id, token_hash(token))
    return TaskInvitePreview(owner_name=found.owner_name, title=found.title) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    return sharing.accept_task_invite(db, user_id, token_hash(token))
