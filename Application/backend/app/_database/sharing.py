"""Cross-user steps for partners, shared tasks and shared events.

On Postgres each function calls its `SECURITY DEFINER` twin in `rls.FUNCTION_SQL`,
which identifies the caller by the session's acting user and answers with a status
word, a name or a few named fields, never whole rows. On SQLite, which has no row
security, each runs a plain query meant to give the same answer, identifying the
caller by its `user_id` argument; routes pass the verified caller, so the two agree.
"""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    MAX_EVENT_MEMBERS, MAX_TASK_MEMBERS, EventInviteModel, EventMemberModel, EventModel, InviteModel,
    PartnershipModel, TaskInviteModel, TaskMemberModel, TaskModel, UserModel, utc_now,
)


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


@dataclass(frozen=True)
class InvitePreview:
    """What a live partner invite reveals before it is accepted.

    Attributes:
        inviter_name: The inviter's display name.
        kind: What the invite is for; "partner".
    """
    inviter_name: str
    kind: str


@dataclass(frozen=True)
class PartnerFigure:
    """A partner's own weekly completion figure, as read through the definer function.

    Attributes:
        partner_id: The partner whose figure this is.
        week_percent: Share of their tasks due this week that are done, 0-100; None
            when nothing was due.
        streak_weeks: Their run of good weeks before this one.
        figure_on: Their local date when the figure was worked out; None if never.
    """
    partner_id: uuid.UUID
    week_percent: float | None
    streak_weeks: int
    figure_on: date | None


def _live_invite(db: Session, token_hash: str):
    """Return the live partner invite with this token hash, or None.

    Live means unused, unrevoked and unexpired.
    """
    now = utc_now()
    return (
        db.query(InviteModel)
        .filter(InviteModel.token_hash == token_hash, InviteModel.used_at.is_(None),
                InviteModel.revoked_at.is_(None), InviteModel.expires_at > now)
        .first()
    )


def invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> InvitePreview | None:
    """Return what a partner invite link shows: the inviter's name and its kind.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        The preview, or None when the invite is unknown, used, revoked, expired or its
        inviter's account is being deleted.
    """
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
    """Accept a partner invite, writing both sides of the partnership together.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        "accepted"; "invalid" when the invite is unknown, used, revoked or expired, or
        either account is being deleted; "own" for the caller's own invite; "already"
        when the two are already partners.

    Note:
        Commits. Accepting is the only way a partnership row is written for another
        user, and it marks the invite used.
    """
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
    """End a partnership from either side, deleting both rows.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        partner_id: The other person in the partnership.

    Returns:
        True if any row was deleted, False when there was no such partnership.

    Note:
        Commits.
    """
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
    """Return each mutual partner's own weekly figure.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.

    Returns:
        Figures keyed by partner id, only where both partnership rows point at each
        other; a row naming someone who never accepted is left out. Empty when the
        caller has no mutual partners.
    """
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
    """What a live task link reveals before it is accepted.

    Attributes:
        owner_name: The task owner's display name.
        title: The task's title.
    """
    owner_name: str
    title: str


@dataclass(frozen=True)
class SharedTask:
    """The fields of someone else's task that a member may see.

    Never the course, grade, timer, priority or tags.

    Attributes:
        task_id: The task's id.
        owner_name: The owner's display name, as copied when the member joined.
        title: The task's title.
        notes: The task's notes, or None.
        due_date: Local due date, or None.
        due_time: Local due time, or None for end of day.
        done: Whether the task is complete.
        completed_at: When it was completed (naive UTC), or None.
        member_names: Every member's copied name, in joining order.
    """
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
    """Return the user if their account exists and is not being deleted, else None."""
    owner = db.get(UserModel, owner_id)
    return owner if owner is not None and owner.deleted_at is None else None


def _live_task_invite(db: Session, token_hash: str):
    """Return the unrevoked, unexpired task link with this token hash, or None."""
    return (
        db.query(TaskInviteModel)
        .filter(TaskInviteModel.token_hash == token_hash, TaskInviteModel.revoked_at.is_(None),
                TaskInviteModel.expires_at > utc_now())
        .first()
    )


