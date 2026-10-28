"""Boards and the league directory (Phase 3 items 8-9, D13), on SQLite and Postgres.

The promises: a team's board shows teammates who opted in, only to teammates who
opted in; the campus board and the directory list teams, never people, and stay
empty until 5 teams with live captains are listed; asking to join is one request
per team, five waiting at most, and only the captain answers; a declined request
can't be sent again; and the definer functions and their SQLite twins agree.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import aggregates, recounts, teams
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import (
    DIRECTORY_FLOOR, MAX_PENDING_REQUESTS, ActivityModel, CampusBoardModel, GameModel, TeamJoinRequestModel,
    TeamMemberModel, TeamModel, UserModel, utc_now,
)
from app.Auth.services.session_service import create_access_token
from app.Fitness.services import league_service
from app.Teams.schemas.team import TeamUpdate
from app.Teams.services import team_service
from conftest import make_user

TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(league_service, "user_today", lambda db, user_id, at=None: TODAY)


def person(db, name, opted=False):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    if opted:
        user.preferences = {"leaderboard_opt_in": True}
    db.commit()
    return user


def team(db, captain, *members, name=None, listed=False, **extra):
    row = TeamModel(id=uuid.uuid4(), user_id=captain.id, name=name or f"{captain.name}'s team", listed=listed,
                    **extra)
    db.add(row)
    db.flush()
    for member in members:
        db.add(TeamMemberModel(id=uuid.uuid4(), team_id=row.id, member_id=member.id, member_name=member.name,
                               owner_name=captain.name))
    db.commit()
    return row


def ran(db, user, points, on=None):
    db.add(ActivityModel(user_id=user.id, on_date=on or MONDAY, kind="run", minutes=60, met=9.8, weight=1.0,
                         points=points, formula_version=1, source="manual"))
    db.commit()


def listed_teams(db, n, prefix="Team"):
    out = []
    for i in range(n):
        captain = person(db, f"{prefix} captain {i}", opted=True)
        out.append(team(db, captain, name=f"{prefix} {chr(65 + i)}", listed=True, sport="Ultimate"))
        ran(db, captain, 10 * (i + 1))
    return out


def as_(db, user):
    act_as(db, user.id)
    return user


# --- the team board -------------------------------------------------------------------------

def test_the_board_shows_opted_in_teammates_to_opted_in_teammates(db):
    sam, alex, jo = person(db, "Sam", opted=True), person(db, "Alex", opted=True), person(db, "Jo")
    row = team(db, sam, alex, jo)
    ran(db, sam, 50)
    ran(db, alex, 80)
    ran(db, jo, 999)
    ran(db, alex, 500, on=MONDAY - timedelta(days=1))  # last week
    as_(db, sam)
    board = league_service.team_board(db, sam.id, row.id)
    assert board.opted_in is True and board.week_start == MONDAY
    assert [(r.name, r.points, r.is_me) for r in board.rows] == [("Alex", 80, False), ("Sam", 50, True)]


def test_someone_not_opted_in_sees_an_empty_board(db):
    sam, alex = person(db, "Sam"), person(db, "Alex", opted=True)
    row = team(db, sam, alex)
    ran(db, alex, 80)
    as_(db, sam)
    board = league_service.team_board(db, sam.id, row.id)
    assert (board.opted_in, board.rows) == (False, [])


def test_nobody_reads_the_board_of_a_team_theyre_not_on(db):
    sam, alex, stranger = person(db, "Sam", opted=True), person(db, "Alex", opted=True), person(db, "S", opted=True)
    row = team(db, sam, alex)
    ran(db, alex, 80)
    as_(db, stranger)
    assert league_service.team_board(db, stranger.id, row.id).rows == []


def test_the_board_window_is_a_week_at_most(db):
    sam = person(db, "Sam", opted=True)
    row = team(db, sam)
    as_(db, sam)
    assert teams.team_board(db, sam.id, row.id, MONDAY, MONDAY + timedelta(days=6)) != []
    assert teams.team_board(db, sam.id, row.id, MONDAY - timedelta(days=30), MONDAY) == []


def test_a_player_being_deleted_leaves_the_board(db):
    sam, alex = person(db, "Sam", opted=True), person(db, "Alex", opted=True)
    row = team(db, sam, alex)
    alex.deleted_at = utc_now()
    db.commit()
    as_(db, sam)
    assert [r.name for r in league_service.team_board(db, sam.id, row.id).rows] == ["Sam"]


# --- the campus board -------------------------------------------------------------------------

def test_the_campus_board_ranks_listed_teams_by_opted_in_points(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    member = person(db, "Member", opted=True)
    shy = person(db, "Shy")
    db.add(TeamMemberModel(id=uuid.uuid4(), team_id=rows[0].id, member_id=member.id, member_name="Member",
                           owner_name="x"))
    db.add(TeamMemberModel(id=uuid.uuid4(), team_id=rows[0].id, member_id=shy.id, member_name="Shy", owner_name="x"))
    db.commit()
    ran(db, member, 100)
    ran(db, shy, 1000)
    team(db, person(db, "Unlisted", opted=True), name="Hidden team")
    assert aggregates.recount_campus_board(db) == DIRECTORY_FLOOR
    as_(db, person(db, "Reader"))
    board = league_service.campus_board(db)
    assert board.week_start == MONDAY
    assert [(t.team_name, t.points) for t in board.teams] == [
        ("Team A", 110), ("Team E", 50), ("Team D", 40), ("Team C", 30), ("Team B", 20)]


def test_below_the_floor_the_campus_board_is_empty(db):
    listed_teams(db, DIRECTORY_FLOOR - 1)
    assert aggregates.recount_campus_board(db) == 0
    assert league_service.campus_board(db).teams == []


def test_a_listed_team_whose_captain_is_being_deleted_doesnt_count(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    db.get(UserModel, rows[0].user_id).deleted_at = utc_now()
    db.commit()
    assert aggregates.recount_campus_board(db) == 0


def test_the_campus_board_read_checks_the_floor_again(db):
    for i in range(DIRECTORY_FLOOR - 1):
        db.add(CampusBoardModel(week_start=MONDAY, team_name=f"T{i}", points=1))
    db.commit()
    as_(db, person(db, "Reader"))
    assert league_service.campus_board(db).teams == []
    db.add(CampusBoardModel(week_start=MONDAY, team_name="T last", points=1))
    db.commit()
    assert len(league_service.campus_board(db).teams) == DIRECTORY_FLOOR, "at the floor it reads"


def test_the_daily_recount_runs_it(db):
    listed_teams(db, DIRECTORY_FLOOR)
    assert recounts.run_all(db)["campus_board"] == DIRECTORY_FLOOR


# --- the directory ---------------------------------------------------------------------------

def test_the_directory_opens_at_five_listed_teams_and_names_no_member(db):
    rows = listed_teams(db, DIRECTORY_FLOOR - 1)
    seeker = person(db, "Seeker")
    as_(db, seeker)
    assert league_service.directory(db, seeker.id).teams == []
    member = person(db, "Secret Member")
    rows.append(team(db, person(db, "Last captain"), member, name="Team Z", listed=True, level="casual",
                     area="UBC", looking_for_players=True, blurb="Come play"))
    as_(db, seeker)
    found = league_service.directory(db, seeker.id)
    assert [t.name for t in found.teams] == ["Team A", "Team B", "Team C", "Team D", "Team Z"]
    z = found.teams[-1]
    assert (z.members, z.level, z.area, z.looking, z.blurb, z.mine, z.requested) == (
        2, "casual", "UBC", True, "Come play", False, None)
    assert "Secret Member" not in found.model_dump_json()


def test_a_team_without_a_game_in_30_days_is_dormant(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    db.add(GameModel(team_id=rows[0].id, played_on=TODAY - timedelta(days=3), opponent="x", our_score=1,
                     their_score=0, recorded_by=rows[0].user_id, recorded_by_name="x"))
    db.add(GameModel(team_id=rows[1].id, played_on=TODAY - timedelta(days=40), opponent="x", our_score=1,
                     their_score=0, recorded_by=rows[1].user_id, recorded_by_name="x"))
    db.commit()
    seeker = as_(db, person(db, "Seeker"))
    by_name = {t.name: t for t in league_service.directory(db, seeker.id).teams}
    assert (by_name["Team A"].dormant, by_name["Team B"].dormant, by_name["Team C"].dormant) == (False, True, True)


def test_the_captain_lists_and_describes_the_team(db):
    sam = person(db, "Sam")
    row = team(db, sam)
    as_(db, sam)
    found = team_service.update(db, sam.id, row.id, TeamUpdate(listed=True, level="competitive", area="  Kits ",
                                                               looking_for_players=True, blurb=" "))
    assert found.listing.model_dump() == {"listed": True, "level": "competitive", "area": "Kits",
                                          "looking_for_players": True, "blurb": None}
    found = team_service.update(db, sam.id, row.id, TeamUpdate(level=None))
    assert found.listing.level is None and found.listing.listed is True


def test_only_the_captain_sees_the_listing(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    row = team(db, sam, alex, listed=True)
    as_(db, alex)
    assert team_service.detail(db, alex.id, row.id).listing is None


# --- asking to join ------------------------------------------------------------------------------

def test_asking_to_join_and_the_captain_accepting(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    seeker = as_(db, person(db, "Seeker"))
    assert teams.request_to_join(db, seeker.id, rows[0].id, "  I play handler ") == "sent"
    assert league_service.directory(db, seeker.id).teams[0].requested == "pending"
    captain = db.get(TeamModel, rows[0].id).user_id
    act_as(db, captain)
    [waiting] = league_service.team_requests(db, captain, rows[0].id)
    assert (waiting.requester_name, waiting.message) == ("Seeker", "I play handler")
    assert teams.answer_request(db, captain, waiting.request_id, True) == "accepted"
    assert db.query(TeamMemberModel).filter_by(team_id=rows[0].id, member_id=seeker.id).count() == 1
    as_(db, seeker)
    assert [r.status for r in league_service.my_requests(db, seeker.id)] == ["accepted"]


def test_a_declined_request_cant_be_sent_again(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    seeker = as_(db, person(db, "Seeker"))
    teams.request_to_join(db, seeker.id, rows[0].id, None)
    captain = db.get(TeamModel, rows[0].id).user_id
    act_as(db, captain)
    request_id = league_service.team_requests(db, captain, rows[0].id)[0].request_id
    assert teams.answer_request(db, captain, request_id, False) == "declined"
    as_(db, seeker)
    assert teams.request_to_join(db, seeker.id, rows[0].id, None) == "already"
    assert league_service.withdraw(db, seeker.id, request_id) is False, "an answered request stays"


@pytest.mark.parametrize("case", ["closed", "unlisted", "own", "long"])
def test_requests_that_arent_allowed(db, case):
    rows = listed_teams(db, DIRECTORY_FLOOR if case != "closed" else DIRECTORY_FLOOR - 1)
    seeker = person(db, "Seeker")
    target = rows[0].id
    if case == "unlisted":
        target = team(db, person(db, "Other"), name="Quiet").id
    if case == "own":
        target = team(db, seeker, name="Mine", listed=True).id
    as_(db, seeker)
    message = "x" * 201 if case == "long" else None
    expected = {"closed": "not_listed", "unlisted": "not_listed", "own": "own", "long": "invalid"}[case]
    assert teams.request_to_join(db, seeker.id, target, message) == expected
    assert db.query(TeamJoinRequestModel).count() == 0


def test_five_waiting_requests_at_most(db):
    rows = listed_teams(db, MAX_PENDING_REQUESTS + 1)
    seeker = as_(db, person(db, "Seeker"))
    for row in rows[:MAX_PENDING_REQUESTS]:
        assert teams.request_to_join(db, seeker.id, row.id, None) == "sent"
    assert teams.request_to_join(db, seeker.id, rows[-1].id, None) == "limit"


def test_only_the_captain_answers_and_a_waiting_request_can_be_taken_back(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    seeker, other = person(db, "Seeker"), person(db, "Other")
    as_(db, seeker)
    teams.request_to_join(db, seeker.id, rows[0].id, None)
    request_id = db.query(TeamJoinRequestModel).one().id
    act_as(db, other.id)
    assert league_service.team_requests(db, other.id, rows[0].id) == []
    assert teams.answer_request(db, other.id, request_id, True) == "invalid"
    act_as(db, seeker.id)
    assert teams.answer_request(db, seeker.id, request_id, True) == "invalid", "not even the requester"
    assert league_service.withdraw(db, seeker.id, request_id) is True
    assert db.query(TeamJoinRequestModel).count() == 0


def test_deleting_the_team_takes_its_requests(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    seeker = as_(db, person(db, "Seeker"))
    teams.request_to_join(db, seeker.id, rows[0].id, None)
    captain = db.get(TeamModel, rows[0].id).user_id
    act_as(db, captain)
    assert team_service.delete(db, captain, rows[0].id) is not None
    assert db.query(TeamJoinRequestModel).count() == 0


# --- the routes --------------------------------------------------------------------------------------

def test_the_routes(db):
    rows = listed_teams(db, DIRECTORY_FLOOR)
    seeker = person(db, "Seeker")
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(seeker.id, seeker.session_epoch or 0)}"}
        base = f"/api/fitness/{seeker.id}"
        listed = client.get(f"{base}/directory", headers=headers)
        sent = client.post(f"{base}/directory/{rows[0].id}/join", headers=headers, json={"message": "hi"})
        mine = client.get(f"{base}/join-requests", headers=headers)
        board = client.get(f"{base}/campus-board", headers=headers)
        too_long = client.post(f"{base}/directory/{rows[1].id}/join", headers=headers, json={"message": "x" * 201})
    finally:
        app.main.app.dependency_overrides.clear()
    assert len(listed.json()["teams"]) == DIRECTORY_FLOOR and listed.json()["floor"] == DIRECTORY_FLOOR
    assert sent.json() == {"status": "sent"}
    assert [r["team_name"] for r in mine.json()] == ["Team A"]
    assert board.json()["teams"] == [] and too_long.status_code == 422
