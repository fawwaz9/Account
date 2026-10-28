"""Owner review of offered course outlines: list them, approve or reject them.

    export OUTLINE_REVIEW_URL=postgresql://...
    python scripts/outline_review.py
    python scripts/outline_review.py approve 3fa2c1d0 [--replace]
    python scripts/outline_review.py reject 3fa2c1d0

The only writer of `shared_outlines` (Phase 3 item 2, D12): it runs as the tables'
owner and refuses the API's role or any role that cannot write them. Pending offers
are grouped by course, term and outline, and shown with how many distinct accounts
offered each, never who. An outline holds weights and assessments' names,
categories and due dates, never a score or a note.

Approve copies the group's outline into `shared_outlines` for its course and term,
replacing an existing one only with --replace, and marks the group's offers
accepted. Reject marks them rejected. Group ids hash the course, term and outline,
so a listed id stays valid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app._database import rls  # noqa: E402
from app._database.db import connect_args_for, normalize_database_url  # noqa: E402
from app._database.models import OutlineOfferModel, SharedOutlineModel, utc_now  # noqa: E402
from app.Grades.schemas.outline import Outline  # noqa: E402

VARIABLE = "OUTLINE_REVIEW_URL"
"""The environment variable holding the review's database URL."""


class Refused(SystemExit):
    """Raised (as an exit) when the connection is not safe to review with; says why."""


@dataclass
class Group:
    """Pending offers that agree on one course, term and outline.

    Attributes:
        id: Eight hex characters hashing the course, term and outline.
        course_key: The course, such as "UBCV CPSC 221".
        term_code: The term, such as "2026W1".
        outline: The validated outline, as JSON.
        accounts: Distinct offering user ids; only their count is ever shown.
        offer_ids: The offers in the group.
    """
    id: str
    course_key: str
    term_code: str
    outline: dict
    accounts: set = field(default_factory=set)
    offer_ids: list = field(default_factory=list)


