"""Club routes under `/api/clubs` (Phase 3 item 10).

A club the caller isn't in answers 404, the same as one that doesn't exist; only its
owner manages it. The literal `/events` and `/invites/...` paths are declared above
`/{club_id}`, which would otherwise read them as ids.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Clubs.schemas.club import (
    CalendarClubEvent, ClubDetail, ClubEventIn, ClubIn, ClubInvitePreview, ClubSummary, ClubUpdate, NewLink, PollIn,
    PostIn, VoteIn,
)
from app.Clubs.services import club_service as service
from app.shared import audit
from app.shared.errors import error_user, responses
from app.Tasks.schemas.sharing import TaskInviteAccepted as InviteAccepted, TaskInviteToken as InviteToken

router = APIRouter()

NO_CLUB = "Club not found"
CLUB_404 = {404: {"description": NO_CLUB}}
NO_LINK = "That link has expired or been cancelled."


def _found(value, detail: str = NO_CLUB):
    """Return a value, or raise a 404 with `detail` when it is None or False."""
    if value is None or value is False:
        raise HTTPException(status_code=404, detail=detail)
    return value


@router.get("/{user_id}", response_model=list[ClubSummary], responses=responses["user_404"])
def list_clubs(user_id: VerifiedUserId, db: DBSession):
    """List the clubs the caller owns, then those they're in.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Each club with its owner and size.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    return _found(service.overview(db, user_id), error_user["not_found"])


@router.post("/{user_id}", response_model=ClubDetail, responses=responses["user_404"])
def create_club(user_id: VerifiedUserId, body: ClubIn, db: DBSession):
    """Make a club with the caller as its owner.

    Args:
        user_id: The verified caller's id.
        body: Its name and line.
        db: Request-scoped database session.

    Returns:
        The new club.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    return _found(service.create(db, user_id, body), error_user["not_found"])


@router.get("/{user_id}/events", response_model=list[CalendarClubEvent],
            responses={400: {"description": "Window too long"}})
def club_events(user_id: VerifiedUserId, start: date, end: date, db: DBSession):
    """List club events for the caller's calendar: their own clubs' and their member clubs'.

    Args:
        user_id: The verified caller's id.
        start: First day, inclusive.
        end: Last day, inclusive; at most 400 days after `start`.
        db: Request-scoped database session.

    Returns:
        The events by date.

    Raises:
        HTTPException: 400 when the window is backwards or over 400 days.
    """
    found = service.calendar_events(db, user_id, start, end)
    if found is None:
        raise HTTPException(status_code=400, detail="Choose a window of at most 400 days.")
    return found


@router.post("/{user_id}/invites/preview", response_model=ClubInvitePreview, responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Return whose club a link joins, before accepting it; a POST keeps the token out of URLs.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The owner's and club's names.

    Raises:
        HTTPException: 404 when the link is unknown, revoked or expired.
    """
    return _found(service.preview(db, user_id, body.token), NO_LINK)


