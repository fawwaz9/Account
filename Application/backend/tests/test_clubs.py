"""Clubs (Phase 3 item 10), on SQLite and Postgres.

The promises: a club is joined only by its owner's link; only the owner posts, runs
polls, adds events and manages members; members read posts, vote once per poll
(changeable, while open) and see counts, never who voted for what; club events reach
members' calendars; nobody outside a club reaches anything in it; and the definer
functions and their SQLite twins agree.
"""
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import clubs, rls
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import MAX_CLUB_MEMBERS, ClubMemberModel, ClubVoteModel, utc_now
from app.Auth.services.session_service import create_access_token
from app.Clubs.schemas.club import ClubEventIn, ClubIn, PollIn, PostIn
from app.Clubs.services import club_service as service
from conftest import make_user

TODAY = datetime.now(timezone.utc).date()


def person(db, name):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    act_as(db, user.id)
    return user


def club_of(db, owner, name="Chess Club"):
    act_as(db, owner.id)
    return service.create(db, owner.id, ClubIn(name=name, about="Wednesdays"))


def joined(db, owner, club, *people):
    act_as(db, owner.id)
    link = service.new_link(db, owner.id, club.club_id)
    for who in people:
        act_as(db, who.id)
        assert service.accept(db, who.id, link.token) == "accepted"
    return link


# --- joining ----------------------------------------------------------------------------

