"""Cross-room correlations, non-financial (Phase 4 item 8, §4).

Pinned: Pearson's r by hand on a known series; the words for each strength;
silence until eight weeks hold both rooms; only complete weeks; the reading never
claims a cause; no money table is read (§13.3, proved on the queries); another
user's weeks never count.
"""
import re
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.main
from app._database.db import get_db
from app._database.models import ActivityModel, TaskModel
from app.Auth.dependencies import get_current_user
from app.Insights.services.correlation_service import NEEDED_WEEKS, correlations, pearson, reading, strength
from conftest import make_account, make_user

TODAY = date(2026, 11, 4)          # a Wednesday
LAST = date(2026, 10, 26)          # the last complete week's Monday

MONEY_TABLES = {
    "accounts", "transactions", "spend_categories", "budget_targets", "account_category_limits",
    "account_category_month_limits", "account_month_values", "sinking_funds", "sinking_contributions",
    "recurring_transactions", "tuition_payments", "tuition_deductions", "jobs", "shift_records",
    "paycheques", "paycheque_deductions", "imports", "saved_plans", "salary_shares", "salary_figures",
    "merchant_categories", "job_applications", "application_steps", "application_seasons",
}


def activity(db, user, on, points):
    db.add(ActivityModel(id=uuid.uuid4(), user_id=user.id, on_date=on, kind="run", minutes=30, met=8.0,
                         weight=1.0, points=points, formula_version=1))
    db.commit()


def finished(db, user, on, minutes=60, count=1):
    for _ in range(count):
        db.add(TaskModel(id=uuid.uuid4(), user_id=user.id, title="t", done=True,
                         completed_at=datetime.combine(on, time(12)), actual_minutes=minutes))
    db.commit()


def weeks_back(n):
    """The Mondays of the last n complete weeks, oldest first."""
    return [LAST - timedelta(weeks=n - 1 - i) for i in range(n)]


@pytest.fixture
def linked(db, user):
    """Ten weeks where points and tasks rise together: points 10k, tasks k."""
    for k, monday in enumerate(weeks_back(10), start=1):
        activity(db, user, monday + timedelta(days=1), 10 * k)
        finished(db, user, monday + timedelta(days=2), count=k)


# ------------------------------------------------------------------ the maths --

def test_pearson_by_hand():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0)
    # x = 1..4, y = 1, 3, 2, 4: r = 0.8
    assert pearson([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)
    assert pearson([5, 5, 5], [1, 2, 3]) is None


@pytest.mark.parametrize("r, word", [
    (None, "no clear link"), (0.19, "no clear link"), (-0.19, "no clear link"), (0.2, "weak"),
    (-0.39, "weak"), (0.4, "moderate"), (0.59, "moderate"), (0.6, "strong"), (-0.95, "strong"),
])
def test_strength_in_words(r, word):
    assert strength(r) == word


# ---------------------------------------------------------------- the reading --

def test_the_reading_counts_tasks_and_measures_work():
    assert "you tended to finish fewer tasks." in reading(-0.8, 12, "tasks")
    assert "you tended to finish less work." in reading(-0.8, 12, "work")
    assert "you tended to finish more tasks." in reading(0.8, 12, "tasks")


def test_weeks_that_rise_together_read_as_a_strong_link(db, user, linked):
    result = correlations(db, user.id, TODAY)

    assert result.ready and result.weeks_of_both == 10
    tasks = next(c for c in result.correlations if c.key == "tasks")
    assert (tasks.coefficient, tasks.strength, tasks.weeks) == (1.0, "strong", 10)
    assert tasks.reading.startswith("A strong link across 10 weeks")
    assert [p.academic for p in tasks.pairs] == list(range(1, 11))


def test_the_reading_never_claims_a_cause(db, user, linked):
    result = correlations(db, user.id, TODAY)

    for c in result.correlations:
        for word in ("because", "causes", "makes you", "leads to"):
            assert word not in c.reading.lower()
    assert "aren't proof" in result.caution


def test_silent_until_eight_weeks_of_both(db, user):
    for monday in weeks_back(NEEDED_WEEKS - 1):
        activity(db, user, monday, 20)
        finished(db, user, monday)

    result = correlations(db, user.id, TODAY)

    assert not result.ready and result.correlations == []
    assert result.weeks_of_both == NEEDED_WEEKS - 1


def test_one_room_alone_says_nothing(db, user):
    for monday in weeks_back(12):
        activity(db, user, monday, 20)

    result = correlations(db, user.id, TODAY)

    assert not result.ready and result.weeks_of_both == 0


def test_weeks_count_from_when_both_rooms_began(db, user):
    for monday in weeks_back(20):
        activity(db, user, monday, 20)
    for monday in weeks_back(9):
        finished(db, user, monday)

    assert correlations(db, user.id, TODAY).weeks_of_both == 9


def test_this_unfinished_week_is_left_out(db, user, linked):
    activity(db, user, TODAY, 999)
    finished(db, user, TODAY, count=50)

    tasks = next(c for c in correlations(db, user.id, TODAY).correlations if c.key == "tasks")

    assert tasks.pairs[-1].week_start == LAST and tasks.coefficient == 1.0


def test_a_side_that_never_changes_is_no_clear_link(db, user):
    for monday in weeks_back(10):
        activity(db, user, monday, 30)
        finished(db, user, monday, count=2)

    tasks = next(c for c in correlations(db, user.id, TODAY).correlations if c.key == "tasks")

    assert tasks.coefficient is None and tasks.strength == "no clear link"


# ---------------------------------------------------------- silo and others --

def test_no_money_table_is_read(db, user, linked):
    make_account(db, user.id, "Chequing")
    seen: list[str] = []
    bind = db.get_bind()

    def capture(_conn, _cursor, statement, *_args):
        seen.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        correlations(db, user.id, TODAY)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    touched = {name for sql in seen for name in re.findall(r'(?:from|join)\s+"?([a-z_]+)"?', sql)}
    assert {"activities", "tasks"} <= touched, touched
    assert not touched & MONEY_TABLES, touched & MONEY_TABLES


def test_another_users_weeks_never_count(db, user, linked):
    stranger = make_user(db, "stranger@example.com")
    for monday in weeks_back(10):
        activity(db, stranger, monday, 500)
        finished(db, stranger, monday, count=40)

    tasks = next(c for c in correlations(db, user.id, TODAY).correlations if c.key == "tasks")

    assert [p.academic for p in tasks.pairs] == list(range(1, 11))
    assert max(p.body for p in tasks.pairs) == 100


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, client):
    body = client.get(f"/api/fitness/{user.id}/correlations").json()

    assert body["ready"] is False and body["needed_weeks"] == NEEDED_WEEKS
