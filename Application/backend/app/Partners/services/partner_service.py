"""Accountability partners: the caller's weekly figure, their invites and partners.

A partner sees completion only: the share of this week's tasks done and the run of
good weeks, never a grade, money or a task's name. The caller's figure is worked out
from their own tasks and written into their own partnership rows whenever they open
the panel; partners read it through `sharing.partner_figures`.
"""
import hashlib
import secrets
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database import sharing
from app._database.models import INVITE_DAYS, InviteModel, PartnershipModel, TaskModel, utc_now
from app.Partners.schemas.partner import (
    Figure, NewInvite, OpenInvite, Partner, Partners,
)
from app.shared.dates import user_for, user_today

#: A week at or above this share of its tasks done counts toward the streak.
GOOD_WEEK_PERCENT = 80.0
#: How far back a streak is counted.
STREAK_WEEKS_MAX = 26
#: Open invites at once: enough for a few friends, short of a spray.
MAX_OPEN_INVITES = 5


class InviteLimit(ValueError):
    """Raised when the caller already has `MAX_OPEN_INVITES` live invites."""
    pass


def token_hash(token: str) -> str:
    """Return the SHA-256 hex digest of an invite token, which is all that is stored.

    Args:
        token: The raw token from the invite link.

    Returns:
        The 64-character hex digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _monday(day: date) -> date:
    """Return the Monday of the week a date falls in."""
    return day - timedelta(days=day.weekday())


def _week_percent(tasks, start: date) -> float | None:
    """Return the share of tasks due in the week from `start` that are done, or None.

    None when nothing is due that week; otherwise a percentage to one decimal place.
    """
    end = start + timedelta(days=6)
    due = [t for t in tasks if t.due_date is not None and start <= t.due_date <= end]
    if not due:
        return None
    return round(100.0 * sum(1 for t in due if t.done) / len(due), 1)


def figure_for(db: Session, user_id: uuid.UUID, today: date | None = None) -> Figure:
    """Return the user's figure: this week's completion and the streak of good weeks.

    A week counts as good at `GOOD_WEEK_PERCENT` or more; a week with nothing due
    neither breaks nor extends the streak, which looks back at most `STREAK_WEEKS_MAX`
    weeks.

    Args:
        db: Open database session.
        user_id: Whose tasks to count.
        today: The day to measure from; defaults to the user's local today.

    Returns:
        The week's percentage (None when nothing is due), the streak, and the date.
    """
    today = today or user_today(db, user_id)
    this_week = _monday(today)
    oldest = this_week - timedelta(weeks=STREAK_WEEKS_MAX)
    tasks = (
        db.query(TaskModel.due_date, TaskModel.done)
        .filter(TaskModel.user_id == user_id, TaskModel.due_date >= oldest,
                TaskModel.due_date <= this_week + timedelta(days=6))
        .all()
    )
    streak = 0
    for weeks_back in range(1, STREAK_WEEKS_MAX + 1):
        percent = _week_percent(tasks, this_week - timedelta(weeks=weeks_back))
        if percent is None:
            continue
        if percent < GOOD_WEEK_PERCENT:
            break
        streak += 1
    return Figure(week_percent=_week_percent(tasks, this_week), streak_weeks=streak, figure_on=today)


def refresh_my_figure(db: Session, user_id: uuid.UUID) -> Figure:
    """Work out the caller's figure and write it into their own partnership rows.

    Args:
        db: Open session acting as the caller.
        user_id: The caller.

    Returns:
        The figure; commits only when the caller has partnership rows.
    """
    figure = figure_for(db, user_id)
    rows = db.query(PartnershipModel).filter(PartnershipModel.user_id == user_id).all()
    for row in rows:
        row.week_percent, row.streak_weeks, row.figure_on = figure.week_percent, figure.streak_weeks, figure.figure_on
    if rows:
        db.commit()
    return figure


def overview(db: Session, user_id: uuid.UUID) -> Partners | None:
    """Return the partners panel: figures, partners and open invites.

    Refreshes and stores the caller's own figure first.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The panel, or None when the user does not exist. A partner's figure is None
        until they have opened the app since the partnership began.
    """
    if user_for(db, user_id) is None:
        return None
    mine = refresh_my_figure(db, user_id)
    figures = sharing.partner_figures(db, user_id)
    partners = []
    for row in db.query(PartnershipModel).filter(PartnershipModel.user_id == user_id).order_by(PartnershipModel.created_at):
        theirs = figures.get(row.partner_id)
        partners.append(Partner(
            partner_id=row.partner_id, name=row.partner_name, since=row.created_at,
            figure=Figure(week_percent=theirs.week_percent, streak_weeks=theirs.streak_weeks,
                          figure_on=theirs.figure_on) if theirs and theirs.figure_on else None,
        ))
    now = utc_now()
    invites = [
        OpenInvite(id=i.id, created_at=i.created_at, expires_at=i.expires_at)
        for i in db.query(InviteModel).filter(
            InviteModel.user_id == user_id, InviteModel.used_at.is_(None), InviteModel.revoked_at.is_(None),
            InviteModel.expires_at > now,
        ).order_by(InviteModel.created_at)
    ]
    return Partners(mine=mine, partners=partners, invites=invites)


def create_invite(db: Session, user_id: uuid.UUID) -> NewInvite | None:
    """Create a partner invite link, valid for `INVITE_DAYS` days.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The invite with its token, shown this once; None when the user does not exist.

    Raises:
        InviteLimit: If the caller already has `MAX_OPEN_INVITES` live invites.

    Note:
        Commits; only the token's hash is stored.
    """
    if user_for(db, user_id) is None:
        return None
    now = utc_now()
    open_count = db.query(InviteModel).filter(
        InviteModel.user_id == user_id, InviteModel.used_at.is_(None), InviteModel.revoked_at.is_(None),
        InviteModel.expires_at > now,
    ).count()
    if open_count >= MAX_OPEN_INVITES:
        raise InviteLimit(f"You have {open_count} open invites. Cancel one, or wait for one to be used.")
    token = secrets.token_urlsafe(24)
    invite = InviteModel(id=uuid.uuid4(), user_id=user_id, kind="partner", token_hash=token_hash(token),
                         created_at=now, expires_at=now + timedelta(days=INVITE_DAYS))
    db.add(invite)
    db.commit()
    return NewInvite(id=invite.id, token=token, expires_at=invite.expires_at)


def revoke_invite(db: Session, user_id: uuid.UUID, invite_id: uuid.UUID) -> bool:
    """Cancel one of the caller's unused invites.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        invite_id: The invite.

    Returns:
        True if it is now revoked (repeating is harmless); False when it is missing,
        another user's, or already used.

    Note:
        Commits.
    """
    invite = db.query(InviteModel).filter(InviteModel.id == invite_id, InviteModel.user_id == user_id).first()
    if invite is None or invite.used_at is not None:
        return False
    invite.revoked_at = invite.revoked_at or utc_now()
    db.commit()
    return True


def preview(db: Session, user_id: uuid.UUID, token: str):
    """Return what a partner invite link shows, or None when it is not live.

    Args:
        db: Open session acting as the caller.
        user_id: The caller.
        token: The raw token from the link.

    Returns:
        The invite's preview, or None when the link is unknown, used or expired.
    """
    return sharing.invite_preview(db, user_id, token_hash(token))


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    """Accept a partner invite; returns "accepted", "invalid", "own" or "already".

    Args:
        db: Open session acting as the caller.
        user_id: The caller.
        token: The raw token from the link.

    Returns:
        "accepted", "invalid", "own" (the caller's own invite) or "already" (already
        partners).
    """
    return sharing.accept_partner_invite(db, user_id, token_hash(token))


def end(db: Session, user_id: uuid.UUID, partner_id: uuid.UUID) -> bool:
    """End a partnership from either side; returns whether one existed.

    Args:
        db: Open session acting as the caller.
        user_id: The caller.
        partner_id: The other person's user id.

    Returns:
        True when a partnership between the two existed and was removed.
    """
    return sharing.end_partnership(db, user_id, partner_id)