def test_a_link_joins_a_club_once(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    link = joined(db, sam, club, alex)
    act_as(db, alex.id)
    assert service.preview(db, alex.id, link.token).model_dump() == {"owner_name": "Sam", "club_name": "Chess Club"}
    assert service.accept(db, alex.id, link.token) == "already"
    act_as(db, sam.id)
    assert service.accept(db, sam.id, link.token) == "own"
    assert [m.name for m in service.detail(db, sam.id, club.club_id).members] == ["Alex"]


def test_a_new_link_cancels_the_old_one_and_a_cancelled_link_does_nothing(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    act_as(db, sam.id)
    first = service.new_link(db, sam.id, club.club_id)
    second = service.new_link(db, sam.id, club.club_id)
    act_as(db, alex.id)
    assert service.preview(db, alex.id, first.token) is None
    assert service.accept(db, alex.id, first.token) == "invalid"
    act_as(db, sam.id)
    service.cancel_link(db, sam.id, club.club_id)
    act_as(db, alex.id)
    assert service.accept(db, alex.id, second.token) == "invalid"


def test_the_member_limit_in_the_function_is_the_models():
    body = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_accept_club_invite("):]
    assert f">= {MAX_CLUB_MEMBERS} THEN RETURN 'full'" in body[:body.index("$$;")]


def test_a_member_lists_the_club_and_can_leave(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, alex.id)
    [listed] = service.overview(db, alex.id)
    assert (listed.name, listed.owner_name, listed.is_owner, listed.member_count) == ("Chess Club", "Sam", False, 2)
    assert service.leave(db, alex.id, club.club_id) is True
    assert service.overview(db, alex.id) == []
    assert service.detail(db, alex.id, club.club_id) is None


# --- what members see ---------------------------------------------------------------------

def test_posts_and_events_reach_members_and_nobody_else(db):
    sam, alex, stranger = person(db, "Sam"), person(db, "Alex"), person(db, "Stranger")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, sam.id)
    service.add_post(db, sam.id, club.club_id, PostIn(body=" Tournament Saturday "))
    service.add_event(db, sam.id, club.club_id, ClubEventIn(title="Tournament", on_date=TODAY + timedelta(days=3),
                                                             start_time=time(10, 0), location="SUB"))
    act_as(db, alex.id)
    seen = service.detail(db, alex.id, club.club_id)
    assert [p.body for p in seen.posts] == ["Tournament Saturday"]
    assert [(e.title, e.location) for e in seen.events] == [("Tournament", "SUB")]
    assert seen.members is None and seen.link is None, "only the owner manages"
    cal = service.calendar_events(db, alex.id, TODAY, TODAY + timedelta(days=30))
    assert [(e.title, e.club_name) for e in cal] == [("Tournament", "Chess Club")]
    act_as(db, stranger.id)
    assert service.detail(db, stranger.id, club.club_id) is None
    assert clubs.posts(db, stranger.id, club.club_id) == []
    assert service.calendar_events(db, stranger.id, TODAY, TODAY + timedelta(days=30)) == []


def test_the_owner_sees_their_own_events_on_the_calendar(db):
    sam = person(db, "Sam")
    club = club_of(db, sam)
    act_as(db, sam.id)
    service.add_event(db, sam.id, club.club_id, ClubEventIn(title="Social", on_date=TODAY))
    assert [e.title for e in service.calendar_events(db, sam.id, TODAY, TODAY)] == ["Social"]
    assert service.calendar_events(db, sam.id, TODAY, TODAY + timedelta(days=401)) is None


def test_only_the_owner_posts_runs_polls_adds_events_and_removes_people(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, alex.id)
    assert service.add_post(db, alex.id, club.club_id, PostIn(body="hi")) is None
    assert service.add_poll(db, alex.id, club.club_id, PollIn(question="Q", options=["a", "b"])) is None
    assert service.add_event(db, alex.id, club.club_id, ClubEventIn(title="x", on_date=TODAY)) is None
    assert service.new_link(db, alex.id, club.club_id) is None
    member_id = db.query(ClubMemberModel).one().id
    assert service.remove_member(db, alex.id, club.club_id, member_id) is False
    assert service.delete(db, alex.id, club.club_id) is None
    act_as(db, sam.id)
    assert service.remove_member(db, sam.id, club.club_id, member_id) is True


# --- polls ---------------------------------------------------------------------------------

def test_members_vote_once_can_change_and_see_counts_not_names(db):
    sam, alex, jo = person(db, "Sam"), person(db, "Alex"), person(db, "Jo")
    club = club_of(db, sam)
    joined(db, sam, club, alex, jo)
    act_as(db, sam.id)
    detail = service.add_poll(db, sam.id, club.club_id, PollIn(question="Meet when?", options=["Mon", "Wed", "Fri"]))
    poll_id = detail.polls[0].poll_id
    for who, option in ((alex, 1), (jo, 1), (sam, 0)):
        act_as(db, who.id)
        assert service.vote(db, who.id, club.club_id, poll_id, option) is not None
    act_as(db, alex.id)
    seen = service.vote(db, alex.id, club.club_id, poll_id, 2).polls[0]
    assert (seen.counts, seen.my_vote, seen.open) == ([1, 1, 1], 2, True)
    assert db.query(ClubVoteModel).count() == 3, "changing a vote doesn't add one"
    assert "Alex" not in seen.model_dump_json() and "Jo" not in seen.model_dump_json()


def test_votes_that_dont_count(db):
    sam, alex, stranger = person(db, "Sam"), person(db, "Alex"), person(db, "Stranger")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    other = club_of(db, sam, name="Other")
    act_as(db, sam.id)
    open_id = service.add_poll(db, sam.id, club.club_id, PollIn(question="Q", options=["a", "b"])).polls[0].poll_id
    closed_id = service.add_poll(db, sam.id, club.club_id, PollIn(
        question="Old", options=["a", "b"], closes_on=TODAY - timedelta(days=1))).polls[0].poll_id
    act_as(db, alex.id)
    assert service.vote(db, alex.id, club.club_id, closed_id, 0) is None, "closed"
    assert clubs.vote(db, alex.id, open_id, 2) is False, "no such choice"
    assert service.vote(db, alex.id, other.club_id, open_id, 0) is None, "not that club's poll"
    act_as(db, stranger.id)
    assert clubs.vote(db, stranger.id, open_id, 0) is False, "not in the club"
    assert db.query(ClubVoteModel).count() == 0


def test_a_poll_on_its_closing_day_still_counts(db):
    sam = person(db, "Sam")
    club = club_of(db, sam)
    act_as(db, sam.id)
    poll_id = service.add_poll(db, sam.id, club.club_id, PollIn(question="Q", options=["a", "b"],
                                                                 closes_on=TODAY)).polls[0].poll_id
    assert service.vote(db, sam.id, club.club_id, poll_id, 0).polls[0].open is True


@pytest.mark.parametrize("options", [["only"], ["a"] * 7, ["a", "A"], ["a", " "], ["a", "x" * 81]])
def test_a_poll_needs_two_to_six_distinct_choices(options):
    with pytest.raises(ValueError):
        PollIn(question="Q", options=options)


def test_deleting_a_poll_takes_everyones_votes(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, sam.id)
    poll_id = service.add_poll(db, sam.id, club.club_id, PollIn(question="Q", options=["a", "b"])).polls[0].poll_id
    act_as(db, alex.id)
    service.vote(db, alex.id, club.club_id, poll_id, 0)
    act_as(db, sam.id)
    assert service.delete_child(db, sam.id, club.club_id, "poll", poll_id) is True
    assert db.query(ClubVoteModel).count() == 0


def test_deleting_the_club_takes_everything_in_it(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, sam.id)
    poll_id = service.add_poll(db, sam.id, club.club_id, PollIn(question="Q", options=["a", "b"])).polls[0].poll_id
    act_as(db, alex.id)
    service.vote(db, alex.id, club.club_id, poll_id, 0)
    act_as(db, sam.id)
    assert service.delete(db, sam.id, club.club_id) == "Chess Club"
    assert db.query(ClubMemberModel).count() == 0 and db.query(ClubVoteModel).count() == 0


def test_an_owner_being_deleted_closes_the_club_to_members(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    sam.deleted_at = utc_now()
    db.commit()
    act_as(db, alex.id)
    assert service.overview(db, alex.id) == [] and service.detail(db, alex.id, club.club_id) is None


@pytest.mark.parametrize(("start", "end"), [(None, time(12, 0)), (time(12, 0), time(11, 0))])
def test_an_event_ends_after_it_starts(start, end):
    with pytest.raises(ValueError):
        ClubEventIn(title="x", on_date=TODAY, start_time=start, end_time=end)


# --- the routes ------------------------------------------------------------------------------

def test_the_routes(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        as_sam = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        as_alex = {"Authorization": f"Bearer {create_access_token(alex.id, alex.session_epoch or 0)}"}
        made = client.post(f"/api/clubs/{sam.id}", headers=as_sam, json={"name": "Chess Club"}).json()
        link = client.post(f"/api/clubs/{sam.id}/{made['club_id']}/link", headers=as_sam).json()
        joined_ = client.post(f"/api/clubs/{alex.id}/invites/accept", headers=as_alex, json={"token": link["token"]})
        client.post(f"/api/clubs/{sam.id}/{made['club_id']}/events", headers=as_sam,
                    json={"title": "Social", "on_date": TODAY.isoformat()})
        events = client.get(f"/api/clubs/{alex.id}/events", headers=as_alex,
                            params={"start": TODAY.isoformat(), "end": TODAY.isoformat()})
        poll = client.post(f"/api/clubs/{sam.id}/{made['club_id']}/polls", headers=as_sam,
                           json={"question": "Q", "options": ["a", "b"]}).json()["polls"][0]
        voted = client.post(f"/api/clubs/{alex.id}/{made['club_id']}/polls/{poll['poll_id']}/vote", headers=as_alex,
                            json={"option": 1})
        refused = client.post(f"/api/clubs/{alex.id}/{made['club_id']}/posts", headers=as_alex, json={"body": "hi"})
        too_long = client.get(f"/api/clubs/{alex.id}/events", headers=as_alex,
                              params={"start": TODAY.isoformat(), "end": (TODAY + timedelta(days=401)).isoformat()})
    finally:
        app.main.app.dependency_overrides.clear()
    assert joined_.json() == {"status": "accepted"}
    assert [e["title"] for e in events.json()] == ["Social"]
    assert voted.json()["polls"][0]["counts"] == [0, 1]
    assert (refused.status_code, too_long.status_code) == (404, 400)


def test_an_owner_being_deleted_closes_the_clubs_posts_and_polls_too(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, sam.id)
    service.add_post(db, sam.id, club.club_id, PostIn(body="hi"))
    poll_id = service.add_poll(db, sam.id, club.club_id, PollIn(question="Q", options=["a", "b"])).polls[0].poll_id
    sam.deleted_at = utc_now()
    db.commit()
    act_as(db, alex.id)
    assert clubs.posts(db, alex.id, club.club_id) == [] and clubs.polls(db, alex.id, club.club_id) == []
    assert clubs.vote(db, alex.id, poll_id, 0) is False


def test_the_member_events_window_is_400_days_at_most(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    club = club_of(db, sam)
    joined(db, sam, club, alex)
    act_as(db, sam.id)
    service.add_event(db, sam.id, club.club_id, ClubEventIn(title="Social", on_date=TODAY))
    act_as(db, alex.id)
    assert [e.title for e in clubs.member_events(db, alex.id, TODAY, TODAY + timedelta(days=400))] == ["Social"]
    assert clubs.member_events(db, alex.id, TODAY, TODAY + timedelta(days=401)) == []
    assert clubs.member_events(db, alex.id, TODAY, TODAY - timedelta(days=1)) == []
