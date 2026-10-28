"""Cross-user steps for clubs (Phase 3 item 10): links, membership, posts, polls, events.

On Postgres each function calls its `SECURITY DEFINER` twin in `rls.FUNCTION_SQL`,
keyed on the session's acting user; on SQLite a plain query gives the same answer for
the `user_id` argument. "In the club" means its owner or a member, while the owner's
account is not being deleted. Members see names and counts, never another's id or
vote.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    MAX_CLUB_MEMBERS, ClubEventModel, ClubInviteModel, ClubMemberModel, ClubModel, ClubPollModel, ClubPostModel,
    ClubVoteModel, UserModel, utc_now,
)


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


def _live(db: Session, user_id: uuid.UUID) -> UserModel | None:
    """Return the user if their account exists and is not being deleted, else None."""
    user = db.get(UserModel, user_id)
    return user if user is not None and user.deleted_at is None else None


def in_club(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> ClubModel | None:
    """Return the club if the caller owns it or is a member and its owner is live, else None."""
    club = db.get(ClubModel, club_id)
    if club is None or _live(db, club.user_id) is None:
        return None
    if club.user_id == user_id:
        return club
    member = db.query(ClubMemberModel).filter_by(club_id=club_id, member_id=user_id).first()
    return club if member is not None else None


def _live_invite(db: Session, token_hash: str) -> ClubInviteModel | None:
    """Return the unrevoked, unexpired club link with this token hash, or None."""
    return (db.query(ClubInviteModel)
            .filter(ClubInviteModel.token_hash == token_hash, ClubInviteModel.revoked_at.is_(None),
                    ClubInviteModel.expires_at > utc_now())
            .first())


@dataclass(frozen=True)
class ClubInvitePreview:
    """What a live club link shows before it is accepted.

    Attributes:
        owner_name: The owner's display name.
        club_name: The club's name.
    """
    owner_name: str
    club_name: str


def invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> ClubInvitePreview | None:
    """Return what a club link shows: the owner's name and the club's.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        The preview; None when the link is unknown, revoked or expired, or the owner's
        account is being deleted.
    """
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_club_invite_preview(:h)"), {"h": token_hash}).first()
        return ClubInvitePreview(row.owner_name, row.club_name) if row else None
    invite = _live_invite(db, token_hash)
    club = db.get(ClubModel, invite.club_id) if invite else None
    owner = _live(db, club.user_id) if club else None
    return ClubInvitePreview(owner.name, club.name) if owner else None


def accept_invite(db: Session, user_id: uuid.UUID, token_hash: str) -> str:
    """Join a club through its link.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        "accepted"; "invalid" for an unusable link or account; "own" for the owner;
        "already" for a member; "full" at `MAX_CLUB_MEMBERS`.

    Note:
        Commits.
    """
    if _is_postgres(db):
        status = db.execute(text("SELECT account_accept_club_invite(:h)"), {"h": token_hash}).scalar()
        db.commit()
        return status
    invite = _live_invite(db, token_hash)
    club = db.get(ClubModel, invite.club_id) if invite else None
    if club is None:
        return "invalid"
    if club.user_id == user_id:
        return "own"
    me, owner = _live(db, user_id), _live(db, club.user_id)
    if me is None or owner is None:
        return "invalid"
    members = db.query(ClubMemberModel).filter(ClubMemberModel.club_id == club.id)
    if members.filter(ClubMemberModel.member_id == user_id).first() is not None:
        return "already"
    if members.count() >= MAX_CLUB_MEMBERS:
        return "full"
    db.add(ClubMemberModel(club_id=club.id, member_id=user_id, member_name=me.name, owner_name=owner.name,
                           joined_at=utc_now()))
    db.commit()
    return "accepted"


@dataclass(frozen=True)
class MemberClub:
    """A club the caller is in as a member.

    Attributes:
        club_id: The club.
        club_name: Its name.
        about: Its line about itself, or None.
        owner_name: The owner's name as copied when the caller joined.
        members: How many are in it, the owner included.
    """
    club_id: uuid.UUID
    club_name: str
    about: str | None
    owner_name: str
    members: int


def member_clubs(db: Session, user_id: uuid.UUID) -> list[MemberClub]:
    """Return the clubs the caller is in as a member, by name; owners read their own.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.

    Returns:
        One per membership whose owner is live.
    """
    if _is_postgres(db):
        return [MemberClub(*row) for row in db.execute(text("SELECT * FROM account_my_clubs()")).all()]
    out = []
    for membership in db.query(ClubMemberModel).filter(ClubMemberModel.member_id == user_id):
        club = db.get(ClubModel, membership.club_id)
        if club is None or _live(db, club.user_id) is None:
            continue
        count = db.query(ClubMemberModel).filter_by(club_id=club.id).count()
        out.append(MemberClub(club.id, club.name, club.about, membership.owner_name, 1 + count))
    return sorted(out, key=lambda c: c.club_name.lower())


@dataclass(frozen=True)
class Post:
    """An announcement in a club.

    Attributes:
        post_id: The post.
        body: Its text.
        created_at: When it was posted (naive UTC).
    """
    post_id: uuid.UUID
    body: str
    created_at: datetime


def posts(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> list[Post]:
    """Return a club's announcements, newest first, to someone in it.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        club_id: The club.

    Returns:
        The posts; empty for anyone not in the club.
    """
    if _is_postgres(db):
        return [Post(*row) for row in db.execute(text("SELECT * FROM account_club_posts(:c)"), {"c": club_id}).all()]
    if in_club(db, user_id, club_id) is None:
        return []
    rows = db.query(ClubPostModel).filter_by(club_id=club_id).order_by(ClubPostModel.created_at.desc()).all()
    return [Post(r.id, r.body, r.created_at) for r in rows]


@dataclass(frozen=True)
class Poll:
    """A club poll as someone in the club sees it: counts, never who voted for what.

    Attributes:
        poll_id: The poll.
        question: The question.
        options: The choices.
        closes_on: The last day votes count, or None.
        counts: Votes per choice, in order.
        my_vote: The caller's choice, or None.
    """
    poll_id: uuid.UUID
    question: str
    options: list[str]
    closes_on: date | None
    counts: list[int]
    my_vote: int | None


def polls(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> list[Poll]:
    """Return a club's polls, newest first, with counts and the caller's vote.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        club_id: The club.

    Returns:
        The polls; empty for anyone not in the club.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_club_polls(:c)"), {"c": club_id}).all()
        return [Poll(r.poll_id, r.question, list(r.options), r.closes_on, list(r.counts), r.my_vote) for r in rows]
    if in_club(db, user_id, club_id) is None:
        return []
    out = []
    for poll in db.query(ClubPollModel).filter_by(club_id=club_id).order_by(ClubPollModel.created_at.desc()):
        votes = db.query(ClubVoteModel).filter_by(poll_id=poll.id).all()
        counts = [sum(1 for v in votes if v.option == i) for i in range(len(poll.options))]
        mine = next((v.option for v in votes if v.user_id == user_id), None)
        out.append(Poll(poll.id, poll.question, list(poll.options), poll.closes_on, counts, mine))
    return out


