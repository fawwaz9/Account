"""Clubs (Phase 3 item 10): the owner's management, and what members see.

An owner makes a club, shares a join link, posts announcements, runs polls and adds
events; members read them and vote. The owner's own rows are read here directly;
everything a member reaches goes through `_database/clubs.py`.
"""
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app._database import clubs
from app._database.models import (
    INVITE_DAYS, ClubEventModel, ClubInviteModel, ClubMemberModel, ClubModel, ClubPollModel, ClubPostModel, utc_now,
)
from app.Clubs.schemas.club import (
    CalendarClubEvent, ClubDetail, ClubEventIn, ClubEventOut, ClubIn, ClubInvitePreview, ClubSummary, ClubUpdate,
    Link, Member, NewLink, PollIn, PollOut, PostIn, PostOut,
)
from app.shared.dates import user_for, user_today
from app.Teams.services.team_service import token_hash

#: Upcoming events a club page lists, from today.
EVENT_DAYS = 365


def _own(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> ClubModel | None:
    """Return the caller's own club, or None."""
    return db.query(ClubModel).filter(ClubModel.id == club_id, ClubModel.user_id == user_id).first()


def _live_links(db: Session, club_id: uuid.UUID):
    """Return a query for a club's unrevoked, unexpired links."""
    return db.query(ClubInviteModel).filter(ClubInviteModel.club_id == club_id, ClubInviteModel.revoked_at.is_(None),
                                            ClubInviteModel.expires_at > utc_now())


def overview(db: Session, user_id: uuid.UUID) -> list[ClubSummary] | None:
    """Return the clubs the caller owns, then those they're in, each by name.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The summaries; None when the user does not exist.
    """
    me = user_for(db, user_id)
    if me is None:
        return None
    owned = [
        ClubSummary(club_id=c.id, name=c.name, about=c.about, owner_name=me.name, is_owner=True,
                    member_count=1 + db.query(ClubMemberModel).filter_by(club_id=c.id).count())
        for c in db.query(ClubModel).filter(ClubModel.user_id == user_id).order_by(ClubModel.name)
    ]
    joined = [ClubSummary(club_id=c.club_id, name=c.club_name, about=c.about, owner_name=c.owner_name,
                          is_owner=False, member_count=c.members) for c in clubs.member_clubs(db, user_id)]
    return owned + joined


def _is_open(closes_on: date | None) -> bool:
    """Return whether a poll still counts votes today (UTC), its closing day included."""
    return closes_on is None or closes_on >= datetime.now(timezone.utc).date()


def detail(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> ClubDetail | None:
    """Return a club with its posts, polls and upcoming events; members and link for its owner.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.

    Returns:
        The club; None when the caller isn't in it, the same answer as for one that
        doesn't exist.
    """
    summary = next((c for c in overview(db, user_id) or [] if c.club_id == club_id), None)
    if summary is None:
        return None
    today = user_today(db, user_id)
    if summary.is_owner:
        rows = (db.query(ClubEventModel)
                .filter(ClubEventModel.club_id == club_id, ClubEventModel.on_date >= today,
                        ClubEventModel.on_date <= today + timedelta(days=EVENT_DAYS))
                .all())
        events = [ClubEventOut(event_id=e.id, title=e.title, on_date=e.on_date, start_time=e.start_time,
                               end_time=e.end_time, location=e.location) for e in rows]
        events.sort(key=lambda e: (e.on_date, e.start_time is not None, e.start_time or datetime.min.time()))
    else:
        events = [ClubEventOut(event_id=e.event_id, title=e.title, on_date=e.on_date, start_time=e.start_time,
                               end_time=e.end_time, location=e.location)
                  for e in clubs.member_events(db, user_id, today, today + timedelta(days=EVENT_DAYS))
                  if e.club_id == club_id]
    members = link = None
    if summary.is_owner:
        roster = db.query(ClubMemberModel).filter_by(club_id=club_id).order_by(ClubMemberModel.joined_at).all()
        members = [Member(id=m.id, name=m.member_name, joined_at=m.joined_at) for m in roster]
        live = _live_links(db, club_id).order_by(ClubInviteModel.created_at.desc()).first()
        link = Link(expires_at=live.expires_at) if live else None
    return ClubDetail(
        **summary.model_dump(),
        posts=[PostOut(post_id=p.post_id, body=p.body, created_at=p.created_at)
               for p in clubs.posts(db, user_id, club_id)],
        polls=[PollOut(poll_id=p.poll_id, question=p.question, options=p.options, closes_on=p.closes_on,
                       counts=p.counts, my_vote=p.my_vote, open=_is_open(p.closes_on))
               for p in clubs.polls(db, user_id, club_id)],
        events=events, members=members, link=link,
    )


def create(db: Session, user_id: uuid.UUID, data: ClubIn) -> ClubDetail | None:
    """Make a club with the caller as its owner.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: Its name and line.

    Returns:
        The new club; None when the user does not exist.

    Note:
        Commits.
    """
    if user_for(db, user_id) is None:
        return None
    club = ClubModel(user_id=user_id, name=data.name, about=data.about)
    db.add(club)
    db.commit()
    return detail(db, user_id, club.id)


def update(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, data: ClubUpdate) -> ClubDetail | None:
    """Rename a club or change its line; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        data: The fields to change.

    Returns:
        The club; None when the caller isn't its owner.

    Note:
        Commits.
    """
    club = _own(db, user_id, club_id)
    if club is None:
        return None
    fields = data.model_dump(exclude_unset=True)
    if fields.get("name") is not None:
        club.name = fields["name"]
    if "about" in fields:
        club.about = (fields["about"] or "").strip() or None
    db.commit()
    return detail(db, user_id, club_id)


def delete(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> str | None:
    """Delete a club with its members, links, posts, polls, votes and events; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.

    Returns:
        The deleted club's name; None when the caller isn't its owner.

    Note:
        Commits. Votes are other people's rows; the database cascade removes them.
    """
    club = _own(db, user_id, club_id)
    if club is None:
        return None
    name = club.name
    db.delete(club)
    db.commit()
    return name


def new_link(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> NewLink | None:
    """Make a new join link for a club, revoking any live one; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.

    Returns:
        The token, shown this once, and its expiry; None when the caller isn't the
        owner.

    Note:
        Commits; only the token's hash is stored.
    """
    club = _own(db, user_id, club_id)
    if club is None:
        return None
    now = utc_now()
    for old in _live_links(db, club.id):
        old.revoked_at = now
    token = secrets.token_urlsafe(24)
    link = ClubInviteModel(club_id=club.id, token_hash=token_hash(token), created_at=now,
                           expires_at=now + timedelta(days=INVITE_DAYS))
    db.add(link)
    db.commit()
    return NewLink(token=token, expires_at=link.expires_at)


def cancel_link(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> bool:
    """Revoke a club's live join links; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.

    Returns:
        True when the caller is the owner, whether or not a link was live.

    Note:
        Commits.
    """
    club = _own(db, user_id, club_id)
    if club is None:
        return False
    now = utc_now()
    for old in _live_links(db, club.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    """Take someone out of a club; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        member_id: The membership row's id.

    Returns:
        True if removed; False when the caller isn't the owner or there's no such member.

    Note:
        Commits.
    """
    club = _own(db, user_id, club_id)
    member = (db.query(ClubMemberModel).filter(ClubMemberModel.id == member_id, ClubMemberModel.club_id == club_id)
              .first() if club else None)
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True


def preview(db: Session, user_id: uuid.UUID, token: str) -> ClubInvitePreview | None:
    """Return what a club link shows, or None when it can't be used.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        token: The link's token.

    Returns:
        The owner's and club's names.
    """
    found = clubs.invite_preview(db, user_id, token_hash(token))
    return ClubInvitePreview(owner_name=found.owner_name, club_name=found.club_name) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    """Join a club through its link.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        token: The link's token.

    Returns:
        "accepted", "invalid", "own", "already" or "full".
    """
    return clubs.accept_invite(db, user_id, token_hash(token))


def add_post(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, data: PostIn) -> ClubDetail | None:
    """Post an announcement to a club; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        data: The announcement.

    Returns:
        The club; None when the caller isn't its owner.

    Note:
        Commits.
    """
    if _own(db, user_id, club_id) is None:
        return None
    db.add(ClubPostModel(club_id=club_id, body=data.body))
    db.commit()
    return detail(db, user_id, club_id)


def _own_child(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, model, row_id: uuid.UUID):
    """Return a row of the caller's own club by id, or None."""
    if _own(db, user_id, club_id) is None:
        return None
    return db.query(model).filter(model.id == row_id, model.club_id == club_id).first()


def delete_child(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, kind: str, row_id: uuid.UUID) -> bool:
    """Delete a post, poll or event of the caller's own club.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        kind: "post", "poll" or "event".
        row_id: The row.

    Returns:
        True if deleted; False when the caller isn't the owner or there's no such row.

    Note:
        Commits. A poll's votes go with it, by the database cascade.
    """
    model = {"post": ClubPostModel, "poll": ClubPollModel, "event": ClubEventModel}[kind]
    row = _own_child(db, user_id, club_id, model, row_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def add_poll(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, data: PollIn) -> ClubDetail | None:
    """Ask the club a question; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        data: The question, its choices and closing day.

    Returns:
        The club; None when the caller isn't its owner.

    Note:
        Commits.
    """
    if _own(db, user_id, club_id) is None:
        return None
    db.add(ClubPollModel(club_id=club_id, question=data.question, options=data.options, closes_on=data.closes_on))
    db.commit()
    return detail(db, user_id, club_id)


def vote(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, poll_id: uuid.UUID, option: int) -> ClubDetail | None:
    """Vote in a club's poll, or change the caller's vote.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        poll_id: The poll.
        option: The choice's position, from 0.

    Returns:
        The club; None when the vote wasn't recorded (not in the club, the poll isn't
        this club's or is closed, or no such choice).
    """
    if not any(p.poll_id == poll_id for p in clubs.polls(db, user_id, club_id)):
        return None
    if not clubs.vote(db, user_id, poll_id, option):
        return None
    return detail(db, user_id, club_id)


def add_event(db: Session, user_id: uuid.UUID, club_id: uuid.UUID, data: ClubEventIn) -> ClubDetail | None:
    """Add a club event, which appears on every member's calendar; owner only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.
        data: What, when and where.

    Returns:
        The club; None when the caller isn't its owner.

    Note:
        Commits.
    """
    if _own(db, user_id, club_id) is None:
        return None
    db.add(ClubEventModel(club_id=club_id, title=data.title, on_date=data.on_date, start_time=data.start_time,
                          end_time=data.end_time, location=data.location))
    db.commit()
    return detail(db, user_id, club_id)


def calendar_events(db: Session, user_id: uuid.UUID, start: date, end: date) -> list[CalendarClubEvent] | None:
    """Return club events for the caller's calendar: their own clubs' and their member clubs'.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        start: First day, inclusive.
        end: Last day, inclusive; at most 400 days after `start`.

    Returns:
        The events by date; None when the window is backwards or over 400 days.
    """
    if not timedelta(0) <= end - start <= timedelta(days=400):
        return None
    owned = [
        CalendarClubEvent(event_id=e.id, title=e.title, on_date=e.on_date, start_time=e.start_time,
                          end_time=e.end_time, location=e.location, club_id=c.id, club_name=c.name)
        for c in db.query(ClubModel).filter(ClubModel.user_id == user_id)
        for e in db.query(ClubEventModel).filter(ClubEventModel.club_id == c.id, ClubEventModel.on_date >= start,
                                                 ClubEventModel.on_date <= end)
    ]
    joined = [CalendarClubEvent(event_id=e.event_id, title=e.title, on_date=e.on_date, start_time=e.start_time,
                                end_time=e.end_time, location=e.location, club_id=e.club_id, club_name=e.club_name)
              for e in clubs.member_events(db, user_id, start, end)]
    return sorted(owned + joined, key=lambda e: (e.on_date, e.start_time is not None,
                                                 e.start_time or datetime.min.time()))


def leave(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> bool:
    """Leave a club the caller is a member of.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        club_id: The club.

    Returns:
        True if a membership was removed.
    """
    return clubs.leave(db, user_id, club_id)
