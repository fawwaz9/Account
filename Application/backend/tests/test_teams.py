"""Teams and games (Phase 2 item 11, D26).

Runs on SQLite and on Postgres: every step anyone on a team takes has a
definer-function path and a plain-query path that must mean the same.

The rules under test: a score counts only once someone other than its
recorder confirms it -- the captain included; a disputed score shows both and
doesn't count; only the captain changes who is on the team; a non-member sees
nothing of it.
"""
import re
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import rls, teams
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import MAX_TEAM_MEMBERS, GameModel, TeamInviteModel, TeamMemberModel, TeamModel, utc_now
from app.Auth.services.session_service import create_access_token
from app.Teams.schemas.team import DisputeIn, GameIn, TeamIn, TeamUpdate
from app.Teams.services import team_service as service
from app.Users.services.user_service import DELETION_GRACE_DAYS, delete_user, purge_expired_users
from conftest import make_user

DAY = date(2026, 10, 8)


def person(db, name):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    return user


def team_of(db, captain, name="Thunder"):
    act_as(db, captain.id)
    return service.create(db, captain.id, TeamIn(name=name, sport="Ultimate"))


def link(db, captain, team):
    act_as(db, captain.id)
    return service.new_link(db, captain.id, team.team_id)


def accept(db, user, token):
    act_as(db, user.id)
    return service.accept(db, user.id, token)


def join(db, captain, team, member):
    assert accept(db, member, link(db, captain, team).token) == "accepted"


def record(db, user, team, ours=7, theirs=5, opponent="Lightning"):
    act_as(db, user.id)
    return service.record_game(db, user.id, team.team_id,
                               GameIn(played_on=DAY, opponent=opponent, our_score=ours, their_score=theirs))


def view(db, user, team):
    act_as(db, user.id)
    return service.detail(db, user.id, team.team_id)


def only_game(db, user, team):
    [game] = view(db, user, team).games
    return game


def squad(db):
    """A captain and two players."""
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    team = team_of(db, sam)
    join(db, sam, team, alex)
    join(db, sam, team, kim)
    return sam, alex, kim, team


# --- links and the roster ---------------------------------------------------------

def test_only_a_hash_of_the_token_is_kept(db):
    sam = person(db, "Sam")
    team = team_of(db, sam)
    new = link(db, sam, team)
    row = db.query(TeamInviteModel).filter_by(team_id=team.team_id).one()
    assert row.token_hash == service.token_hash(new.token) and new.token not in row.token_hash
    assert row.expires_at - row.created_at == timedelta(days=7)


