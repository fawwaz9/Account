"""Shared events (Phase 2 item 9b, D24).

Runs on SQLite and on Postgres, like the shared-task tests: each member step
has a definer-function path and a plain-query path that must mean the same.

The rule: a member sees when and where, and may leave -- nothing a member does
changes the event. Only a one-off event of the owner's own can be shared.
"""
import re
import uuid
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import rls
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import (
    MAX_EVENT_MEMBERS, EventInviteModel, EventMemberModel, EventModel, GradeModel, JobModel, utc_now,
)
from app.Auth.services.session_service import create_access_token
from app.Calendar.services import event_sharing_service as shares
from app.Calendar.services.event_service import delete_event
from app.Users.services.user_service import DELETION_GRACE_DAYS, delete_user, purge_expired_users
from conftest import make_course, make_user


def person(db, name):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    return user


def own_event(db, user, title="Study group", **extra):
    fields = {"kind": "personal", "location": "Library 2F", "notes": "bring the problem set",
              "starts_on": date(2026, 10, 22), "start_time": time(14, 0), "end_time": time(15, 30), **extra}
    row = EventModel(id=uuid.uuid4(), user_id=user.id, title=title, **fields)
    db.add(row)
    db.commit()
    return row


def link(db, owner, event):
    act_as(db, owner.id)
    return shares.new_link(db, owner.id, event.id)


def accept(db, user, token):
    act_as(db, user.id)
    return shares.accept(db, user.id, token)


def join(db, owner, event, member):
    assert accept(db, member, link(db, owner, event).token) == "accepted"


def seen_by(db, user, **window):
    act_as(db, user.id)
    return shares.shared_with_me(db, user.id, **window)


def fresh(db, event):
    db.expire_all()
    return db.get(EventModel, event.id)


# --- links ----------------------------------------------------------------------

def test_only_a_hash_of_the_token_is_kept(db):
    sam = person(db, "Sam")
    event = own_event(db, sam)
    new = link(db, sam, event)
    row = db.query(EventInviteModel).filter_by(event_id=event.id).one()
    assert row.token_hash == shares.token_hash(new.token) and new.token not in row.token_hash
    assert row.expires_at - row.created_at == timedelta(days=7)


