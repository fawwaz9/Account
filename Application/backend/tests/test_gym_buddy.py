"""Gym buddies (Phase 3 item 13), on SQLite and Postgres.

The promises: you see only connections, mutual partners and teammates, who are
looking too; only while you're looking yourself; never a stranger, a one-sided
partner, yourself or an account being deleted; and the definer function and its
SQLite twin agree.
"""
import uuid

from fastapi.testclient import TestClient

import app.main
from app._database import connections
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import PartnershipModel, TeamMemberModel, TeamModel, utc_now
from app.Auth.services.session_service import create_access_token
from app.Fitness.schemas.fitness import GymBuddyIn
from app.Fitness.services import gym_buddy_service as service
from conftest import make_user


def person(db, name):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    return user


def looking(db, user, times="mornings", note=None, on=True):
    act_as(db, user.id)
    return service.save(db, user.id, GymBuddyIn(looking=on, times=times, note=note))


def partners(db, a, b, mutual=True):
    db.add(PartnershipModel(id=uuid.uuid4(), user_id=a.id, partner_id=b.id, partner_name=b.name))
    if mutual:
        db.add(PartnershipModel(id=uuid.uuid4(), user_id=b.id, partner_id=a.id, partner_name=a.name))
    db.commit()


def team(db, captain, *members, name="Ultimate"):
    row = TeamModel(id=uuid.uuid4(), user_id=captain.id, name=name)
    db.add(row)
    db.flush()
    for member in members:
        db.add(TeamMemberModel(id=uuid.uuid4(), team_id=row.id, member_id=member.id, member_name=member.name,
                               owner_name=captain.name))
    db.commit()
    return row


def seen(db, user):
    act_as(db, user.id)
    return [(b.name, b.times, b.via) for b in service.read(db, user.id).buddies]


def test_a_partner_looking_too_is_shown(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    partners(db, sam, alex)
    looking(db, sam)
    looking(db, alex, times="weekday evenings")
    assert seen(db, sam) == [("Alex", "weekday evenings", "partner")]


def test_teammates_are_connections_both_ways(db):
    sam, alex, jo = person(db, "Sam"), person(db, "Alex"), person(db, "Jo")
    team(db, sam, alex, jo)
    for who in (sam, alex, jo):
        looking(db, who)
    assert [name for name, *_ in seen(db, sam)] == ["Alex", "Jo"], "the captain sees members"
    assert [name for name, *_ in seen(db, alex)] == ["Jo", "Sam"], "a member sees the captain and members"


def test_how_you_know_them_lists_every_way(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    partners(db, sam, alex)
    team(db, sam, alex, name="Ultimate")
    team(db, alex, sam, name="Badminton")
    looking(db, sam)
    looking(db, alex)
    assert seen(db, sam) == [("Alex", "mornings", "partner, Badminton, Ultimate")]


def test_you_see_nobody_while_you_arent_looking(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    partners(db, sam, alex)
    looking(db, alex)
    assert seen(db, sam) == []
    looking(db, sam, on=False)
    assert seen(db, sam) == []


def test_connections_not_looking_strangers_and_one_sided_partners_are_never_shown(db):
    sam, alex, stranger, fan = person(db, "Sam"), person(db, "Alex"), person(db, "Stranger"), person(db, "Fan")
    partners(db, sam, alex)
    # Sam's own row naming Fan, which Fan never agreed to (only the accept
    # function writes both); and Fan's naming Sam the other way round.
    partners(db, sam, fan, mutual=False)
    stalker = person(db, "Stalker")
    partners(db, stalker, sam, mutual=False)
    looking(db, stalker)
    looking(db, sam)
    looking(db, alex, on=False)
    looking(db, stranger)
    looking(db, fan)
    assert seen(db, sam) == []


def test_an_account_being_deleted_is_never_shown(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    partners(db, sam, alex)
    looking(db, sam)
    looking(db, alex)
    alex.deleted_at = utc_now()
    db.commit()
    assert seen(db, sam) == []


def test_a_team_whose_captain_is_being_deleted_connects_nobody(db):
    sam, alex, cap = person(db, "Sam"), person(db, "Alex"), person(db, "Cap")
    team(db, cap, sam, alex)
    for who in (sam, alex):
        looking(db, who)
    cap.deleted_at = utc_now()
    db.commit()
    assert seen(db, sam) == []


def test_saving_trims_and_reads_back(db):
    sam = person(db, "Sam")
    saved = looking(db, sam, times="  weekday mornings ", note="   ")
    assert (saved.looking, saved.times, saved.note) == (True, "weekday mornings", None)
    act_as(db, sam.id)
    assert service.read(db, sam.id).looking is True


def test_nobody_set_reads_as_not_looking(db):
    sam = person(db, "Sam")
    act_as(db, sam.id)
    found = service.read(db, sam.id)
    assert (found.looking, found.buddies) == (False, [])


def test_the_sqlite_connection_rule_matches(db):
    sam, alex, jo = person(db, "Sam"), person(db, "Alex"), person(db, "Jo")
    partners(db, sam, alex)
    team(db, jo, sam, name="Ultimate")
    found = connections.connections(db, sam.id)
    assert found == {alex.id: {"partner"}, jo.id: {"Ultimate"}}


def test_the_routes_read_and_save_your_own(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    partners(db, sam, alex)
    looking(db, alex)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        saved = client.put(f"/api/fitness/{sam.id}/gym-buddy", headers=headers,
                           json={"looking": True, "times": "evenings"})
        foreign = client.get(f"/api/fitness/{alex.id}/gym-buddy", headers=headers)
        too_long = client.put(f"/api/fitness/{sam.id}/gym-buddy", headers=headers,
                              json={"looking": True, "times": "x" * 81})
    finally:
        app.main.app.dependency_overrides.clear()
    assert saved.status_code == 200 and saved.json()["buddies"][0]["name"] == "Alex"
    assert (foreign.status_code, too_long.status_code) == (403, 422)
