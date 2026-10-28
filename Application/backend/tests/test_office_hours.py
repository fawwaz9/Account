"""The office-hours radar (Phase 3 item 11, D11), on SQLite and Postgres.

The promises: a check-in is the caller's own row, made on their own course, at
their local weekday and hour; a second tap within half an hour changes the first;
a slot is counted from each person's latest check-in in the last 120 days, live
accounts only, and never below the floor; and the course page reads only the
course its own course is counted under.
"""
import re
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import aggregates, rls
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import (
    COHORT_FLOOR, OFFICE_HOUR_WINDOW_DAYS, CourseModel, OfficeHourCheckinModel, OfficeHourSlotModel, utc_now,
)
from app.Auth.services.session_service import create_access_token
from app.Grades.services import class_figures_service, office_hours_service as service
from conftest import make_user


def student(db, name="sam", zone=None):
    user = make_user(db, f"{name}-{uuid.uuid4().hex[:6]}@example.com")
    if zone:
        user.preferences = {**(user.preferences or {}), "timezone": zone}
    db.commit()
    act_as(db, user.id)
    return user


def course(db, user, code="CPSC 221", **extra):
    row = CourseModel(id=uuid.uuid4(), user_id=user.id, code=code, name="x", semester="Fall", year=3,
                      credits=4.0, **extra)
    db.add(row)
    db.commit()
    return row


def checkin(db, user, key="CPSC 221", weekday=1, hour=14, wait="long", ago=timedelta(days=1)):
    """A check-in written as the service would have, `ago` in the past."""
    row = course(db, user, code=f"{key} {uuid.uuid4().hex[:4]}")
    db.add(OfficeHourCheckinModel(user_id=user.id, course_id=row.id, course_key=key, weekday=weekday, hour=hour,
                                  wait=wait, checked_at=utc_now() - ago))
    db.commit()


def people(db, n, **kwargs):
    for i in range(n):
        checkin(db, make_user(db, f"p-{uuid.uuid4().hex[:8]}@example.com"), **kwargs)


def slots(db, key="CPSC 221"):
    act_as(db, make_user(db, f"reader-{uuid.uuid4().hex[:6]}@example.com").id)
    return aggregates.office_hours(db, key)


# --- checking in ---------------------------------------------------------------------

def test_a_check_in_is_kept_at_your_local_weekday_and_hour(db, monkeypatch):
    sam = student(db, zone="America/Vancouver")
    row = course(db, sam)
    # 2026-10-27 22:30 UTC is Tuesday 15:30 in Vancouver.
    monkeypatch.setattr(service, "user_now",
                        lambda db, user_id: datetime(2026, 10, 27, 15, 30))
    saved = service.check_in(db, sam.id, row.id, "short")
    assert (saved.weekday, saved.hour, saved.wait, saved.course_key) == (1, 15, "short", "CPSC 221")
    assert saved.user_id == sam.id


def test_a_second_tap_within_half_an_hour_changes_the_first(db):
    sam = student(db)
    row = course(db, sam)
    first = service.check_in(db, sam.id, row.id, "short")
    second = service.check_in(db, sam.id, row.id, "long")
    assert second.id == first.id and second.wait == "long"
    assert db.query(OfficeHourCheckinModel).count() == 1


def test_after_half_an_hour_it_is_a_new_visit(db):
    sam = student(db)
    row = course(db, sam)
    first = service.check_in(db, sam.id, row.id, "short")
    first.checked_at = utc_now() - timedelta(minutes=service.MERGE_MINUTES + 1)
    db.commit()
    service.check_in(db, sam.id, row.id, "none")
    assert db.query(OfficeHourCheckinModel).count() == 2


def test_transfer_credit_and_codes_that_arent_courses_cant_check_in(db):
    sam = student(db)
    for row in (course(db, sam, code="CPSC 100", transfer_credit=True), course(db, sam, code="Study group")):
        with pytest.raises(service.CheckInError):
            service.check_in(db, sam.id, row.id, "long")
    assert db.query(OfficeHourCheckinModel).count() == 0


