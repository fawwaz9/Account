"""Owner review of prerequisite proposals: list them as counts, approve or reject them.

    export CATALOGUE_REVIEW_URL=postgresql://...
    python scripts/catalogue_review.py
    python scripts/catalogue_review.py approve 3fa2c1d0 [--session 2026W]
    python scripts/catalogue_review.py reject 3fa2c1d0

The only writer of the shared catalogue: it runs as the tables' owner and refuses
the API's role or any role that cannot write them. Pending proposals are grouped by
course, kind and rule tree and shown as how many distinct accounts proposed each,
never who, and never a note or syllabus wording.

Approve writes the catalogue course if missing and the group's rule for one session
(the group's most common, or --session) as "reviewed-proposal", replacing an
existing rule only with --replace, and marks the group's proposals accepted. Reject
marks them rejected; they keep applying to their authors. Group ids hash the
course, kind and rule, so a listed id stays valid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app._database import rls  # noqa: E402
from app._database.db import connect_args_for, normalize_database_url  # noqa: E402
from app._database.models import (  # noqa: E402
    CatalogueCourseModel,
    CataloguePrerequisiteModel,
    CourseModel,
    PrerequisiteProposalModel,
    utc_now,
)
from app.Grades.services.catalogue_service import key_of  # noqa: E402
from app.Grades.utils.prerequisites import render, validate  # noqa: E402

VARIABLE = "CATALOGUE_REVIEW_URL"
"""The environment variable holding the review's database URL."""


class Refused(SystemExit):
    """Raised (as an exit) when the connection is not safe to review with; says why."""


@dataclass
class Group:
    """Pending proposals that agree on one course, kind and rule tree.

    Attributes:
        id: Eight hex characters hashing the course, kind and rule.
        campus: "UBCV" or "UBCO" from the course code, or None when it names none.
        subject: Subject code.
        number: Course number.
        kind: "prerequisite" or "corequisite".
        rule: The validated rule tree.
        accounts: Distinct proposing user ids; only their count is ever shown.
        proposal_ids: The proposals in the group.
        sessions: How many proposals name each calendar session.
    """
    id: str
    campus: str | None
    subject: str
    number: str
    kind: str
    rule: dict
    accounts: set = field(default_factory=set)
    proposal_ids: list = field(default_factory=list)
    sessions: Counter = field(default_factory=Counter)

    @property
    def course(self) -> str:
        """The course as "CAMPUS SUBJECT NUMBER", with "????" for an unknown campus."""
        return f"{self.campus or '????'} {self.subject} {self.number}"