def test_a_preview_names_the_captain_the_team_and_the_sport(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    new = link(db, sam, team_of(db, sam))
    act_as(db, alex.id)
    found = service.preview(db, alex.id, new.token)
    assert (found.captain_name, found.team_name, found.sport) == ("Sam", "Thunder", "Ultimate")
    assert service.preview(db, alex.id, "not-a-real-token-at-all") is None


@pytest.mark.parametrize("spoil", ["expired", "cancelled", "replaced"])
def test_a_dead_link_previews_and_accepts_nothing(db, spoil):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    team = team_of(db, sam)
    new = link(db, sam, team)
    act_as(db, sam.id)
    if spoil == "expired":
        row = db.query(TeamInviteModel).filter_by(team_id=team.team_id).one()
        row.expires_at = utc_now() - timedelta(minutes=1)
        db.commit()
    elif spoil == "cancelled":
        assert service.cancel_link(db, sam.id, team.team_id) is True
    else:
        link(db, sam, team)
    act_as(db, alex.id)
    assert service.preview(db, alex.id, new.token) is None
    assert accept(db, alex, new.token) == "invalid"


def test_one_link_brings_in_the_whole_team_and_nobody_twice(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    team = team_of(db, sam)
    new = link(db, sam, team)
    assert accept(db, sam, new.token) == "own"
    assert accept(db, alex, new.token) == "accepted"
    assert accept(db, kim, new.token) == "accepted"
    assert accept(db, kim, new.token) == "already"
    assert view(db, sam, team).member_names == ["Alex", "Kim"]


def test_a_team_holds_at_most_the_limit(db):
    sam = person(db, "Sam")
    team = team_of(db, sam)
    new = link(db, sam, team)
    for n in range(MAX_TEAM_MEMBERS):
        assert accept(db, person(db, f"M{n}"), new.token) == "accepted"
    assert accept(db, person(db, "OneTooMany"), new.token) == "full"


def test_the_limit_in_the_database_function_is_the_models(db):
    found = re.search(r"FROM team_members WHERE team_id = tm\.id\) >= (\d+)", rls.FUNCTION_SQL)
    assert found and int(found.group(1)) == MAX_TEAM_MEMBERS


def test_a_member_sees_the_team_and_names_but_not_the_captains_controls(db):
    sam, alex, kim, team = squad(db)
    seen = view(db, alex, team)
    assert (seen.name, seen.captain_name, seen.is_captain, seen.member_names) == ("Thunder", "Sam", False, ["Alex", "Kim"])
    assert seen.members is None and seen.link is None
    captains = view(db, sam, team)
    assert captains.is_captain and [m.name for m in captains.members] == ["Alex", "Kim"]


def test_someone_not_on_the_team_sees_and_does_nothing(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    game = only_game(db, sam, team)
    eve = person(db, "Eve")
    act_as(db, eve.id)
    assert service.detail(db, eve.id, team.team_id) is None
    assert service.overview(db, eve.id) == []
    assert teams.games(db, eve.id, team.team_id) == []
    assert record(db, eve, team) is None
    for step in (teams.confirm_game, teams.delete_game):
        act_as(db, eve.id)
        assert step(db, eve.id, game.game_id) is False
    act_as(db, eve.id)
    assert teams.dispute_game(db, eve.id, game.game_id, 1, 1) is False
    act_as(db, eve.id)
    assert service.leave(db, eve.id, team.team_id) is False
    assert db.query(GameModel).count() == 1 and db.query(TeamMemberModel).count() == 2


# --- a score counts once someone else confirms it --------------------------------------

def test_a_recorded_game_counts_only_once_someone_else_confirms_it(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team, ours=7, theirs=5)
    assert view(db, sam, team).record.model_dump() == {
        "wins": 0, "losses": 0, "ties": 0, "points_for": 0, "points_against": 0, "unconfirmed": 1}
    game = only_game(db, alex, team)
    act_as(db, alex.id)
    assert teams.confirm_game(db, alex.id, game.game_id) is False, "nobody confirms their own score"
    act_as(db, kim.id)
    assert service.confirm_game(db, kim.id, team.team_id, game.game_id) is True
    act_as(db, sam.id)
    assert teams.confirm_game(db, sam.id, game.game_id) is False, "once is enough"
    assert view(db, sam, team).record.model_dump() == {
        "wins": 1, "losses": 0, "ties": 0, "points_for": 7, "points_against": 5, "unconfirmed": 0}
    assert only_game(db, sam, team).confirmed_by_name == "Kim"


def test_the_captain_needs_someone_else_too(db):
    sam, alex, kim, team = squad(db)
    record(db, sam, team)
    game = only_game(db, sam, team)
    act_as(db, sam.id)
    assert teams.confirm_game(db, sam.id, game.game_id) is False
    act_as(db, alex.id)
    assert teams.confirm_game(db, alex.id, game.game_id) is True


def test_wins_losses_and_ties(db):
    sam, alex, kim, team = squad(db)
    for ours, theirs in ((3, 1), (0, 2), (4, 4)):
        record(db, alex, team, ours=ours, theirs=theirs)
    for game in view(db, sam, team).games:
        act_as(db, kim.id)
        assert teams.confirm_game(db, kim.id, game.game_id)
    record_ = view(db, sam, team).record
    assert (record_.wins, record_.losses, record_.ties, record_.points_for, record_.points_against) == (1, 1, 1, 7, 7)


def test_a_disputed_score_shows_both_counts_for_nothing_and_settles_by_correction(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team, ours=7, theirs=5)
    game = only_game(db, alex, team)
    act_as(db, kim.id)
    assert service.dispute_game(db, kim.id, team.team_id, game.game_id, DisputeIn(our_score=6, their_score=5)) is True
    seen = only_game(db, sam, team)
    assert (seen.our_score, seen.their_score, seen.disputed_our, seen.disputed_their, seen.disputed_by_name) == (7, 5, 6, 5, "Kim")
    assert view(db, sam, team).record.unconfirmed == 1
    act_as(db, sam.id)
    assert teams.confirm_game(db, sam.id, game.game_id) is False, "not over someone else's dispute"
    act_as(db, alex.id)
    assert service.correct_game(db, alex.id, team.team_id, game.game_id,
                                GameIn(played_on=DAY, opponent="Lightning", our_score=6, their_score=5)) is True
    seen = only_game(db, sam, team)
    assert (seen.our_score, seen.disputed_by_name) == (6, None)
    act_as(db, sam.id)
    assert teams.confirm_game(db, sam.id, game.game_id) is True


def test_confirming_your_own_dispute_withdraws_it(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    game = only_game(db, alex, team)
    act_as(db, kim.id)
    teams.dispute_game(db, kim.id, game.game_id, 6, 5)
    act_as(db, kim.id)
    assert teams.confirm_game(db, kim.id, game.game_id) is True
    seen = only_game(db, sam, team)
    assert seen.confirmed_by_name == "Kim" and seen.disputed_by_name is None


def test_only_the_recorder_corrects_or_deletes_and_only_before_confirmation(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    game = only_game(db, alex, team)
    act_as(db, kim.id)
    assert teams.correct_game(db, kim.id, game.game_id, DAY, "Lightning", 0, 9) is False
    act_as(db, kim.id)
    assert teams.delete_game(db, kim.id, game.game_id) is False
    act_as(db, kim.id)
    teams.confirm_game(db, kim.id, game.game_id)
    act_as(db, alex.id)
    assert teams.correct_game(db, alex.id, game.game_id, DAY, "Lightning", 0, 9) is False
    act_as(db, alex.id)
    assert teams.delete_game(db, alex.id, game.game_id) is False
    act_as(db, kim.id)
    assert teams.dispute_game(db, kim.id, game.game_id, 1, 1) is False, "a confirmed game is settled"
    act_as(db, sam.id)
    assert teams.delete_game(db, sam.id, game.game_id) is True, "the captain can remove any game"


def test_the_recorder_can_delete_an_unconfirmed_game(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    act_as(db, alex.id)
    assert service.delete_game(db, alex.id, team.team_id, only_game(db, alex, team).game_id) is True
    assert view(db, sam, team).games == []


@pytest.mark.parametrize(("opponent", "ours", "theirs"), [("   ", 1, 1), ("x" * 61, 1, 1), ("Them", -1, 1), ("Them", 1, 1000)])
def test_the_database_refuses_a_bad_game_too(db, opponent, ours, theirs):
    sam, alex, kim, team = squad(db)
    act_as(db, alex.id)
    assert teams.record_game(db, alex.id, team.team_id, DAY, opponent, ours, theirs) is None
    assert db.query(GameModel).count() == 0


def test_a_game_is_only_reached_through_its_own_team(db):
    sam, alex, kim, team = squad(db)
    other = team_of(db, alex, name="Alex's other team")
    record(db, alex, other)
    stray = only_game(db, alex, other)
    act_as(db, kim.id)
    assert service.confirm_game(db, kim.id, team.team_id, stray.game_id) is None


# --- who is on it ------------------------------------------------------------------

def test_leaving_and_being_taken_off_both_cut_you_off_at_once(db):
    sam, alex, kim, team = squad(db)
    act_as(db, alex.id)
    assert service.leave(db, alex.id, team.team_id) is True
    assert service.detail(db, alex.id, team.team_id) is None
    kims_row = db.query(TeamMemberModel).filter_by(member_id=kim.id).one()
    act_as(db, sam.id)
    assert service.remove_member(db, sam.id, team.team_id, kims_row.id) is True
    act_as(db, kim.id)
    assert service.detail(db, kim.id, team.team_id) is None
    assert record(db, kim, team) is None


def test_only_the_captain_runs_the_team(db):
    sam, alex, kim, team = squad(db)
    kims_row = db.query(TeamMemberModel).filter_by(member_id=kim.id).one()
    act_as(db, alex.id)
    assert service.update(db, alex.id, team.team_id, TeamUpdate(name="Alex FC")) is None
    assert service.new_link(db, alex.id, team.team_id) is None
    assert service.cancel_link(db, alex.id, team.team_id) is False
    assert service.remove_member(db, alex.id, team.team_id, kims_row.id) is False
    assert service.delete(db, alex.id, team.team_id) is None
    assert view(db, sam, team).name == "Thunder" and db.query(TeamMemberModel).count() == 2


def test_deleting_the_team_takes_its_games_members_and_link(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    act_as(db, sam.id)
    assert service.delete(db, sam.id, team.team_id) == "Thunder"
    assert (db.query(GameModel).count(), db.query(TeamMemberModel).count(), db.query(TeamInviteModel).count()) == (0, 0, 0)
    assert service.overview(db, alex.id) == []


def _purge(db, user):
    act_as(db, user.id)
    delete_user(db, user.id)
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()


def test_a_captain_being_deleted_hides_the_team_and_their_purge_removes_it(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    game = only_game(db, alex, team)
    act_as(db, sam.id)
    delete_user(db, sam.id)
    act_as(db, alex.id)
    assert service.detail(db, alex.id, team.team_id) is None
    # Not only hidden from the list: nobody can play on, either.
    act_as(db, alex.id)
    assert teams.games(db, alex.id, team.team_id) == []
    assert record(db, alex, team) is None
    act_as(db, kim.id)
    assert teams.confirm_game(db, kim.id, game.game_id) is False
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()
    assert db.get(TeamModel, team.team_id) is None and db.query(TeamMemberModel).count() == 0


def test_a_player_being_purged_leaves_the_scoresheet_as_it_was(db):
    sam, alex, kim, team = squad(db)
    record(db, alex, team)
    _purge(db, alex)
    assert db.query(TeamMemberModel).filter_by(member_id=alex.id).count() == 0
    assert only_game(db, sam, team).recorded_by_name == "Alex"


# --- through the API -----------------------------------------------------------------

def signed_in(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}


def test_post_game_flow_through_the_api_with_names_never_emails(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    as_sam, as_alex = signed_in(sam), signed_in(alex)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        team = client.post(f"/api/teams/{sam.id}", json={"name": "Thunder", "sport": "Ultimate"}, headers=as_sam).json()
        token = client.post(f"/api/teams/{sam.id}/{team['team_id']}/link", headers=as_sam).json()["token"]
        joined = client.post(f"/api/teams/{alex.id}/invites/accept", json={"token": token}, headers=as_alex)
        recorded = client.post(f"/api/teams/{alex.id}/{team['team_id']}/games", headers=as_alex,
                               json={"played_on": "2026-10-08", "opponent": "Lightning", "our_score": 7, "their_score": 5})
        game_id = recorded.json()["games"][0]["game_id"]
        own = client.post(f"/api/teams/{alex.id}/{team['team_id']}/games/{game_id}/confirm", headers=as_alex)
        confirmed = client.post(f"/api/teams/{sam.id}/{team['team_id']}/games/{game_id}/confirm", headers=as_sam)
        members_view = client.get(f"/api/teams/{alex.id}/{team['team_id']}", headers=as_alex)
        captains_view = client.get(f"/api/teams/{sam.id}/{team['team_id']}", headers=as_sam)
    finally:
        app.main.app.dependency_overrides.clear()
    assert joined.json() == {"status": "accepted"}
    assert own.status_code == 409 and confirmed.status_code == 200
    assert members_view.json()["record"]["wins"] == 1 and members_view.json()["members"] is None
    assert [m["name"] for m in captains_view.json()["members"]] == ["Alex"]
    for response in (recorded, members_view, captains_view):
        assert sam.email not in response.text and alex.email not in response.text
        assert str(sam.id) not in response.text.replace(f"/api/teams/{sam.id}", "")


def test_a_team_you_are_not_on_answers_404_like_one_that_does_not_exist(db):
    sam, eve = person(db, "Sam"), person(db, "Eve")
    team = team_of(db, sam)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        reads = [client.get(f"/api/teams/{eve.id}/{target}", headers=signed_in(eve))
                 for target in (team.team_id, uuid.uuid4())]
    finally:
        app.main.app.dependency_overrides.clear()
    assert [r.status_code for r in reads] == [404, 404] and reads[0].json() == reads[1].json()
