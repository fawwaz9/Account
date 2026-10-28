"""Service functions for shared tasks: the owner's side and the member's.

The owner's functions touch only the owner's own rows (the task, its members
and its invite link) under the ordinary row policy. The member's functions go
entirely through `app._database.sharing`, whose definer functions are the only
way to reach a task someone else owns. Repeating occurrences cannot be shared.
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
    """Raised when a link is asked for on a task that cannot be shared."""

    pass


def token_hash(token: str) -> str:
    """Return the SHA-256 hex digest of an invite token, the only form ever stored.

    Args:
        token: The raw token from the link.

    Returns:
        The 64-character hex digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _own_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskModel | None:
    """Return the caller's own task with this id, or None."""
    return db.query(TaskModel).filter(TaskModel.id == task_id, TaskModel.user_id == user_id).first()


def _live_links(db: Session, task_id: uuid.UUID):
    """Query the task's invite links that are neither revoked nor expired."""
    return db.query(TaskInviteModel).filter(
        TaskInviteModel.task_id == task_id, TaskInviteModel.revoked_at.is_(None),
        TaskInviteModel.expires_at > utc_now(),
    )


# ---------------------------------------------------------------- the owner --

def sharing_of(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TaskSharing | None:
    """Return who is on one of the caller's tasks and whether a link is open.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        task_id: The task.

    Returns:
        Its members (earliest first), the newest live link, whether it can be
        shared and the member limit; None when the task is not the caller's.
    """
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
    """Make a fresh invite link for one of the caller's tasks, cancelling any live one.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        task_id: The task to share.

    Returns:
        The new link with its token, which is never shown again; None when the
        task is not the caller's.

    Raises:
        NotShareable: If the task is an occurrence of a repeating task.
    """
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
    """Revoke every live invite link on one of the caller's tasks.

    Commits; members who already joined stay.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        task_id: The task.

    Returns:
        True, including when no link was open; False when the task is not the
        caller's.
    """
    task = _own_task(db, user_id, task_id)
    if task is None:
        return False
    now = utc_now()
    for old in _live_links(db, task.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    """Take someone off one of the caller's tasks.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        task_id: The task.
        member_id: The membership row's id, not the member's user id.

    Returns:
        True when removed; False when the task is not the caller's or has no such
        member.
    """
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
    """Convert a definer function's shared-task row into the response model."""
    return SharedTask(
        task_id=row.task_id, owner_name=row.owner_name, title=row.title, notes=row.notes,
        due_date=row.due_date, due_time=row.due_time, done=row.done, completed_at=row.completed_at,
        member_names=row.member_names,
    )


def shared_with_me(db: Session, user_id: uuid.UUID) -> list[SharedTask]:
    """Return the tasks the caller has joined as a member.

    Open tasks come first, then by due date and time (undated last) and title.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The member's view of each task; empty when there are none.
    """
    rows = sharing.shared_tasks(db, user_id)
    rows.sort(key=lambda r: (r.done, r.due_date is None, r.due_date or 0, r.due_time is None,
                             r.due_time or 0, r.title.lower()))
    return [_out(r) for r in rows]


def _one(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> sharing.SharedTask | None:
    """Return the caller's member view of one shared task, or None if not on it."""
    return next((r for r in sharing.shared_tasks(db, user_id) if r.task_id == task_id), None)


def update_shared(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: SharedTaskUpdate) -> SharedTask | None:
    """Change a shared task as a member: tick it off, or edit its title and notes.

    Text and completion are separate definer calls, each committing on its own.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        task_id: The shared task.
        data: The fields to change; the title is stripped.

    Returns:
        The task as the member now sees it; None when the caller is not on it,
        which reads the same as no such task.
    """
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
    """Take the caller off someone else's task.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        task_id: The task.

    Returns:
        True when the caller was on it and has left; False otherwise.
    """
    return sharing.leave_shared_task(db, user_id, task_id)


def preview(db: Session, user_id: uuid.UUID, token: str) -> TaskInvitePreview | None:
    """Return what the holder of a task link sees before accepting it.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        token: The raw token from the link.

    Returns:
        The owner's name and the task's title; None when the link is unknown,
        revoked or expired, the task repeats, or its owner's account is being
        deleted.
    """
    found = sharing.task_invite_preview(db, user_id, token_hash(token))
    return TaskInvitePreview(owner_name=found.owner_name, title=found.title) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    """Join someone else's task through its invite link.

    Commits on success.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        token: The raw token from the link.

    Returns:
        "accepted", "invalid", "own", "already" or "full".
    """
    return sharing.accept_task_invite(db, user_id, token_hash(token))