def group_id(campus, subject, number, kind, rule) -> str:
    """Return the stable eight-character id of a (course, kind, rule) group.

    Args:
        campus: Campus code, or None.
        subject: Subject code, such as "CPSC".
        number: Course number.
        kind: "prerequisite" or "corequisite".
        rule: The rule tree.

    Returns:
        The first 8 hex characters of a SHA-256 of the canonical JSON.
    """
    canonical = json.dumps([campus, subject, number, kind, rule], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def check_connection(session: Session) -> None:
    """Refuse to run as the API's role, or as a role that cannot write the catalogue.

    Args:
        session: The review session; on SQLite nothing is checked.

    Raises:
        Refused: If connected as `rls.APP_ROLE` or without INSERT on a shared table.
    """
    if session.bind.dialect.name != "postgresql":
        return
    who = session.execute(text("SELECT current_user")).scalar()
    if who == rls.APP_ROLE:
        raise Refused(f"Connected as {rls.APP_ROLE}, the API's role. Review runs as the tables' owner.")
    for table in sorted(rls.SHARED_READ_TABLES):
        can = session.execute(text("SELECT has_table_privilege(current_user, :t, 'INSERT')"), {"t": table}).scalar()
        if not can:
            raise Refused(f"{who} cannot write {table}. Review runs as the tables' owner.")


def pending_groups(session: Session) -> list[Group]:
    """Return every pending proposal grouped by course, kind and rule.

    Proposals whose course code or rule cannot be read are skipped.

    Args:
        session: The review session.

    Returns:
        The groups ordered by subject, number, campus and kind, the most-supported
        first within each.
    """
    rows = (
        session.query(PrerequisiteProposalModel, CourseModel.code)
        .join(CourseModel, CourseModel.id == PrerequisiteProposalModel.course_id)
        .filter(PrerequisiteProposalModel.status == "pending")
        .all()
    )
    groups: dict[str, Group] = {}
    for proposal, code in rows:
        key = key_of(code)
        if key is None:
            continue
        try:
            rule = validate(proposal.rule)
        except ValueError:
            continue
        gid = group_id(key.campus, key.subject, key.number, proposal.kind, rule)
        group = groups.setdefault(gid, Group(gid, key.campus, key.subject, key.number, proposal.kind, rule))
        group.accounts.add(proposal.user_id)
        group.proposal_ids.append(proposal.id)
        if proposal.session:
            group.sessions[proposal.session] += 1
    return sorted(groups.values(), key=lambda g: (g.subject, g.number, g.campus or "", g.kind, -len(g.accounts)))


def existing_rule(session: Session, group: Group) -> CataloguePrerequisiteModel | None:
    """Return the catalogue's latest rule of this kind for the course, or None.

    Args:
        session: Session acting as the catalogue's owner.
        group: The proposal group.

    Returns:
        The newest rule by `session`, or None when the course or rule is not catalogued.
    """
    if group.campus is None:
        return None
    course = session.query(CatalogueCourseModel).filter_by(
        campus=group.campus, subject=group.subject, number=group.number).first()
    if course is None:
        return None
    rows = session.query(CataloguePrerequisiteModel).filter_by(catalogue_course_id=course.id, kind=group.kind).all()
    return max(rows, key=lambda r: r.session) if rows else None


def listing(session: Session) -> list[str]:
    """Return the review listing as lines, course by course.

    Groups are marked when several accounts agree, when they disagree with another
    group, when they match the catalogue, or when the campus is unknown.

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
        by_course[(group.course, group.kind)].append(group)
    for (course, kind), members in by_course.items():
        out.append(f"{course}  {kind}")
        current = existing_rule(session, members[0])
        if current is not None:
            out.append(f"    catalogue now ({current.session}): {render(current.rule)}")
        for group in members:
            accounts = len(group.accounts)
            marks = []
            if accounts >= 2:
                marks.append(f"{accounts} accounts agree")
            if len(members) > 1:
                marks.append("disagrees with another proposal")
            if current is not None and validate(current.rule) == group.rule:
                marks.append("same as the catalogue")
            if group.campus is None:
                marks.append("campus unknown: approve with --campus")
            suffix = f"   [{'; '.join(marks)}]" if marks else ""
            out.append(f"  {group.id}  {render(group.rule)}   ({accounts} account{'s' if accounts != 1 else ''}){suffix}")
    return out


def _find(session: Session, gid: str) -> Group:
    """Return the pending group with an id, or exit saying to list again."""
    for group in pending_groups(session):
        if group.id == gid:
            return group
    raise SystemExit(f"No pending group {gid}. Run the listing again; it may have been reviewed.")


def approve(session: Session, gid: str, session_name: str | None = None, campus: str | None = None,
            replace: bool = False) -> str:
    """Write a group's rule into the shared catalogue and accept its proposals.

    Only the rule tree is written; the note and any syllabus wording never are.

    Args:
        session: The review session, as the tables' owner.
        gid: The group id from the listing.
        session_name: The calendar session to file under; defaults to the group's most
            common.
        campus: The campus when the codes name none.
        replace: Replace an existing rule for that course, kind and session.

    Returns:
        A line describing what was approved.

    Raises:
        SystemExit: If the group is gone, the campus or session cannot be decided, or a
            rule exists and `replace` is False.

    Note:
        Commits.
    """
    group = _find(session, gid)
    campus = group.campus or campus
    if campus not in ("UBCV", "UBCO"):
        raise SystemExit(f"{group.course}: which campus? Pass --campus UBCV or --campus UBCO.")
    chosen_session = session_name or (group.sessions.most_common(1)[0][0] if group.sessions else None)
    if not chosen_session:
        raise SystemExit("No proposal says which session it is from. Pass --session, e.g. --session 2026W.")

    course = session.query(CatalogueCourseModel).filter_by(
        campus=campus, subject=group.subject, number=group.number).first()
    if course is None:
        course = CatalogueCourseModel(id=uuid.uuid4(), campus=campus, subject=group.subject, number=group.number)
        session.add(course)
        session.flush()
    row = session.query(CataloguePrerequisiteModel).filter_by(
        catalogue_course_id=course.id, kind=group.kind, session=chosen_session).first()
    if row is not None and not replace:
        raise SystemExit(f"The catalogue already has a {group.kind} for {group.course} in {chosen_session}: "
                         f"{render(row.rule)}. Pass --replace to replace it.")
    if row is None:
        row = CataloguePrerequisiteModel(id=uuid.uuid4(), catalogue_course_id=course.id, kind=group.kind,
                                         session=chosen_session)
        session.add(row)
    # The tree alone. No note and no wording: both are what a person typed or
    # their syllabus said, and neither is world knowledge (D6).
    row.rule, row.note, row.source, row.source_text, row.reviewed_at = (
        group.rule, None, "reviewed-proposal", None, utc_now())
    now = utc_now()
    session.query(PrerequisiteProposalModel).filter(PrerequisiteProposalModel.id.in_(group.proposal_ids)).update(
        {"status": "accepted", "reviewed_at": now}, synchronize_session=False)
    session.commit()
    return f"Approved {gid}: {campus} {group.subject} {group.number} {group.kind} ({chosen_session}) = {render(group.rule)}"


def reject(session: Session, gid: str) -> str:
    """Mark a group's proposals rejected; they still apply to their authors.

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
    session.query(PrerequisiteProposalModel).filter(PrerequisiteProposalModel.id.in_(group.proposal_ids)).update(
        {"status": "rejected", "reviewed_at": utc_now()}, synchronize_session=False)
    session.commit()
    return f"Rejected {gid}: {group.course} {group.kind} = {render(group.rule)}. It still applies to its authors."


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
        0 on success; 2 when `CATALOGUE_REVIEW_URL` is unset, the connection is refused,
        or approve/reject has no group id.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", nargs="?", default="list", choices=("list", "approve", "reject"))
    parser.add_argument("group", nargs="?")
    parser.add_argument("--session", dest="session_name")
    parser.add_argument("--campus", choices=("UBCV", "UBCO"))
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
            print(approve(session, args.group, args.session_name, args.campus, args.replace))
        else:
            print(reject(session, args.group))
    finally:
        session.close()
        session.bind.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