def test_nobody_checks_in_to_or_undoes_someone_elses(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    theirs = course(db, alex)
    act_as(db, sam.id)
    assert service.check_in(db, sam.id, theirs.id, "long") is None
    act_as(db, alex.id)
    kept = service.check_in(db, alex.id, theirs.id, "long")
    act_as(db, sam.id)
    assert service.remove(db, sam.id, kept.id) is False
    act_as(db, alex.id)
    assert service.remove(db, alex.id, kept.id) is True


def test_deleting_the_course_takes_its_check_ins(db):
    sam = student(db)
    row = course(db, sam)
    service.check_in(db, sam.id, row.id, "long")
    db.delete(row)
    db.commit()
    assert db.query(OfficeHourCheckinModel).count() == 0


# --- counting --------------------------------------------------------------------------

def test_a_slot_at_the_floor_is_counted_and_read(db):
    people(db, 3, wait="long")
    people(db, 2, wait="short")
    assert aggregates.recount_office_hours(db) == 1
    [slot] = slots(db)
    assert (slot.weekday, slot.hour, slot.people, slot.long_votes, slot.short_votes, slot.none_votes) == \
        (1, 14, 5, 3, 2, 0)


def test_below_the_floor_no_slot_is_written(db):
    people(db, COHORT_FLOOR - 1)
    assert aggregates.recount_office_hours(db) == 0
    assert db.query(OfficeHourSlotModel).count() == 0


def test_one_vote_per_person_their_latest(db):
    regular = make_user(db, "regular@example.com")
    for days, wait in ((3, "none"), (2, "none"), (1, "long")):
        checkin(db, regular, wait=wait, ago=timedelta(days=days))
    people(db, COHORT_FLOOR - 2, wait="long")
    assert aggregates.recount_office_hours(db) == 0, "four people, however many visits"
    people(db, 1, wait="long")
    aggregates.recount_office_hours(db)
    assert [(s.people, s.long_votes, s.none_votes) for s in slots(db)] == [(COHORT_FLOOR, COHORT_FLOOR, 0)]


def test_old_check_ins_and_deleted_accounts_are_left_out(db):
    people(db, COHORT_FLOOR - 1)
    people(db, 1, ago=timedelta(days=OFFICE_HOUR_WINDOW_DAYS + 1))
    gone = make_user(db, "gone@example.com")
    checkin(db, gone)
    gone.deleted_at = utc_now()
    db.commit()
    assert aggregates.recount_office_hours(db) == 0


def test_slots_and_courses_are_kept_apart(db):
    people(db, COHORT_FLOOR, hour=10)
    people(db, COHORT_FLOOR, hour=15)
    people(db, COHORT_FLOOR, key="MATH 200", hour=10)
    assert aggregates.recount_office_hours(db) == 3
    assert [s.hour for s in slots(db)] == [10, 15]
    assert [s.hour for s in slots(db, "MATH 200")] == [10]


def test_the_floor_and_window_in_the_functions_are_the_models():
    for name in ("account_recount_office_hours", "account_office_hours"):
        body = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index(f"FUNCTION {name}("):]
        body = body[:body.index("$$;")]
        assert set(re.findall(r">= (\d+)", body)) == {str(COHORT_FLOOR)}, name
    recount = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_recount_office_hours("):]
    assert f"interval '{OFFICE_HOUR_WINDOW_DAYS} days'" in recount[:recount.index("$$;")]


@pytest.mark.parametrize(("votes", "read"), [
    ((1, 1, 3), "long"), ((1, 3, 1), "short"), ((3, 1, 1), "none"), ((2, 1, 2), "long"), ((2, 2, 1), "short"),
])
def test_a_slot_reads_as_most_people_found_it_the_busier_on_a_tie(votes, read):
    none, short, long = votes
    assert service.reading(aggregates.Slot(1, 14, sum(votes), none, short, long)) == read


# --- on the course page, and the routes -------------------------------------------------

def test_the_course_page_lists_the_slots_with_their_reading(db):
    people(db, 4, wait="long")
    people(db, 1, wait="none")
    aggregates.recount_office_hours(db)
    sam = student(db)
    row = course(db, sam)
    found = class_figures_service.class_figures(db, sam.id, row.id).office_hours
    assert [(s.weekday, s.hour, s.people, s.reading) for s in found] == [(1, 14, 5, "long")]


def test_the_routes_check_in_undo_and_refuse_someone_elses_course(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    mine, theirs = course(db, sam), course(db, alex)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        made = client.post(f"/api/grades/{sam.id}/courses/{mine.id}/office-hours", headers=headers,
                           json={"wait": "short"})
        other = client.post(f"/api/grades/{sam.id}/courses/{theirs.id}/office-hours", headers=headers,
                            json={"wait": "short"})
        odd = client.post(f"/api/grades/{sam.id}/courses/{mine.id}/office-hours", headers=headers,
                          json={"wait": "huge"})
        undone = client.delete(f"/api/grades/{sam.id}/office-hours/{made.json()['id']}", headers=headers)
        again = client.delete(f"/api/grades/{sam.id}/office-hours/{made.json()['id']}", headers=headers)
    finally:
        app.main.app.dependency_overrides.clear()
    assert made.status_code == 200 and made.json()["wait"] == "short"
    assert (other.status_code, odd.status_code, undone.status_code, again.status_code) == (404, 422, 200, 404)


def test_the_read_checks_the_floor_again_whatever_the_table_holds(db):
    db.add(OfficeHourSlotModel(course_key="CPSC 221", weekday=1, hour=14, people=COHORT_FLOOR - 1, none_votes=0,
                               short_votes=0, long_votes=COHORT_FLOOR - 1))
    db.commit()
    assert slots(db) == []