def group_id(course_key: str, term_code: str, outline: dict) -> str:
    """Return the stable eight-character id of a (course, term, outline) group.

    Args:
        course_key: The course.
        term_code: The term.
        outline: The outline as JSON.

    Returns:
        The first 8 hex characters of a SHA-256 of the canonical JSON.
    """
    canonical = json.dumps([course_key, term_code, outline], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def check_connection(session: Session) -> None:
    """Refuse to run as the API's role, or as a role that cannot write the outlines.

    Args:
        session: The review session; on SQLite nothing is checked.

    Raises:
        Refused: If connected as `rls.APP_ROLE` or without INSERT on `shared_outlines`.
    """
    if session.bind.dialect.name != "postgresql":
        return
    who = session.execute(text("SELECT current_user")).scalar()
    if who == rls.APP_ROLE:
        raise Refused(f"Connected as {rls.APP_ROLE}, the API's role. Review runs as the tables' owner.")
    can = session.execute(text("SELECT has_table_privilege(current_user, 'shared_outlines', 'INSERT')")).scalar()
    if not can:
        raise Refused(f"{who} cannot write shared_outlines. Review runs as the tables' owner.")


def pending_groups(session: Session) -> list[Group]:
    """Return every pending offer grouped by course, term and outline.

    Offers whose outline no longer validates are skipped.

    Args:
        session: The review session.

    Returns:
        The groups by course and term, the most-offered first within each.
    """
    groups: dict[str, Group] = {}
    for offer in session.query(OutlineOfferModel).filter(OutlineOfferModel.status == "pending"):
        try:
            outline = Outline.model_validate(offer.outline).model_dump(mode="json")
        except ValidationError:
            continue
        gid = group_id(offer.course_key, offer.term_code, outline)
        group = groups.setdefault(gid, Group(gid, offer.course_key, offer.term_code, outline))
        group.accounts.add(offer.user_id)
        group.offer_ids.append(offer.id)
    return sorted(groups.values(), key=lambda g: (g.course_key, g.term_code, -len(g.accounts)))


def render(outline: dict) -> list[str]:
    """Return an outline as indented lines: the weights, then each assessment.

    Args:
        outline: The outline as JSON.

    Returns:
        One line of weights, then one line per assessment with its date.
    """
    weights = ", ".join(f"{category} {weight:g}%" for category, weight in sorted(outline["weights"].items()))
    lines = [f"      weights: {weights}"]
    for item in outline["assessments"]:
        lines.append(f"      - {item['name']} ({item['category']}, {item['due_date'] or 'no date'})")
    return lines


def listing(session: Session) -> list[str]:
    """Return the review listing as lines, course and term by course and term.

    Args:
        session: The review session.

    Returns:
        The lines to print; "Nothing pending." when there is nothing to review.
    """
    groups = pending_groups(session)
    if not groups:
        return ["Nothing pending."]
    out = []
    by_course = defaultdict(list)
    for group in groups:
        by_course[(group.course_key, group.term_code)].append(group)
    for (course_key, term_code), members in by_course.items():
        out.append(f"{course_key}  {term_code}")
        if session.query(SharedOutlineModel).filter_by(course_key=course_key, term_code=term_code).first():
            out.append("    already shared: approving needs --replace")
        for group in members:
            accounts = len(group.accounts)
            marks = ["disagrees with another offer"] if len(members) > 1 else []
            suffix = f"   [{'; '.join(marks)}]" if marks else ""
            out.append(f"  {group.id}  ({accounts} account{'s' if accounts != 1 else ''}){suffix}")
            out += render(group.outline)
    return out


def _find(session: Session, gid: str) -> Group:
    """Return the pending group with an id, or exit saying to list again."""
    for group in pending_groups(session):
        if group.id == gid:
            return group
    raise SystemExit(f"No pending group {gid}. Run the listing again; it may have been reviewed.")


def approve(session: Session, gid: str, replace: bool = False) -> str:
    """Share a group's outline for its course and term, and accept its offers.

    Args:
        session: The review session, as the tables' owner.
        gid: The group id from the listing.
        replace: Replace an outline already shared for that course and term.

    Returns:
        A line describing what was approved.

    Raises:
        SystemExit: If the group is gone, or an outline is already shared and
            `replace` is False.

    Note:
        Commits.
    """
    group = _find(session, gid)
    row = session.query(SharedOutlineModel).filter_by(course_key=group.course_key, term_code=group.term_code).first()
    if row is not None and not replace:
        raise SystemExit(f"{group.course_key} {group.term_code} already has a shared outline. "
                         "Pass --replace to replace it.")
    if row is None:
        row = SharedOutlineModel(id=uuid.uuid4(), course_key=group.course_key, term_code=group.term_code)
        session.add(row)
    now = utc_now()
    row.outline, row.source, row.approved_at = group.outline, "reviewed-offer", now
    session.query(OutlineOfferModel).filter(OutlineOfferModel.id.in_(group.offer_ids)).update(
        {"status": "accepted", "reviewed_at": now}, synchronize_session=False)
    session.commit()
    return f"Approved {gid}: {group.course_key} {group.term_code}, {len(group.outline['assessments'])} assessments."


def reject(session: Session, gid: str) -> str:
    """Mark a group's offers rejected; nothing is shared.

    Args:
        session: The review session.
        gid: The group id from the listing.

    Returns:
        A line describing what was rejected.

    Raises:
        SystemExit: If the group is no longer pending.

    Note:
        Commits.
    """
    group = _find(session, gid)
    session.query(OutlineOfferModel).filter(OutlineOfferModel.id.in_(group.offer_ids)).update(
        {"status": "rejected", "reviewed_at": utc_now()}, synchronize_session=False)
    session.commit()
    return f"Rejected {gid}: {group.course_key} {group.term_code}."


def open_session(raw: str) -> Session:
    """Return a session on the given database URL, with no connection pooling.

    Args:
        raw: A database URL as pasted; normalised first.

    Returns:
        A new session; the caller closes it.
    """
    url = normalize_database_url(raw)
    engine = create_engine(url, connect_args=connect_args_for(url), poolclass=NullPool)
    return sessionmaker(bind=engine)()


def main(argv: list[str] | None = None) -> int:
    """Run the review from the command line: list (the default), approve or reject.

    Args:
        argv: Arguments instead of `sys.argv`, for tests.

    Returns:
        0 on success; 2 when `OUTLINE_REVIEW_URL` is unset, the connection is refused,
        or approve/reject has no group id.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", nargs="?", default="list", choices=("list", "approve", "reject"))
    parser.add_argument("group", nargs="?")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    raw = os.environ.get(VARIABLE, "").strip()
    if not raw:
        print(f"{VARIABLE} is not set", file=sys.stderr)
        return 2
    session = open_session(raw)
    try:
        try:
            check_connection(session)
        except Refused as refused:
            print(refused.code, file=sys.stderr)
            return 2
        if args.action == "list":
            print("\n".join(listing(session)))
        elif not args.group:
            print(f"{args.action} needs a group id from the listing", file=sys.stderr)
            return 2
        elif args.action == "approve":
            print(approve(session, args.group, args.replace))
        else:
            print(reject(session, args.group))
    finally:
        session.close()
        session.bind.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
