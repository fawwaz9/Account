"""Accountability partners and invite links (Phase 2 item 10, D16, D22).

Runs on SQLite and on Postgres: the cross-user steps (sharing.py) have a
definer-function path and a plain-query path, and both must mean the same.
Each person's steps are taken as that person (act_as), as a request would.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import InviteModel, PartnershipModel, TaskModel, utc_now
from app.Auth.dependencies import get_current_user
from app.Partners.services import partner_service as partners
from app.Users.services.user_service import DELETION_GRACE_DAYS, delete_user, purge_expired_users
from conftest import make_user


def person(db, name):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    return user


def invite(db, user):
    act_as(db, user.id)
    return partners.create_invite(db, user.id)


def accept(db, user, token):
    act_as(db, user.id)
    return partners.accept(db, user.id, token)


def pair(db, a, b):
    assert accept(db, b, invite(db, a).token) == "accepted"


def task(db, user, due, done):
    db.add(TaskModel(id=uuid.uuid4(), user_id=user.id, title="t", due_date=due, done=done, priority=3))
    db.commit()


# --- invites --------------------------------------------------------------------

def test_only_a_hash_of_the_token_is_kept(db):
    sam = person(db, "Sam")
    new = invite(db, sam)
    row = db.get(InviteModel, new.id)
    assert row.token_hash == partners.token_hash(new.token) and new.token not in row.token_hash
    assert row.expires_at - row.created_at == timedelta(days=7)


def test_a_preview_names_the_inviter_and_nothing_else(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    new = invite(db, sam)
    act_as(db, alex.id)
    found = partners.preview(db, alex.id, new.token)
    assert (found.inviter_name, found.kind) == ("Sam", "partner")
    assert partners.preview(db, alex.id, "not-a-real-token-at-all") is None


@pytest.mark.parametrize("spoil", ["expired", "revoked", "used"])
def test_a_dead_link_previews_and_accepts_nothing(db, spoil):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    new = invite(db, sam)
    row = db.get(InviteModel, new.id)
    if spoil == "expired":
        row.expires_at = utc_now() - timedelta(minutes=1)
        db.commit()
    elif spoil == "revoked":
        act_as(db, sam.id)
        assert partners.revoke_invite(db, sam.id, new.id)
    else:
        assert accept(db, kim, new.token) == "accepted"
    act_as(db, alex.id)
    assert partners.preview(db, alex.id, new.token) is None
    assert accept(db, alex, new.token) == "invalid"


def test_accepting_creates_both_sides_and_uses_the_link(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    new = invite(db, sam)
    assert accept(db, alex, new.token) == "accepted"
    rows = {(r.user_id, r.partner_id, r.partner_name) for r in db.query(PartnershipModel)}
    assert rows == {(sam.id, alex.id, "Alex"), (alex.id, sam.id, "Sam")}
    db.expire_all()
    assert db.get(InviteModel, new.id).used_by == alex.id


def test_your_own_link_and_a_second_partnership_are_refused(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    assert accept(db, sam, invite(db, sam).token) == "own"
    pair(db, sam, alex)
    assert accept(db, alex, invite(db, sam).token) == "already"
    assert db.query(PartnershipModel).count() == 2


def test_open_invites_are_capped(db):
    sam = person(db, "Sam")
    for _ in range(partners.MAX_OPEN_INVITES):
        invite(db, sam)
    with pytest.raises(partners.InviteLimit):
        invite(db, sam)


def test_you_can_revoke_only_your_own_invite(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    new = invite(db, sam)
    act_as(db, alex.id)
    assert partners.revoke_invite(db, alex.id, new.id) is False
    db.expire_all()
    assert db.get(InviteModel, new.id).revoked_at is None


# --- figures --------------------------------------------------------------------

MONDAY = date(2026, 10, 5)


def test_the_figure_is_this_weeks_share_done_and_the_run_of_good_weeks(db):
    sam = person(db, "Sam")
    for done in (True, True, True, False):                      # this week: 75%
        task(db, sam, MONDAY + timedelta(days=1), done)
    for weeks_back, results in ((1, (True, True)), (2, ()), (3, (True, True, True, True, False)), (4, (False,))):
        for done in results:                                    # 100%, quiet, 80%, 0%
            task(db, sam, MONDAY - timedelta(weeks=weeks_back), done)
    figure = partners.figure_for(db, sam.id, today=MONDAY + timedelta(days=2))
    assert (figure.week_percent, figure.streak_weeks) == (75.0, 2)


def test_a_week_with_nothing_due_has_no_percentage(db):
    sam = person(db, "Sam")
    assert partners.figure_for(db, sam.id, today=MONDAY).week_percent is None


def test_each_partner_sees_the_others_figure(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    pair(db, sam, alex)
    task(db, alex, date.today(), True)
    act_as(db, alex.id)
    partners.overview(db, alex.id)                 # Alex opens the app: their figure is written
    act_as(db, sam.id)
    [listed] = partners.overview(db, sam.id).partners
    assert (listed.name, listed.figure.week_percent) == ("Alex", 100.0)


def test_a_partner_who_has_not_opened_the_app_shows_no_figure_yet(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    pair(db, sam, alex)
    act_as(db, sam.id)
    [listed] = partners.overview(db, sam.id).partners
    assert listed.figure is None


def test_a_one_sided_row_shows_nothing(db):
    """The forgery: Sam writes a row of Sam's own naming Kim. Kim has a figure
    -- Kim partners with Alex -- but no row naming Sam, which only the accept
    function could write. Sam must see nothing of Kim's."""
    sam, kim, alex = person(db, "Sam"), person(db, "Kim"), person(db, "Alex")
    pair(db, kim, alex)
    task(db, kim, date.today(), True)
    act_as(db, kim.id)
    partners.overview(db, kim.id)                  # Kim's figure is now written, in Kim's row
    db.add(PartnershipModel(id=uuid.uuid4(), user_id=sam.id, partner_id=kim.id, partner_name="Kim"))
    db.commit()
    act_as(db, sam.id)
    [listed] = partners.overview(db, sam.id).partners
    assert listed.name == "Kim" and listed.figure is None