def task_invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> TaskInvitePreview | None:
    """Return what a task link shows: the owner's name and the task's title.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        The preview, or None when the link is unknown, revoked or expired, the task is
        a repeating occurrence, or its owner's account is being deleted.
    """
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
    """Join a task through its link, adding the caller as a member.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        "accepted"; "invalid" when the link or task is unusable or either account is
        being deleted; "own" for the caller's own task; "already" for an existing
        member; "full" once the task has `MAX_TASK_MEMBERS` members.

    Note:
        Commits. The link stays usable for others until it expires or is revoked.
    """
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
    """Return a one-off task of a live owner that the caller belongs to, or None.

    The SQLite stand-in for the condition every shared-task definer function applies.
    """
    task = db.get(TaskModel, task_id)
    if task is None or task.recurring_id is not None or _live_owner(db, task.user_id) is None:
        return None
    member = db.query(TaskMemberModel).filter_by(task_id=task_id, member_id=user_id).first()
    return task if member is not None else None


def shared_tasks(db: Session, user_id: uuid.UUID) -> list[SharedTask]:
    """Return every task the caller is a member of, with only the fields members see.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.

    Returns:
        One `SharedTask` per membership, skipping repeating occurrences and tasks whose
        owner's account is being deleted; empty when there are none.
    """
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
    """Tick a shared task done or not done, for everyone on it.

    Completion and archiving move together, exactly as the owner's own tick does.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        task_id: The shared task.
        done: True to complete it, False to reopen it.

    Returns:
        True if the task changed; False when the caller is not a member, the task is a
        repeating occurrence or its owner's account is being deleted.

    Note:
        Commits.
    """
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
    """Change a shared task's title and notes as a member; nothing else can be edited.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        task_id: The shared task.
        title: New title; stripped, then 1-200 characters.
        notes: New notes, at most 2,000 characters; None clears them.

    Returns:
        True if the task changed; False when the caller may not edit it or a value is
        out of range.

    Note:
        Commits.
    """
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
    """Remove the caller from a shared task's members.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        task_id: The shared task.

    Returns:
        True if a membership was removed, False when the caller was not a member.

    Note:
        Commits.
    """
    if _is_postgres(db):
        left = bool(db.execute(text("SELECT account_leave_shared_task(:t)"), {"t": task_id}).scalar())
        db.commit()
        return left
    gone = db.query(TaskMemberModel).filter(
        TaskMemberModel.task_id == task_id, TaskMemberModel.member_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0


# --------------------------------------------------------------------------
# Shared events (Phase 2 item 9b, D24): a member sees and leaves, nothing more
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EventInvitePreview:
    """What a live event link reveals before it is accepted.

    Attributes:
        owner_name: The event owner's display name.
        title: The event's title.
        starts_on: The event's date.
    """
    owner_name: str
    title: str
    starts_on: date


@dataclass(frozen=True)
class SharedEvent:
    """The fields of someone else's event that a member may see: when and where.

    Attributes:
        event_id: The event's id.
        owner_name: The owner's display name, as copied when the member joined.
        title: The event's title.
        kind: The event's card theme, such as "personal".
        location: Where it happens, or None.
        notes: The event's notes, or None.
        starts_on: The event's date.
        start_time: Local start time, or None for all day.
        end_time: Local end time, or None for all day.
        member_names: Every member's copied name, in joining order.
    """
    event_id: uuid.UUID
    owner_name: str
    title: str
    kind: str
    location: str | None
    notes: str | None
    starts_on: date
    start_time: object | None
    end_time: object | None
    member_names: list[str]


def event_shareable(event: EventModel) -> bool:
    """Return whether an event may be shared: a one-off, not a shift or a grade's block.

    Args:
        event: The event to test.

    Returns:
        True when it has no recurrence rule, no job and no grade.
    """
    return event.recur_freq is None and event.job_id is None and event.grade_id is None


def _live_event_invite(db: Session, token_hash: str):
    """Return the unrevoked, unexpired event link with this token hash, or None."""
    return (
        db.query(EventInviteModel)
        .filter(EventInviteModel.token_hash == token_hash, EventInviteModel.revoked_at.is_(None),
                EventInviteModel.expires_at > utc_now())
        .first()
    )


def event_invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> EventInvitePreview | None:
    """Return what an event link shows: the owner's name, the title and the date.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        The preview, or None when the link is unknown, revoked or expired, the event
        cannot be shared, or its owner's account is being deleted.
    """
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_event_invite_preview(:h)"), {"h": token_hash}).first()
        return EventInvitePreview(row.owner_name, row.title, row.starts_on) if row else None
    invite = _live_event_invite(db, token_hash)
    event = db.get(EventModel, invite.event_id) if invite else None
    if event is None or not event_shareable(event):
        return None
    owner = _live_owner(db, event.user_id)
    return EventInvitePreview(owner.name, event.title, event.starts_on) if owner else None


def accept_event_invite(db: Session, user_id: uuid.UUID, token_hash: str) -> str:
    """Join an event through its link, adding the caller as a member.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        "accepted"; "invalid" when the link or event is unusable or either account is
        being deleted; "own" for the caller's own event; "already" for an existing
        member; "full" once the event has `MAX_EVENT_MEMBERS` members.

    Note:
        Commits.
    """
    if _is_postgres(db):
        status = db.execute(text("SELECT account_accept_event_invite(:h)"), {"h": token_hash}).scalar()
        db.commit()
        return status
    invite = _live_event_invite(db, token_hash)
    event = db.get(EventModel, invite.event_id) if invite else None
    if event is None or not event_shareable(event):
        return "invalid"
    if event.user_id == user_id:
        return "own"
    me, owner = _live_owner(db, user_id), _live_owner(db, event.user_id)
    if me is None or owner is None:
        return "invalid"
    members = db.query(EventMemberModel).filter(EventMemberModel.event_id == event.id)
    if members.filter(EventMemberModel.member_id == user_id).first() is not None:
        return "already"
    if members.count() >= MAX_EVENT_MEMBERS:
        return "full"
    db.add(EventMemberModel(id=uuid.uuid4(), event_id=event.id, member_id=user_id, member_name=me.name,
                            owner_name=owner.name, joined_at=utc_now()))
    db.commit()
    return "accepted"


def shared_events(db: Session, user_id: uuid.UUID) -> list[SharedEvent]:
    """Return every event the caller is a member of, with only the fields members see.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.

    Returns:
        One `SharedEvent` per membership, skipping events that can no longer be shared
        or whose owner's account is being deleted; empty when there are none.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_shared_events()")).all()
        return [SharedEvent(r.event_id, r.owner_name, r.title, r.kind, r.location, r.notes, r.starts_on,
                            r.start_time, r.end_time, list(r.member_names or [])) for r in rows]
    out = []
    for membership in db.query(EventMemberModel).filter(EventMemberModel.member_id == user_id):
        event = db.get(EventModel, membership.event_id)
        if event is None or not event_shareable(event) or _live_owner(db, event.user_id) is None:
            continue
        names = [m.member_name for m in sorted(
            db.query(EventMemberModel).filter(EventMemberModel.event_id == event.id),
            key=lambda m: (m.joined_at, m.member_name))]
        out.append(SharedEvent(event.id, membership.owner_name, event.title, event.kind, event.location,
                               event.notes, event.starts_on, event.start_time, event.end_time, names))
    return out


def leave_shared_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> bool:
    """Remove the caller from a shared event's members.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        event_id: The shared event.

    Returns:
        True if a membership was removed, False when the caller was not a member.

    Note:
        Commits.
    """
    if _is_postgres(db):
        left = bool(db.execute(text("SELECT account_leave_shared_event(:e)"), {"e": event_id}).scalar())
        db.commit()
        return left
    gone = db.query(EventMemberModel).filter(
        EventMemberModel.event_id == event_id, EventMemberModel.member_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0
