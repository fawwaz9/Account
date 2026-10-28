"""Exertion points and weekly goals (Phase 3 items 6 and 7).

The promises: points are hours x MET x weight x 10, worked out when logged and
never rewritten; weeks run Monday to Sunday in the student's own calendar; the goal
is the student's own and can be cleared; the suggestion is the last 4 weeks plus
10%, eased in an exam week, and nothing until there's history.
"""
import uuid
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import ActivityModel, EventModel
from app.Auth.services.session_service import create_access_token
from app.Fitness.schemas.fitness import ActivityIn
from app.Fitness.services import exertion_service as service
from conftest import make_user

#: A Wednesday.
TODAY = date(2026, 10, 28)
MONDAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(service, "user_today", lambda db, user_id, at=None: TODAY)


def student(db):
    user = make_user(db, f"s-{uuid.uuid4().hex[:6]}@example.com")
    act_as(db, user.id)
    return user


def logged(db, user, on, minutes=60, kind="run"):
    return service.log(db, user.id, ActivityIn(on_date=on, kind=kind, minutes=minutes))


@pytest.mark.parametrize(("minutes", "met", "weight", "expected"), [
    (60, 9.8, 1.0, 98), (30, 9.8, 1.0, 49), (45, 3.5, 1.0, 26), (1, 2.5, 1.0, 0), (600, 9.8, 1.0, 980),
    (60, 9.8, 0.5, 49),
])
def test_points_are_hours_times_met_times_weight_times_ten(minutes, met, weight, expected):
    assert service.points(minutes, met, weight) == expected


def test_every_kind_has_a_met_in_every_version():
    from app._database.models import ACTIVITY_KINDS
    for version, table in service.MET_BY_VERSION.items():
        assert set(table) == set(ACTIVITY_KINDS), version
    assert service.FORMULA_VERSION in service.MET_BY_VERSION


def test_an_activity_keeps_the_formula_it_was_logged_under(db):
    sam = student(db)
    run = logged(db, sam, TODAY, minutes=30)
    row = db.get(ActivityModel, run.id)
    assert (run.points, run.formula_version, row.met, row.weight, row.source) == (49, 1, 9.8, 1.0, "manual")


def test_a_later_formula_never_rewrites_an_earlier_row(db, monkeypatch):
    sam = student(db)
    old = logged(db, sam, TODAY, minutes=60)
    monkeypatch.setitem(service.MET_BY_VERSION, 2, {**service.MET_BY_VERSION[1], "run": 11.0})
    monkeypatch.setattr(service, "FORMULA_VERSION", 2)
    new = logged(db, sam, TODAY, minutes=60)
    db.expire_all()
    assert (db.get(ActivityModel, old.id).points, db.get(ActivityModel, old.id).formula_version) == (98, 1)
    assert (new.points, new.formula_version) == (110, 2)


def test_weeks_run_monday_to_sunday(db):
    sam = student(db)
    logged(db, sam, MONDAY, minutes=60)               # this week
    logged(db, sam, MONDAY - timedelta(days=1), 30)   # last Sunday: last week
    found = service.summary(db, sam.id)
    assert (found.week_start, found.this_week) == (MONDAY, 98)
    assert found.weeks[-1] == service.WeekPoints(week_start=MONDAY - timedelta(weeks=1), points=49)
    assert len(found.weeks) == 8 and found.weeks[0].week_start == MONDAY - timedelta(weeks=8)


def test_the_suggestion_needs_two_weeks_of_history(db):
    sam = student(db)
    logged(db, sam, MONDAY - timedelta(weeks=1))
    found = service.summary(db, sam.id)
    assert found.suggestion.points is None and "couple of weeks" in found.suggestion.reason


