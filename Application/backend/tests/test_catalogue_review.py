"""The owner review script (Phase 2 item 6, D13): counts in, catalogue rows out.

Its "Done when": an approved proposal appears in every user's catalogue, a
rejected one stays only with its author, and the script refuses to run as the
app role. The last is proven on Postgres in test_rls.py's neighbour below.
"""
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import catalogue_review as review  # noqa: E402
from app._database.models import CatalogueCourseModel, CataloguePrerequisiteModel, PrerequisiteProposalModel  # noqa: E402
from app.Grades.services.prerequisite_service import prerequisites, set_own  # noqa: E402
from app.Grades.schemas.prerequisite import RuleWrite  # noqa: E402
from conftest import make_course, make_user  # noqa: E402


def propose(db, user, code, text, kind="prerequisite", year=3):
    course = make_course(db, user.id, code, year=year)
    set_own(db, user.id, course.id, RuleWrite(kind=kind, text=text, note=f"private note of {user.email}"),
            source="syllabus", source_text=f"private sentence of {user.email}")
    return course


def people(db, n):
    return [make_user(db, f"review-{i}-{uuid.uuid4().hex[:6]}@example.com") for i in range(n)]


def test_the_listing_counts_accounts_and_shows_no_one(db):
    a, b, c = people(db, 3)
    propose(db, a, "CPSC_V 221", "CPSC 210")
    propose(db, b, "CPSC_V 221", "cpsc 210")
    propose(db, c, "CPSC_V 221", "CPSC 213")
    text = "\n".join(review.listing(db))
    assert "UBCV CPSC 221  prerequisite" in text
    assert "CPSC 210   (2 accounts)" in text and "2 accounts agree" in text
    assert "CPSC 213   (1 account)" in text and "disagrees with another proposal" in text
    for person in (a, b, c):
        assert person.email not in text and str(person.id) not in text
    assert "private" not in text


def test_two_proposals_by_one_account_count_once(db):
    (a,) = people(db, 1)
    propose(db, a, "CPSC_V 221", "CPSC 210")
    propose(db, a, "CPSC_V 221 ", "CPSC 210", kind="prerequisite", year=4)  # a retake, same rule
    [group] = review.pending_groups(db)
    assert len(group.accounts) == 1 and len(group.proposal_ids) == 2


def test_approving_shares_the_rule_and_nothing_else(db):
    a, b, outsider = people(db, 3)
    propose(db, a, "CPSC_V 221", "CPSC 210")
    propose(db, b, "CPSC_V 221", "CPSC 210")
    [group] = review.pending_groups(db)
    review.approve(db, group.id, session_name="2026W")

    row = db.query(CataloguePrerequisiteModel).one()
    assert row.rule == {"course": "CPSC 210"} and row.source == "reviewed-proposal" and row.session == "2026W"
    assert row.note is None and row.source_text is None
    statuses = {p.status for p in db.query(PrerequisiteProposalModel)}
    assert statuses == {"accepted"}

    # Every user's catalogue: someone who proposed nothing now sees it.
    theirs = make_course(db, outsider.id, "CPSC_V 221", year=3)
    view = prerequisites(db, outsider.id, theirs.id)
    shared = next(k for k in view.kinds if k.kind == "prerequisite").shared
    assert shared.text == "CPSC 210" and shared.source == "reviewed"


def test_rejecting_leaves_the_rule_with_its_author_only(db):
    a, outsider = people(db, 2)
    mine = propose(db, a, "CPSC_V 221", "CPSC 213")
    [group] = review.pending_groups(db)
    review.reject(db, group.id)

    assert db.query(CatalogueCourseModel).count() == 0
    own = next(k for k in prerequisites(db, a.id, mine.id).kinds if k.kind == "prerequisite")
    assert own.yours.text == "CPSC 213" and own.yours.review == "rejected" and own.applies == "yours"
    theirs = make_course(db, outsider.id, "CPSC_V 221", year=3)
    assert all(k.shared is None and k.yours is None for k in prerequisites(db, outsider.id, theirs.id).kinds)


def test_the_session_is_the_groups_most_common_unless_given(db):
    a, b = people(db, 2)
    propose(db, a, "CPSC_V 221", "CPSC 210")
    propose(db, b, "CPSC_V 221", "CPSC 210")
    for proposal, session in zip(db.query(PrerequisiteProposalModel).all(), ("2025W", "2025W")):
        proposal.session = session
    db.commit()
    [group] = review.pending_groups(db)
    review.approve(db, group.id)
    assert db.query(CataloguePrerequisiteModel).one().session == "2025W"


def test_no_session_known_asks_for_one(db):
    (a,) = people(db, 1)
    propose(db, a, "CPSC_V 221", "CPSC 210")
    [group] = review.pending_groups(db)
    with pytest.raises(SystemExit, match="--session"):
        review.approve(db, group.id)
    assert db.query(CataloguePrerequisiteModel).count() == 0


def test_an_existing_rule_is_replaced_only_when_asked(db):
    a, b = people(db, 2)
    propose(db, a, "CPSC_V 221", "CPSC 210")
    [first] = review.pending_groups(db)
    review.approve(db, first.id, session_name="2026W")
    propose(db, b, "CPSC_V 221", "CPSC 213", year=4)
    [second] = review.pending_groups(db)
    with pytest.raises(SystemExit, match="--replace"):
        review.approve(db, second.id, session_name="2026W")
    review.approve(db, second.id, session_name="2026W", replace=True)
    assert db.query(CataloguePrerequisiteModel).one().rule == {"course": "CPSC 213"}


def test_a_code_without_a_campus_needs_one(db):
    (a,) = people(db, 1)
    propose(db, a, "CPSC 221", "CPSC 210")
    [group] = review.pending_groups(db)
    assert "campus unknown" in "\n".join(review.listing(db))
    with pytest.raises(SystemExit, match="--campus"):
        review.approve(db, group.id, session_name="2026W")
    review.approve(db, group.id, session_name="2026W", campus="UBCO")
    assert db.query(CatalogueCourseModel).one().campus == "UBCO"


def test_a_group_id_is_stable(db):
    assert review.group_id("UBCV", "CPSC", "221", "prerequisite", {"course": "CPSC 210"}) == \
        review.group_id("UBCV", "CPSC", "221", "prerequisite", {"course": "CPSC 210"})
    assert review.group_id("UBCV", "CPSC", "221", "prerequisite", {"course": "CPSC 210"}) != \
        review.group_id("UBCO", "CPSC", "221", "prerequisite", {"course": "CPSC 210"})


def test_an_unknown_group_changes_nothing(db):
    with pytest.raises(SystemExit, match="No pending group"):
        review.approve(db, "deadbeef", session_name="2026W")


def test_without_a_url_it_stops(monkeypatch, capsys):
    monkeypatch.delenv(review.VARIABLE, raising=False)
    assert review.main([]) == 2
