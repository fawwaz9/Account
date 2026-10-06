"""Owner review: proposals in, shared catalogue rows out (Phase 2 item 6, D13).

    CATALOGUE_REVIEW_URL=postgresql://... python scripts/catalogue_review.py
    CATALOGUE_REVIEW_URL=... python scripts/catalogue_review.py approve 3fa2c1d0 [--session 2026W]
    CATALOGUE_REVIEW_URL=... python scripts/catalogue_review.py reject 3fa2c1d0

The only writer of the shared catalogue. The API's role cannot write it (D9),
so this runs as the tables' owner -- the role the schema step runs as -- and
refuses to run as the app role, or as anything that cannot write them.

**What it shows: counts, never people.** Pending proposals are grouped by
course and rule, and each group says how many *different accounts* proposed
it. No names, no emails, no ids, no notes and no syllabus wording: a rule tree
holds course codes and numbers and nothing typed by a person, and that tree is
all that ever reaches the catalogue (D6). Two proposals by one account count
once.

**What it suggests.** A group several accounts agree on is marked; two groups
that disagree about one course are shown together, beside whatever the
catalogue already says.

**Approve** writes the catalogue course if it is missing, and the rule for the
session (the most common session among the group's proposals, or --session),
marked ``reviewed-proposal``. Every proposal in the group becomes accepted.
An existing rule for that course, kind and session is replaced only with
--replace. **Reject** marks the group's proposals rejected; they keep applying
to their authors, as yours always does.

Group ids are a hash of the course, kind and rule, so the id printed by a
listing names the same group when you approve it, however long you wait.
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


class Refused(SystemExit):
    """Not safe to run against this connection; the message says why."""


@dataclass
class Group:
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
        return f"{self.campus or '????'} {self.subject} {self.number}"


def group_id(campus, subject, number, kind, rule) -> str:
    canonical = json.dumps([campus, subject, number, kind, rule], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def check_connection(session: Session) -> None:
    """Refuse the app role, and anything that cannot write the catalogue.

    On SQLite (a local copy, and the tests) there are no roles to check.
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
    if group.campus is None:
        return None
    course = session.query(CatalogueCourseModel).filter_by(
        campus=group.campus, subject=group.subject, number=group.number).first()
    if course is None:
        return None
    rows = session.query(CataloguePrerequisiteModel).filter_by(catalogue_course_id=course.id, kind=group.kind).all()
    return max(rows, key=lambda r: r.session) if rows else None


def listing(session: Session) -> list[str]:
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
    for group in pending_groups(session):
        if group.id == gid:
            return group
    raise SystemExit(f"No pending group {gid}. Run the listing again; it may have been reviewed.")


def approve(session: Session, gid: str, session_name: str | None = None, campus: str | None = None,
            replace: bool = False) -> str:
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
    group = _find(session, gid)
    session.query(PrerequisiteProposalModel).filter(PrerequisiteProposalModel.id.in_(group.proposal_ids)).update(
        {"status": "rejected", "reviewed_at": utc_now()}, synchronize_session=False)
    session.commit()
    return f"Rejected {gid}: {group.course} {group.kind} = {render(group.rule)}. It still applies to its authors."


def open_session(raw: str) -> Session:
    url = normalize_database_url(raw)
    engine = create_engine(url, connect_args=connect_args_for(url), poolclass=NullPool)
    return sessionmaker(bind=engine)()


def main(argv: list[str] | None = None) -> int:
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