def test_a_preview_names_the_owner_the_event_and_its_day(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    new = link(db, sam, event)
    act_as(db, alex.id)
    found = shares.preview(db, alex.id, new.token)
    assert (found.owner_name, found.title, found.starts_on) == ("Sam", "Study group", date(2026, 10, 22))
    assert shares.preview(db, alex.id, "not-a-real-token-at-all") is None


@pytest.mark.parametrize("spoil", ["expired", "cancelled", "replaced"])
def test_a_dead_link_previews_and_accepts_nothing(db, spoil):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    new = link(db, sam, event)
    act_as(db, sam.id)
    if spoil == "expired":
        row = db.query(EventInviteModel).filter_by(event_id=event.id).one()
        row.expires_at = utc_now() - timedelta(minutes=1)
        db.commit()
    elif spoil == "cancelled":
        assert shares.cancel_link(db, sam.id, event.id) is True
    else:
        link(db, sam, event)
    act_as(db, alex.id)
    assert shares.preview(db, alex.id, new.token) is None
    assert accept(db, alex, new.token) == "invalid"
    assert db.query(EventMemberModel).count() == 0


def test_one_link_lets_several_people_join_and_not_twice(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    event = own_event(db, sam)
    new = link(db, sam, event)
    assert accept(db, sam, new.token) == "own"
    assert accept(db, alex, new.token) == "accepted"
    assert accept(db, kim, new.token) == "accepted"
    assert accept(db, kim, new.token) == "already"
    rows = db.query(EventMemberModel).filter_by(event_id=event.id).all()
    assert {(r.member_id, r.member_name, r.owner_name) for r in rows} == {(alex.id, "Alex", "Sam"), (kim.id, "Kim", "Sam")}


def test_an_event_holds_at_most_the_limit(db):
    sam = person(db, "Sam")
    event = own_event(db, sam)
    new = link(db, sam, event)
    for n in range(MAX_EVENT_MEMBERS):
        assert accept(db, person(db, f"M{n}"), new.token) == "accepted"
    assert accept(db, person(db, "OneTooMany"), new.token) == "full"


def test_the_limit_in_the_database_function_is_the_models(db):
    found = re.search(r"FROM event_members WHERE event_id = ev\.id\) >= (\d+)", rls.FUNCTION_SQL)
    assert found and int(found.group(1)) == MAX_EVENT_MEMBERS


@pytest.mark.parametrize("kind", ["repeat", "shift", "grade"])
def test_only_a_one_off_of_your_own_can_be_shared(db, kind):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    if kind == "repeat":
        event = own_event(db, sam, recur_freq="weekly")
    elif kind == "shift":
        job = JobModel(id=uuid.uuid4(), user_id=sam.id, name="Cafe", kind="hourly", hourly_rate=17.0)
        db.add(job)
        db.commit()
        event = own_event(db, sam, kind="shift", job_id=job.id)
    else:
        course = make_course(db, sam.id, "CPSC 310")
        grade = GradeModel(id=uuid.uuid4(), course_id=course.id, name="Midterm", category="Midterm", max_score=100.0)
        db.add(grade)
        db.commit()
        event = own_event(db, sam, kind="midterm", grade_id=grade.id)
    act_as(db, sam.id)
    with pytest.raises(shares.NotShareable):
        shares.new_link(db, sam.id, event.id)
    assert shares.sharing_of(db, sam.id, event.id).shareable is False
    # Rows written past the API are still ignored.
    token = f"planted-link-on-a-{kind}-event"
    db.add(EventInviteModel(id=uuid.uuid4(), event_id=event.id, token_hash=shares.token_hash(token),
                            created_at=utc_now(), expires_at=utc_now() + timedelta(days=1)))
    db.add(EventMemberModel(id=uuid.uuid4(), event_id=event.id, member_id=alex.id, member_name="Alex",
                            owner_name="Sam"))
    db.commit()
    act_as(db, alex.id)
    assert shares.preview(db, alex.id, token) is None
    assert accept(db, person(db, "Kim"), token) == "invalid"
    assert seen_by(db, alex) == []


# --- what a member sees ---------------------------------------------------------

def test_a_member_sees_when_and_where_and_who_else_never_the_course(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    course = make_course(db, sam.id, "CPSC 310")
    event = own_event(db, sam, course_id=course.id)
    join(db, sam, event, alex)
    join(db, sam, event, kim)
    [mine] = seen_by(db, alex)
    assert mine.model_dump() == {
        "event_id": event.id, "owner_name": "Sam", "title": "Study group", "kind": "personal",
        "location": "Library 2F", "notes": "bring the problem set", "starts_on": date(2026, 10, 22),
        "start_time": time(14, 0), "end_time": time(15, 30), "member_names": ["Alex", "Kim"],
    }


def test_the_window_bounds_what_is_listed(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    assert seen_by(db, alex, start=date(2026, 10, 20), end=date(2026, 10, 26))
    assert seen_by(db, alex, start=date(2026, 10, 23)) == []
    assert seen_by(db, alex, end=date(2026, 10, 21)) == []


def test_someone_not_on_the_event_sees_nothing_and_cannot_leave_for_anyone(db):
    sam, alex, eve = person(db, "Sam"), person(db, "Alex"), person(db, "Eve")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    assert seen_by(db, eve) == []
    act_as(db, eve.id)
    assert shares.leave(db, eve.id, event.id) is False
    assert db.query(EventMemberModel).count() == 1


def test_an_owner_change_reaches_members_and_making_it_repeat_hides_it(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    row = fresh(db, event)
    row.location = "Room 105"
    db.commit()
    assert seen_by(db, alex)[0].location == "Room 105"
    row.recur_freq = "weekly"
    db.commit()
    assert seen_by(db, alex) == []


# --- leaving, removing, deleting ---------------------------------------------------

def test_leaving_takes_only_you_off(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    join(db, sam, event, kim)
    act_as(db, alex.id)
    assert shares.leave(db, alex.id, event.id) is True
    assert seen_by(db, alex) == []
    assert [e.member_names for e in seen_by(db, kim)] == [["Kim"]]
    assert fresh(db, event) is not None


def test_removing_someone_cuts_them_off_at_once_and_only_the_owner_can(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    join(db, sam, event, kim)
    kims_row = db.query(EventMemberModel).filter_by(member_id=kim.id).one()
    act_as(db, alex.id)
    assert shares.sharing_of(db, alex.id, event.id) is None
    assert shares.new_link(db, alex.id, event.id) is None
    assert shares.remove_member(db, alex.id, event.id, kims_row.id) is False
    act_as(db, sam.id)
    assert shares.remove_member(db, sam.id, event.id, kims_row.id) is True
    assert seen_by(db, kim) == []


def test_deleting_the_event_ends_every_membership_and_link(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    act_as(db, sam.id)
    delete_event(db, sam.id, event.id)
    assert db.query(EventMemberModel).count() == 0 and db.query(EventInviteModel).count() == 0
    assert seen_by(db, alex) == []


def test_an_owner_being_deleted_hides_it_and_their_purge_removes_it(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    new = link(db, sam, event)
    assert accept(db, alex, new.token) == "accepted"
    act_as(db, sam.id)
    delete_user(db, sam.id)
    assert seen_by(db, alex) == []
    assert accept(db, person(db, "Kim"), new.token) == "invalid"
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()
    assert db.get(EventModel, event.id) is None and db.query(EventMemberModel).count() == 0


def test_a_member_being_purged_removes_only_their_membership(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    event = own_event(db, sam)
    join(db, sam, event, alex)
    act_as(db, alex.id)
    delete_user(db, alex.id)
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()
    assert db.query(EventMemberModel).count() == 0
    assert db.get(EventModel, event.id) is not None


def test_leaving_never_writes_the_event(db):
    """The member functions only read the event: none of the four SQL
    functions updates or deletes an events row."""
    source = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("account_event_invite_preview"):]
    source = source[:source.index("-- Definer functions run with their owner's rights")]
    assert "UPDATE events" not in source and "DELETE FROM events" not in source


# --- through the API -----------------------------------------------------------------

def signed_in(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}


def test_the_api_shows_names_never_emails_and_only_the_listed_fields(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    course = make_course(db, sam.id, "CPSC 310")
    event = own_event(db, sam, course_id=course.id)
    as_sam, as_alex = signed_in(sam), signed_in(alex)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        new = client.post(f"/api/calendar/{sam.id}/events/{event.id}/sharing/link", headers=as_sam).json()
        assert len(new["token"]) >= 30
        preview = client.post(f"/api/calendar/{alex.id}/shared-events/invites/preview",
                              json={"token": new["token"]}, headers=as_alex)
        accepted = client.post(f"/api/calendar/{alex.id}/shared-events/invites/accept",
                               json={"token": new["token"]}, headers=as_alex)
        listed = client.get(f"/api/calendar/{alex.id}/shared-events",
                            params={"start": "2026-10-19", "end": "2026-10-25"}, headers=as_alex)
        # A member has no way to change the event: its own routes refuse them.
        edit = client.patch(f"/api/calendar/{alex.id}/events/{event.id}", json={"title": "mine now"},
                            headers=as_alex)
        sharing_view = client.get(f"/api/calendar/{sam.id}/events/{event.id}/sharing", headers=as_sam)
    finally:
        app.main.app.dependency_overrides.clear()
    assert preview.json() == {"owner_name": "Sam", "title": "Study group", "starts_on": "2026-10-22"}
    assert accepted.json() == {"status": "accepted"}
    assert set(listed.json()[0]) == {"event_id", "owner_name", "title", "kind", "location", "notes",
                                     "starts_on", "start_time", "end_time", "member_names"}
    assert edit.status_code == 404 and fresh(db, event).title == "Study group"
    for response in (preview, listed, sharing_view):
        assert sam.email not in response.text and alex.email not in response.text
    assert [m["name"] for m in sharing_view.json()["members"]] == ["Alex"]


def test_an_event_you_are_not_on_answers_404_like_one_that_does_not_exist(db):
    sam, eve = person(db, "Sam"), person(db, "Eve")
    event = own_event(db, sam)
    as_eve = signed_in(eve)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        leaves = [client.delete(f"/api/calendar/{eve.id}/shared-events/{target}", headers=as_eve)
                  for target in (event.id, uuid.uuid4())]
        reads = [client.get(f"/api/calendar/{eve.id}/events/{target}/sharing", headers=as_eve)
                 for target in (event.id, uuid.uuid4())]
    finally:
        app.main.app.dependency_overrides.clear()
    assert [r.status_code for r in leaves] == [404, 404] and leaves[0].json() == leaves[1].json()
    assert [r.status_code for r in reads] == [404, 404] and reads[0].json() == reads[1].json()