def test_the_suggestion_is_the_last_four_weeks_plus_ten_percent(db):
    sam = student(db)
    for weeks_back in (1, 2, 3, 4):
        logged(db, sam, MONDAY - timedelta(weeks=weeks_back), minutes=60)  # 98 a week
    logged(db, sam, MONDAY - timedelta(weeks=5), minutes=600)  # older than the window
    found = service.summary(db, sam.id)
    assert found.suggestion.points == 110  # 98 x 1.1 = 107.8, to the nearest 5
    assert found.suggestion.reason == "Your last 4 weeks, plus 10%."


def test_an_exam_week_eases_the_suggestion(db):
    sam = student(db)
    for weeks_back in (1, 2, 3, 4):
        logged(db, sam, MONDAY - timedelta(weeks=weeks_back), minutes=60)
    for day in (MONDAY + timedelta(days=2), MONDAY + timedelta(days=4)):
        db.add(EventModel(id=uuid.uuid4(), user_id=sam.id, title="Midterm", kind="midterm", starts_on=day,
                          start_time=time(9, 0), end_time=time(11, 0)))
    # A lecture the same week is not an exam.
    db.add(EventModel(id=uuid.uuid4(), user_id=sam.id, title="Lecture", kind="lecture", starts_on=MONDAY,
                      start_time=time(13, 0), end_time=time(14, 0)))
    db.commit()
    found = service.summary(db, sam.id)
    assert found.suggestion.points == 75  # 107.8 x 0.7 = 75.5, to the nearest 5
    assert found.suggestion.reason.startswith("2 exams this week")


@pytest.mark.parametrize(("history", "exams", "points"), [
    ([0, 0, 0, 0], 0, None), ([0, 0, 10, 0], 0, None), ([0, 0, 1, 1], 0, 5), ([40, 40, 40, 40], 1, 30),
])
def test_suggestions_round_and_never_drop_below_five(history, exams, points):
    assert service.suggest(history, exams).points == points


def test_the_goal_is_yours_and_can_be_cleared(db):
    sam = student(db)
    assert service.summary(db, sam.id).goal is None
    assert service.set_goal(db, sam.id, 150).goal == 150
    assert service.set_goal(db, sam.id, None).goal is None


def test_only_the_last_28_days_are_listed_newest_first(db):
    sam = student(db)
    logged(db, sam, TODAY - timedelta(days=30))
    a = logged(db, sam, TODAY - timedelta(days=3))
    b = logged(db, sam, TODAY)
    assert [r.id for r in service.summary(db, sam.id).recent] == [b.id, a.id]


def test_nobody_deletes_someone_elses_activity(db):
    sam, alex = student(db), student(db)
    theirs = logged(db, alex, TODAY)
    assert service.delete(db, sam.id, theirs.id) is False
    assert service.delete(db, alex.id, theirs.id) is True


def test_the_routes_log_read_set_and_delete(db):
    sam, alex = student(db), student(db)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        base = f"/api/fitness/{sam.id}"
        made = client.post(f"{base}/activities", headers=headers,
                           json={"on_date": TODAY.isoformat(), "kind": "swim", "minutes": 45, "note": " laps "})
        too_long = client.post(f"{base}/activities", headers=headers,
                               json={"on_date": TODAY.isoformat(), "kind": "swim", "minutes": 601})
        odd_kind = client.post(f"{base}/activities", headers=headers,
                               json={"on_date": TODAY.isoformat(), "kind": "napping", "minutes": 30})
        goal = client.put(f"{base}/exertion/goal", headers=headers, json={"goal": 200})
        read = client.get(f"{base}/exertion", headers=headers)
        foreign = client.get(f"/api/fitness/{alex.id}/exertion", headers=headers)
        gone = client.delete(f"{base}/activities/{made.json()['id']}", headers=headers)
    finally:
        app.main.app.dependency_overrides.clear()
    assert made.status_code == 200 and (made.json()["points"], made.json()["note"]) == (60, "laps")
    assert (too_long.status_code, odd_kind.status_code, foreign.status_code) == (422, 422, 403)
    assert goal.json()["goal"] == 200 and read.json()["this_week"] == 60
    assert gone.status_code == 200