@router.post("/{user_id}/invites/accept", response_model=InviteAccepted, responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Join a club through its link.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        `status`: "accepted", "invalid", "own", "already" or "full".
    """
    return InviteAccepted(status=service.accept(db, user_id, body.token))


@router.get("/{user_id}/{club_id}", response_model=ClubDetail, responses=CLUB_404)
def get_club(user_id: VerifiedUserId, club_id: UUID, db: DBSession):
    """Read a club with its posts, polls and upcoming events.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        db: Request-scoped database session.

    Returns:
        The club, with its members and link for its owner.

    Raises:
        HTTPException: 404 when the caller isn't in it.
    """
    return _found(service.detail(db, user_id, club_id))


@router.patch("/{user_id}/{club_id}", response_model=ClubDetail, responses=CLUB_404)
def update_club(user_id: VerifiedUserId, club_id: UUID, body: ClubUpdate, db: DBSession):
    """Rename a club or change its line; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        body: The fields to change.
        db: Request-scoped database session.

    Returns:
        The club.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    return _found(service.update(db, user_id, club_id, body))


@router.delete("/{user_id}/{club_id}", responses=CLUB_404)
def delete_club(user_id: VerifiedUserId, club_id: UUID, db: DBSession):
    """Delete a club and everything in it; owner only, audit-logged.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    name = _found(service.delete(db, user_id, club_id))
    audit.deletion("club", user_id=user_id, target_id=club_id, detail=name)
    return {"deleted": True}


@router.post("/{user_id}/{club_id}/link", response_model=NewLink, responses=CLUB_404)
def make_link(user_id: VerifiedUserId, club_id: UUID, db: DBSession):
    """Make a new join link, cancelling any live one; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        db: Request-scoped database session.

    Returns:
        The token, shown this once, and its expiry.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    return _found(service.new_link(db, user_id, club_id))


@router.delete("/{user_id}/{club_id}/link", responses=CLUB_404)
def cancel_link(user_id: VerifiedUserId, club_id: UUID, db: DBSession):
    """Cancel the club's live join link; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        db: Request-scoped database session.

    Returns:
        `{"cancelled": true}`.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    _found(service.cancel_link(db, user_id, club_id))
    return {"cancelled": True}


@router.delete("/{user_id}/{club_id}/members/{member_id}", responses=CLUB_404)
def remove_member(user_id: VerifiedUserId, club_id: UUID, member_id: UUID, db: DBSession):
    """Take someone out of the club; owner only, audit-logged.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        member_id: The membership's id.
        db: Request-scoped database session.

    Returns:
        `{"removed": true}`.

    Raises:
        HTTPException: 404 when the caller isn't the owner or there's no such member.
    """
    _found(service.remove_member(db, user_id, club_id, member_id))
    audit.deletion("club_member", user_id=user_id, target_id=member_id)
    return {"removed": True}


@router.delete("/{user_id}/{club_id}/membership", responses=CLUB_404)
def leave_club(user_id: VerifiedUserId, club_id: UUID, db: DBSession):
    """Leave a club the caller is a member of.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        db: Request-scoped database session.

    Returns:
        `{"left": true}`.

    Raises:
        HTTPException: 404 when the caller isn't a member of it.
    """
    _found(service.leave(db, user_id, club_id))
    return {"left": True}


@router.post("/{user_id}/{club_id}/posts", response_model=ClubDetail, responses=CLUB_404)
def add_post(user_id: VerifiedUserId, club_id: UUID, body: PostIn, db: DBSession):
    """Post an announcement to every member; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        body: The announcement.
        db: Request-scoped database session.

    Returns:
        The club.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    return _found(service.add_post(db, user_id, club_id, body))


@router.delete("/{user_id}/{club_id}/posts/{post_id}", responses=CLUB_404)
def delete_post(user_id: VerifiedUserId, club_id: UUID, post_id: UUID, db: DBSession):
    """Delete an announcement; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        post_id: The post.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the caller isn't the owner or there's no such post.
    """
    _found(service.delete_child(db, user_id, club_id, "post", post_id))
    return {"deleted": True}


@router.post("/{user_id}/{club_id}/polls", response_model=ClubDetail, responses=CLUB_404)
def add_poll(user_id: VerifiedUserId, club_id: UUID, body: PollIn, db: DBSession):
    """Ask the club a question with 2-6 choices; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        body: The question, choices and closing day.
        db: Request-scoped database session.

    Returns:
        The club.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    return _found(service.add_poll(db, user_id, club_id, body))


@router.delete("/{user_id}/{club_id}/polls/{poll_id}", responses=CLUB_404)
def delete_poll(user_id: VerifiedUserId, club_id: UUID, poll_id: UUID, db: DBSession):
    """Delete a poll and its votes; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        poll_id: The poll.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the caller isn't the owner or there's no such poll.
    """
    _found(service.delete_child(db, user_id, club_id, "poll", poll_id))
    return {"deleted": True}


@router.post("/{user_id}/{club_id}/polls/{poll_id}/vote", response_model=ClubDetail,
             responses={404: {"description": "Can't vote in that poll"}})
def vote(user_id: VerifiedUserId, club_id: UUID, poll_id: UUID, body: VoteIn, db: DBSession):
    """Vote in a club's poll, or change the caller's vote, while it's open.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        poll_id: The poll.
        body: The choice.
        db: Request-scoped database session.

    Returns:
        The club, with the counts as they now stand.

    Raises:
        HTTPException: 404 when the caller isn't in the club, the poll is closed or
            isn't this club's, or there's no such choice.
    """
    return _found(service.vote(db, user_id, club_id, poll_id, body.option), "Can't vote in that poll")


@router.post("/{user_id}/{club_id}/events", response_model=ClubDetail, responses=CLUB_404)
def add_event(user_id: VerifiedUserId, club_id: UUID, body: ClubEventIn, db: DBSession):
    """Add a club event; it appears on every member's calendar. Owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        body: What, when and where.
        db: Request-scoped database session.

    Returns:
        The club.

    Raises:
        HTTPException: 404 when the caller isn't its owner.
    """
    return _found(service.add_event(db, user_id, club_id, body))


@router.delete("/{user_id}/{club_id}/events/{event_id}", responses=CLUB_404)
def delete_event(user_id: VerifiedUserId, club_id: UUID, event_id: UUID, db: DBSession):
    """Delete a club event; owner only.

    Args:
        user_id: The verified caller's id.
        club_id: The club.
        event_id: The event.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the caller isn't the owner or there's no such event.
    """
    _found(service.delete_child(db, user_id, club_id, "event", event_id))
    return {"deleted": True}