def vote(db: Session, user_id: uuid.UUID, poll_id: uuid.UUID, option: int) -> bool:
    """Vote in a club poll, or change the caller's vote, while it is open.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        poll_id: The poll.
        option: The choice's position, from 0.

    Returns:
        True if the vote was recorded; False for someone not in the club, a closed poll
        (after its closing day, UTC) or a choice it doesn't have.

    Note:
        Commits.
    """
    if _is_postgres(db):
        done = db.execute(text("SELECT account_vote_club_poll(:p, :o)"), {"p": poll_id, "o": option}).scalar()
        db.commit()
        return bool(done)
    poll = db.get(ClubPollModel, poll_id)
    if poll is None or in_club(db, user_id, poll.club_id) is None:
        return False
    if poll.closes_on is not None and poll.closes_on < datetime.now(timezone.utc).date():
        return False
    if option is None or not 0 <= option < len(poll.options):
        return False
    row = db.query(ClubVoteModel).filter_by(user_id=user_id, poll_id=poll_id).first()
    if row is None:
        db.add(ClubVoteModel(user_id=user_id, poll_id=poll_id, option=option, created_at=utc_now()))
    else:
        row.option, row.created_at = option, utc_now()
    db.commit()
    return True


@dataclass(frozen=True)
class ClubEvent:
    """A club event for a member's calendar.

    Attributes:
        event_id: The event.
        club_id: Its club.
        club_name: Its club's name.
        title: What it is.
        on_date: The day.
        start_time: When it starts, or None for all day.
        end_time: When it ends, or None.
        location: Where, or None.
    """
    event_id: uuid.UUID
    club_id: uuid.UUID
    club_name: str
    title: str
    on_date: date
    start_time: time | None
    end_time: time | None
    location: str | None


def member_events(db: Session, user_id: uuid.UUID, start: date, end: date) -> list[ClubEvent]:
    """Return events of the clubs the caller is a member of, in a window of at most 400 days.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        start: First day, inclusive.
        end: Last day, inclusive.

    Returns:
        The events by date then start; empty for a window over 400 days.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_club_events(:s, :e)"), {"s": start, "e": end}).all()
        return [ClubEvent(*row) for row in rows]
    if not timedelta(0) <= end - start <= timedelta(days=400):
        return []
    out = []
    for membership in db.query(ClubMemberModel).filter(ClubMemberModel.member_id == user_id):
        club = db.get(ClubModel, membership.club_id)
        if club is None or _live(db, club.user_id) is None:
            continue
        for e in db.query(ClubEventModel).filter(ClubEventModel.club_id == club.id, ClubEventModel.on_date >= start,
                                                 ClubEventModel.on_date <= end):
            out.append(ClubEvent(e.id, club.id, club.name, e.title, e.on_date, e.start_time, e.end_time, e.location))
    return sorted(out, key=lambda e: (e.on_date, e.start_time is not None, e.start_time or time.min))


def leave(db: Session, user_id: uuid.UUID, club_id: uuid.UUID) -> bool:
    """Leave a club the caller is a member of.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only.
        club_id: The club.

    Returns:
        True if a membership was removed.

    Note:
        Commits.
    """
    if _is_postgres(db):
        left = db.execute(text("SELECT account_leave_club(:c)"), {"c": club_id}).scalar()
        db.commit()
        return bool(left)
    row = db.query(ClubMemberModel).filter_by(club_id=club_id, member_id=user_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
