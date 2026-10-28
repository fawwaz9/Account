"""Cross-user reads among the people a student already knows (Phase 3 items 8 and 13).

"Connections" are mutual partners and everyone on a team the caller is on. On
Postgres each read calls its `SECURITY DEFINER` function in `rls.FUNCTION_SQL`, keyed
on the session's acting user; on SQLite a plain query gives the same answer for the
`user_id` argument. Nothing here reaches anyone the caller isn't connected to.
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import GymBuddyModel, PartnershipModel, TeamMemberModel, TeamModel, UserModel


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


def _live(db: Session, user_id: uuid.UUID) -> UserModel | None:
    """Return the user if their account exists and is not being deleted, else None."""
    user = db.get(UserModel, user_id)
    return user if user is not None and user.deleted_at is None else None


def connections(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, set[str]]:
    """Return everyone the caller is connected to, with how: "partner" or a team's name.

    The SQLite twin of the connection rule in the Postgres functions.

    Args:
        db: Open session.
        user_id: The caller.

    Returns:
        Each connected person's id to the ways they're connected; never the caller.
    """
    found: dict[uuid.UUID, set[str]] = defaultdict(set)
    for row in db.query(PartnershipModel).filter(PartnershipModel.user_id == user_id):
        mutual = db.query(PartnershipModel).filter_by(user_id=row.partner_id, partner_id=user_id).first()
        if mutual is not None:
            found[row.partner_id].add("partner")
    teams = {t.id: t for t in db.query(TeamModel).filter(TeamModel.user_id == user_id)}
    for membership in db.query(TeamMemberModel).filter(TeamMemberModel.member_id == user_id):
        team = db.get(TeamModel, membership.team_id)
        if team is not None:
            teams[team.id] = team
    for team in teams.values():
        if _live(db, team.user_id) is None:
            continue
        people = {team.user_id} | {m.member_id for m in db.query(TeamMemberModel).filter_by(team_id=team.id)}
        for person in people - {user_id}:
            found[person].add(team.name)
    return found


@dataclass(frozen=True)
class GymBuddy:
    """A connection who is also looking for someone to train with.

    Attributes:
        name: Their display name.
        times: When they could go, or None.
        note: Anything else they said, or None.
        via: How you know them: "partner" and team names, in no particular order.
    """
    name: str
    times: str | None
    note: str | None
    via: list[str]


def gym_buddies(db: Session, user_id: uuid.UUID) -> list[GymBuddy]:
    """Return the caller's connections who are looking too, while the caller is looking.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the acting user.

    Returns:
        Looking connections by name; empty when the caller isn't looking.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_gym_buddies()")).all()
        return [GymBuddy(r.name, r.times, r.note, list(r.via or [])) for r in rows]
    mine = db.query(GymBuddyModel).filter_by(user_id=user_id).first()
    if mine is None or not mine.looking:
        return []
    out = []
    for person, ways in connections(db, user_id).items():
        status = db.query(GymBuddyModel).filter_by(user_id=person).first()
        user = _live(db, person)
        if status is None or not status.looking or user is None:
            continue
        out.append(GymBuddy(user.name, status.times, status.note, list(ways)))
    return sorted(out, key=lambda buddy: buddy.name)