def test_a_row_naming_you_shows_nothing_unless_yours_names_them(db):
    """Kim writes a row of Kim's own naming Sam, with Kim's figure in it. Sam
    never agreed -- no row of Sam's names Kim -- so Sam is shown nothing."""
    from app._database.sharing import partner_figures
    sam, kim = person(db, "Sam"), person(db, "Kim")
    db.add(PartnershipModel(id=uuid.uuid4(), user_id=kim.id, partner_id=sam.id, partner_name="Sam",
                            week_percent=90.0, streak_weeks=3, figure_on=date.today()))
    db.commit()
    act_as(db, sam.id)
    assert partner_figures(db, sam.id) == {}
    # Not vacuous: once Sam's row names Kim, it is a partnership and shows.
    db.add(PartnershipModel(id=uuid.uuid4(), user_id=sam.id, partner_id=kim.id, partner_name="Kim"))
    db.commit()
    act_as(db, sam.id)
    assert partner_figures(db, sam.id)[kim.id].week_percent == 90.0


# --- ending ---------------------------------------------------------------------

@pytest.mark.parametrize("who_ends", ["inviter", "accepter"])
def test_either_side_can_end_it_and_both_rows_go(db, who_ends):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    pair(db, sam, alex)
    ender, other = (sam, alex) if who_ends == "inviter" else (alex, sam)
    act_as(db, ender.id)
    assert partners.end(db, ender.id, other.id) is True
    assert db.query(PartnershipModel).count() == 0
    act_as(db, other.id)
    assert partners.overview(db, other.id).partners == []


def test_nobody_can_end_a_partnership_they_are_not_in(db):
    sam, alex, kim = person(db, "Sam"), person(db, "Alex"), person(db, "Kim")
    pair(db, sam, alex)
    act_as(db, kim.id)
    assert partners.end(db, kim.id, alex.id) is False
    assert db.query(PartnershipModel).count() == 2


def test_purging_a_partner_removes_your_side_too(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    pair(db, sam, alex)
    act_as(db, alex.id)
    delete_user(db, alex.id)
    purge_expired_users(db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1))
    db.expire_all()
    assert db.query(PartnershipModel).count() == 0


# --- through the API ------------------------------------------------------------

def test_the_api_never_shows_a_partners_email(db):
    sam, alex = person(db, "Sam"), person(db, "Alex")
    pair(db, sam, alex)
    app.main.app.dependency_overrides[get_current_user] = lambda: sam
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        body = client.get(f"/api/partners/{sam.id}").text
        new = client.post(f"/api/partners/{sam.id}/invites").json()
        assert len(new["token"]) >= 30
        app.main.app.dependency_overrides[get_current_user] = lambda: alex
        preview = client.post(f"/api/partners/{alex.id}/invites/preview", json={"token": new["token"]}).json()
    finally:
        app.main.app.dependency_overrides.clear()
    assert alex.email not in body and "Alex" in body
    assert preview == {"inviter_name": "Sam", "kind": "partner"}
