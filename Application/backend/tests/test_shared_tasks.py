"""Shared tasks (Phase 2 item 9a, D23).

Runs on SQLite and on Postgres: every step a member takes (sharing.py) has a
definer-function path and a plain-query path, and both must mean the same.
Each person's steps are taken as that person (act_as), as a request would.

The rule under test throughout: a member sees the few fields D23 lists,
ticks and edits the text, and leaves -- and nothing else. Only the owner
deletes the task, changes its date or course, or changes who is on it.
"""
import re
import uuid
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import rls, sharing
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import (
    MAX_TASK_MEMBERS, RecurringTaskModel, TaskInviteModel, TaskMemberModel, TaskModel, utc_now,
)
from app.Auth.dependencies import get_current_user
from app.Partners.services import partner_service
from app.Tasks.schemas.sharing import SharedTaskUpdate
from app.Tasks.services import task_service
from app.Tasks.services import task_sharing_service as shares
from app.Users.services.user_service import DELETION_GRACE_DAYS, delete_user, purge_expired_users
from conftest import make_course, make_user


def person(db, name):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    return user


def own_task(db, user, title="Group report", **extra):
    fields = {"notes": "draft by Friday", "due_date": date(2026, 10, 20), "due_time": time(17, 0),
              "priority": 3, **extra}
    row = TaskModel(id=uuid.uuid4(), user_id=user.id, title=title, **fields)
    db.add(row)
    db.commit()
    return row


def link(db, owner, task):
    act_as(db, owner.id)
    return shares.new_link(db, owner.id, task.id)


def accept(db, user, token):
    act_as(db, user.id)
    return shares.accept(db, user.id, token)


def join(db, owner, task, member):
    assert accept(db, member, link(db, owner, task).token) == "accepted"


def seen_by(db, user):
    act_as(db, user.id)
    return shares.shared_with_me(db, user.id)


def fresh(db, task):
    db.expire_all()
    return db.get(TaskModel, task.id)


# --- links ----------------------------------------------------------------------

def test_only_a_hash_of_the_token_is_kept(db):
    sam = person(db, "Sam")
    task = own_task(db, sam)
    new = link(db, sam, task)
    row = db.query(TaskInviteModel).filter_by(task_id=task.id).one()
    assert row.token_hash == shares.token_hash(new.token) and new.token not in row.token_hash
    assert row.expires_at - row.created_at == timedelta(days=7)


def test_a_preview_names_the_owner_and_the_task_and_nothing_else(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    new = link(db, sam, task)
    act_as(db, alex.id)
    found = shares.preview(db, alex.id, new.token)
    assert (found.owner_name, found.title) == ("Sam", "Group report")
    assert shares.preview(db, alex.id, "not-a-real-token-at-all") is None


@pytest.mark.parametrize("spoil", ["expired", "cancelled", "replaced"])
def test_a_dead_link_previews_and_accepts_nothing(db, spoil):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    new = link(db, sam, task)
    act_as(db, sam.id)
    if spoil == "expired":
        row = db.query(TaskInviteModel).filter_by(task_id=task.id).one()
        row.expires_at = utc_now() - timedelta(minutes=1)
        db.commit()
    elif spoil == "cancelled":
        assert shares.cancel_link(db, sam.id, task.id) is True
    else:
        link(db, sam, task)  # a new link cancels the old one
    act_as(db, alex.id)
    assert shares.preview(db, alex.id, new.token) is None
    assert accept(db, alex, new.token) == "invalid"
    assert db.query(TaskMemberModel).count() == 0


def test_one_link_lets_several_people_join_with_their_names_copied(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    task = own_task(db, sam)
    new = link(db, sam, task)
    assert accept(db, alex, new.token) == "accepted"
    assert accept(db, kim, new.token) == "accepted"
    rows = db.query(TaskMemberModel).filter_by(task_id=task.id).all()
    assert {(r.member_id, r.member_name, r.owner_name) for r in rows} == {
        (alex.id, "Alex", "Sam"), (kim.id, "Kim", "Sam"),
    }


def test_your_own_link_and_joining_twice_change_nothing(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    new = link(db, sam, task)
    assert accept(db, sam, new.token) == "own"
    assert accept(db, alex, new.token) == "accepted"
    assert accept(db, alex, new.token) == "already"
    assert db.query(TaskMemberModel).count() == 1


def test_a_task_holds_at_most_the_limit(db):
    sam = person(db, "Sam")
    task = own_task(db, sam)
    new = link(db, sam, task)
    for n in range(MAX_TASK_MEMBERS):
        assert accept(db, person(db, f"M{n}"), new.token) == "accepted"
    assert accept(db, person(db, "OneTooMany"), new.token) == "full"
    assert db.query(TaskMemberModel).count() == MAX_TASK_MEMBERS


def test_the_limit_in_the_database_function_is_the_models(db):
    """The accept function cannot import a Python constant; hold the two together."""
    found = re.search(r"FROM task_members WHERE task_id = t\.id\) >= (\d+)", rls.FUNCTION_SQL)
    assert found and int(found.group(1)) == MAX_TASK_MEMBERS


def test_a_repeating_task_cannot_be_shared(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    rule = RecurringTaskModel(id=uuid.uuid4(), user_id=sam.id, title="Chores", recur_freq="weekly",
                              starts_on=date(2026, 10, 1))
    db.add(rule)
    db.commit()
    task = own_task(db, sam, title="Chores", recurring_id=rule.id, occurrence_date=date(2026, 10, 20))
    act_as(db, sam.id)
    with pytest.raises(shares.NotShareable):
        shares.new_link(db, sam.id, task.id)
    assert shares.sharing_of(db, sam.id, task.id).shareable is False
    # And if a row says otherwise anyway -- a link and a member written past the
    # API -- the functions still ignore the task.
    token = "planted-link-on-a-repeating-task"
    db.add(TaskInviteModel(id=uuid.uuid4(), task_id=task.id, token_hash=shares.token_hash(token),
                           created_at=utc_now(), expires_at=utc_now() + timedelta(days=1)))
    db.add(TaskMemberModel(id=uuid.uuid4(), task_id=task.id, member_id=alex.id, member_name="Alex",
                           owner_name="Sam"))
    db.commit()
    act_as(db, alex.id)
    assert shares.preview(db, alex.id, token) is None
    assert seen_by(db, alex) == []
    kim = person(db, "Kim")
    assert accept(db, kim, token) == "invalid"
    assert db.query(TaskMemberModel).filter_by(member_id=kim.id).count() == 0
    act_as(db, alex.id)
    assert sharing.set_shared_task_done(db, alex.id, task.id, True) is False
    assert fresh(db, task).done is False


# --- what a member sees -----------------------------------------------------------

def test_a_member_sees_the_listed_fields_and_who_else_is_on_it(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    course = make_course(db, sam.id, "CPSC 310")
    task = own_task(db, sam, course_id=course.id, estimated_minutes=90, tags=["secret-tag"], priority=5)
    join(db, sam, task, alex)
    join(db, sam, task, kim)
    [mine] = seen_by(db, alex)
    assert mine.model_dump() == {
        "task_id": task.id, "owner_name": "Sam", "title": "Group report", "notes": "draft by Friday",
        "due_date": date(2026, 10, 20), "due_time": time(17, 0), "done": False, "completed_at": None,
        "member_names": ["Alex", "Kim"],
    }


def test_someone_not_on_the_task_sees_and_changes_nothing(db):
    sam, alex, eve = person(db, "Sam"), person(db, "Alex"), person(db, "Eve")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    assert seen_by(db, eve) == []
    act_as(db, eve.id)
    assert shares.update_shared(db, eve.id, task.id, SharedTaskUpdate(done=True, title="mine now")) is None
    act_as(db, eve.id)
    assert sharing.set_shared_task_done(db, eve.id, task.id, True) is False
    act_as(db, eve.id)
    assert sharing.edit_shared_task(db, eve.id, task.id, "mine now", None) is False
    act_as(db, eve.id)
    assert shares.leave(db, eve.id, task.id) is False
    row = fresh(db, task)
    assert (row.done, row.title) == (False, "Group report")
    assert db.query(TaskMemberModel).count() == 1


# --- what a member may do -----------------------------------------------------------

def test_one_tick_closes_it_for_everyone_and_unticking_reopens_it(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    act_as(db, alex.id)
    assert shares.update_shared(db, alex.id, task.id, SharedTaskUpdate(done=True)).done is True
    row = fresh(db, task)
    assert row.done and row.archived and row.completed_at is not None
    act_as(db, sam.id)
    assert all(t.id != task.id for t in task_service.list_tasks(db, sam.id)), "done leaves the owner's open list"
    act_as(db, alex.id)
    assert shares.update_shared(db, alex.id, task.id, SharedTaskUpdate(done=False)).done is False
    row = fresh(db, task)
    assert (row.done, row.archived, row.completed_at) == (False, False, None)


def test_a_member_edits_the_text_and_nothing_else(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    course = make_course(db, sam.id, "CPSC 310")
    task = own_task(db, sam, course_id=course.id, priority=5)
    join(db, sam, task, alex)
    act_as(db, alex.id)
    updated = shares.update_shared(db, alex.id, task.id, SharedTaskUpdate(title="  Final report  ", notes=None))
    assert (updated.title, updated.notes) == ("Final report", None)
    row = fresh(db, task)
    assert (row.title, row.notes, row.course_id, row.priority, row.due_date) == (
        "Final report", None, course.id, 5, date(2026, 10, 20))


def test_the_text_limits_hold_in_the_database_too(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    for title, notes in (("   ", None), ("x" * 201, None), ("ok", "n" * 2001)):
        act_as(db, alex.id)
        assert sharing.edit_shared_task(db, alex.id, task.id, title, notes) is False, (title[:5], notes)
    assert fresh(db, task).title == "Group report"


def test_leaving_takes_only_you_off(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    join(db, sam, task, kim)
    act_as(db, alex.id)
    assert shares.leave(db, alex.id, task.id) is True
    assert seen_by(db, alex) == []
    assert [t.member_names for t in seen_by(db, kim)] == [["Kim"]]
    act_as(db, alex.id)
    assert sharing.set_shared_task_done(db, alex.id, task.id, True) is False


# --- what only the owner may do --------------------------------------------------------

def test_the_owner_sees_who_is_on_it_and_removing_someone_cuts_them_off_at_once(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    act_as(db, sam.id)
    found = shares.sharing_of(db, sam.id, task.id)
    assert [m.name for m in found.members] == ["Alex"] and found.link is not None
    assert task_service.get_task(db, sam.id, task.id).shared_with == ["Alex"]
    act_as(db, sam.id)
    assert shares.remove_member(db, sam.id, task.id, found.members[0].id) is True
    assert seen_by(db, alex) == []
    act_as(db, alex.id)
    assert sharing.set_shared_task_done(db, alex.id, task.id, True) is False


def test_a_member_cannot_manage_someone_elses_task(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    join(db, sam, task, kim)
    kims_row = db.query(TaskMemberModel).filter_by(member_id=kim.id).one()
    act_as(db, alex.id)
    assert shares.sharing_of(db, alex.id, task.id) is None
    assert shares.new_link(db, alex.id, task.id) is None
    assert shares.cancel_link(db, alex.id, task.id) is False
    assert shares.remove_member(db, alex.id, task.id, kims_row.id) is False
    assert task_service.delete_task(db, alex.id, task.id) is None
    assert db.query(TaskMemberModel).count() == 2 and fresh(db, task) is not None


def test_deleting_the_task_ends_every_membership_and_link(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    act_as(db, sam.id)
    task_service.delete_task(db, sam.id, task.id)
    assert db.query(TaskMemberModel).count() == 0 and db.query(TaskInviteModel).count() == 0
    assert seen_by(db, alex) == []


# --- accounts going (D17) -----------------------------------------------------------

def purge(db, user):
    act_as(db, user.id)
    delete_user(db, user.id)
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()


def test_an_owner_being_deleted_hides_the_task_at_once_and_their_purge_removes_it(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    new = link(db, sam, task)
    assert accept(db, alex, new.token) == "accepted"
    act_as(db, sam.id)
    delete_user(db, sam.id)  # the grace period: restorable, but not shown
    assert seen_by(db, alex) == []
    act_as(db, alex.id)
    assert shares.preview(db, alex.id, new.token) is None
    kim = person(db, "Kim")
    assert accept(db, kim, new.token) == "invalid", "nobody joins the task of an account being deleted"
    act_as(db, alex.id)
    assert sharing.set_shared_task_done(db, alex.id, task.id, True) is False
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()
    assert db.get(TaskModel, task.id) is None
    assert db.query(TaskMemberModel).count() == 0


def test_a_member_being_purged_removes_only_their_membership(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    task = own_task(db, sam)
    join(db, sam, task, alex)
    purge(db, alex)
    assert db.query(TaskMemberModel).count() == 0
    assert db.get(TaskModel, task.id) is not None


# --- what a shared task feeds -------------------------------------------------------

def test_a_shared_task_counts_toward_its_owners_figure_alone(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    today = date(2026, 10, 14)
    task = own_task(db, sam)
    task.due_date = today
    db.commit()
    join(db, sam, task, alex)
    act_as(db, alex.id)
    shares.update_shared(db, alex.id, task.id, SharedTaskUpdate(done=True))
    assert partner_service.figure_for(db, alex.id, today).week_percent is None
    assert partner_service.figure_for(db, sam.id, today).week_percent == 100.0


# --- through the API -----------------------------------------------------------------

def test_the_api_shows_names_never_emails_and_only_the_listed_fields(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    course = make_course(db, sam.id, "CPSC 310")
    task = own_task(db, sam, course_id=course.id)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        app.main.app.dependency_overrides[get_current_user] = lambda: sam
        new = client.post(f"/api/tasks/{sam.id}/tasks/{task.id}/sharing/link").json()
        assert len(new["token"]) >= 30
        app.main.app.dependency_overrides[get_current_user] = lambda: alex
        preview = client.post(f"/api/tasks/{alex.id}/shared-tasks/invites/preview", json={"token": new["token"]})
        accepted = client.post(f"/api/tasks/{alex.id}/shared-tasks/invites/accept", json={"token": new["token"]})
        listed = client.get(f"/api/tasks/{alex.id}/shared-tasks")
        # Fields a member may not change are ignored, not applied.
        patched = client.patch(f"/api/tasks/{alex.id}/shared-tasks/{task.id}",
                               json={"done": True, "due_date": "2030-01-01", "course_id": None})
        blank = client.patch(f"/api/tasks/{alex.id}/shared-tasks/{task.id}", json={"title": "   "})
        app.main.app.dependency_overrides[get_current_user] = lambda: sam
        sharing_view = client.get(f"/api/tasks/{sam.id}/tasks/{task.id}/sharing")
        owners_task = client.get(f"/api/tasks/{sam.id}/tasks/{task.id}")
    finally:
        app.main.app.dependency_overrides.clear()
    assert preview.json() == {"owner_name": "Sam", "title": "Group report"}
    assert accepted.json() == {"status": "accepted"}
    assert set(listed.json()[0]) == {"task_id", "owner_name", "title", "notes", "due_date", "due_time",
                                     "done", "completed_at", "member_names"}
    assert patched.status_code == 200 and blank.status_code == 422
    row = fresh(db, task)
    assert row.done and row.due_date == date(2026, 10, 20) and row.course_id == course.id
    for response in (preview, listed, patched, sharing_view, owners_task):
        assert sam.email not in response.text and alex.email not in response.text
    assert [m["name"] for m in sharing_view.json()["members"]] == ["Alex"]
    assert owners_task.json()["shared_with"] == ["Alex"]


def test_a_task_you_are_not_on_answers_404_like_one_that_does_not_exist(db):
    sam, eve = person(db, "Sam"), person(db, "Eve")
    task = own_task(db, sam)
    app.main.app.dependency_overrides[get_db] = lambda: db
    app.main.app.dependency_overrides[get_current_user] = lambda: eve
    try:
        client = TestClient(app.main.app)
        answers = [
            client.patch(f"/api/tasks/{eve.id}/shared-tasks/{target}", json={"done": True})
            for target in (task.id, uuid.uuid4())
        ]
        sharing_reads = [client.get(f"/api/tasks/{eve.id}/tasks/{target}/sharing") for target in (task.id, uuid.uuid4())]
    finally:
        app.main.app.dependency_overrides.clear()
    assert [a.status_code for a in answers] == [404, 404] and answers[0].json() == answers[1].json()
    assert [r.status_code for r in sharing_reads] == [404, 404] and sharing_reads[0].json() == sharing_reads[1].json()
