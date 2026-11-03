"""The deadline spending guard, detection half (Phase 4 item 13, §13.5).

Pinned: crunch weeks against your own threshold; tasks counted whether done or
not; the lift rule (above 1.5x, over 3+ crunch weeks, by $5+); silence before two
crunch weeks; the week ahead only within seven days and never the week under way;
uncounted accounts and other users' rows left out.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CrunchAllocationModel, EventModel, TaskModel, TransactionModel
from app.Auth.dependencies import get_current_user
from app.Finances.schemas.guard import AllocateIn, DismissIn
from app.Finances.services.budget_service import delete_category
from app.Finances.services.guard_service import (
    CRUNCH_FLOOR, DISMISSALS_TO_STOP, NEEDED_CRUNCH_WEEKS, allocate, dismiss, spending_guard, threshold, weekly_load,
)
from conftest import make_account, make_category, make_user

TODAY = date(2026, 11, 4)       # a Wednesday
THIS_WEEK = date(2026, 11, 2)
NEXT_WEEK = date(2026, 11, 9)


def monday(weeks_ago):
    return THIS_WEEK - timedelta(weeks=weeks_ago)


def exam(db, user, on, kind="midterm"):
    db.add(EventModel(id=uuid.uuid4(), user_id=user.id, title=kind, kind=kind, starts_on=on))
    db.commit()


def spend(db, user, account, category, on, amount):
    db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
                            amount=-amount, description="x", occurred_on=on, category_id=category.id))
    db.commit()


@pytest.fixture
def money(db, user):
    account = make_account(db, user.id, "Chequing")
    return account, make_category(db, user.id, "Delivery"), make_category(db, user.id, "Groceries")


@pytest.fixture
def history(db, user, money):
    """Twelve weeks: a deadline every week (load 1), two midterms in weeks 2, 5, 8 (load 7).

    Delivery: $40 in a usual week, $90 in a crunch week. Groceries: $60 every week.
    """
    account, delivery, groceries = money
    for w in range(1, 13):
        start = monday(w)
        db.add(EventModel(id=uuid.uuid4(), user_id=user.id, title="lab", kind="deadline", starts_on=start))
        crunchy = w in (2, 5, 8)
        if crunchy:
            exam(db, user, start + timedelta(days=1))
            exam(db, user, start + timedelta(days=3))
        spend(db, user, account, delivery, start + timedelta(days=2), 90.0 if crunchy else 40.0)
        spend(db, user, account, groceries, start + timedelta(days=4), 60.0)
    db.commit()
    return money


# ------------------------------------------------------------- crunch weeks --

def test_the_threshold_is_yours():
    assert threshold([0, 1, 1, 1, 7]) == CRUNCH_FLOOR       # twice the median week is 2
    assert threshold([4, 4, 5, 6, 12]) == 10                # twice the median of 5
    assert threshold([0, 0, 0, 5]) == CRUNCH_FLOOR          # exam weeks alone still count
    assert threshold([0, 0]) == float("inf")


def test_tasks_count_whether_done_or_not(db, user):
    db.add(TaskModel(id=uuid.uuid4(), user_id=user.id, title="a", due_date=monday(3), done=True))
    db.add(TaskModel(id=uuid.uuid4(), user_id=user.id, title="b", due_date=monday(3), done=False))
    db.add(TaskModel(id=uuid.uuid4(), user_id=user.id, title="c", due_date=monday(3), archived=True))
    db.commit()

    week = weekly_load(db, user.id, monday(3), monday(3))[monday(3)]

    assert (week["tasks"], week["weight"]) == (2, 2)


def test_finds_the_crunch_weeks(db, user, history):
    assert spending_guard(db, user.id, TODAY).crunch_weeks == 3


# -------------------------------------------------------------------- lifts --

def test_a_category_that_spikes_in_crunch_weeks_is_named(db, user, history):
    result = spending_guard(db, user.id, TODAY)

    (lift,) = result.lifts
    assert (lift.category, lift.crunch_weekly, lift.usual_weekly, lift.crunch_weeks) == ("Delivery", 90.0, 40.0, 3)
    assert lift.lift == 2.2


def test_a_category_that_doesnt_spike_isnt(db, user, history):
    assert "Groceries" not in {c.category for c in spending_guard(db, user.id, TODAY).lifts}


def test_a_categorised_transfer_is_not_spending_here(db, user, history):
    """D27: a transfer can carry a category, but moving money is not a crunch-week spike."""
    account, _, groceries = history
    for w in (2, 5, 8):
        db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="transfer",
                                amount=-500.0, description="x", occurred_on=monday(w), category_id=groceries.id))
    db.commit()

    assert "Groceries" not in {c.category for c in spending_guard(db, user.id, TODAY).lifts}


def test_two_crunch_weeks_speak_but_name_no_category(db, user, money):
    account, delivery, _ = money
    for w in range(1, 9):
        db.add(EventModel(id=uuid.uuid4(), user_id=user.id, title="lab", kind="deadline", starts_on=monday(w)))
        if w in (2, 5):
            exam(db, user, monday(w), "final")
            exam(db, user, monday(w) + timedelta(days=1), "final")
        spend(db, user, account, delivery, monday(w), 90.0 if w in (2, 5) else 40.0)

    result = spending_guard(db, user.id, TODAY)

    assert result.ready and result.crunch_weeks == 2
    assert result.lifts == []


def test_a_small_gap_is_not_a_spike(db, user, money):
    account, delivery, _ = money
    for w in range(1, 13):
        db.add(EventModel(id=uuid.uuid4(), user_id=user.id, title="lab", kind="deadline", starts_on=monday(w)))
        if w in (2, 5, 8):
            exam(db, user, monday(w), "final")
        spend(db, user, account, delivery, monday(w), 7.0 if w in (2, 5, 8) else 3.0)  # $4 more

    assert spending_guard(db, user.id, TODAY).lifts == []


def test_uncounted_accounts_are_left_out(db, user, history):
    _, delivery, _ = history
    hidden = make_account(db, user.id, "Joint")
    hidden.counts_toward_net_worth = False
    db.commit()
    for w in (1, 3, 4, 6, 7, 9):
        spend(db, user, hidden, delivery, monday(w), 500.0)

    (lift,) = spending_guard(db, user.id, TODAY).lifts
    assert lift.usual_weekly == 40.0


# --------------------------------------------------------------- silence --

def test_silent_before_two_crunch_weeks(db, user, money):
    account, delivery, _ = money
    exam(db, user, monday(3), "final")
    for w in range(1, 6):
        spend(db, user, account, delivery, monday(w), 100.0)

    result = spending_guard(db, user.id, TODAY)

    assert not result.ready and result.crunch_weeks == 1 and result.needed_crunch_weeks == NEEDED_CRUNCH_WEEKS
    assert result.lifts == [] and result.upcoming is None


# ---------------------------------------------------------- the week ahead --

def test_a_crunch_week_ahead_is_named_within_seven_days(db, user, history):
    exam(db, user, NEXT_WEEK + timedelta(days=1))
    exam(db, user, NEXT_WEEK + timedelta(days=2), "final")

    upcoming = spending_guard(db, user.id, TODAY).upcoming

    assert (upcoming.starts_on, upcoming.days_away, upcoming.exams) == (NEXT_WEEK, 5, 2)


def test_too_far_ahead_says_nothing_yet(db, user, history):
    exam(db, user, NEXT_WEEK + timedelta(days=1))
    exam(db, user, NEXT_WEEK + timedelta(days=2), "final")

    # From the Sunday before last, next week's Monday is 8 days away.
    assert spending_guard(db, user.id, NEXT_WEEK - timedelta(days=8)).upcoming is None


def test_never_during_the_crunch(db, user, history):
    exam(db, user, THIS_WEEK + timedelta(days=4))
    exam(db, user, THIS_WEEK + timedelta(days=5), "final")

    assert spending_guard(db, user.id, TODAY).upcoming is None


def test_another_users_rows_never_count(db, user, history):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_account(db, stranger.id, "Theirs")
    their_cat = make_category(db, stranger.id, "Delivery")
    for w in range(1, 13):
        exam(db, stranger, monday(w), "final")
        spend(db, stranger, theirs, their_cat, monday(w), 999.0)

    result = spending_guard(db, user.id, TODAY)

    assert result.crunch_weeks == 3
    (lift,) = result.lifts
    assert lift.crunch_weekly == 90.0


def test_a_stray_row_on_my_category_is_still_not_mine(db, user, history):
    """Defence in depth: a stranger's spending that names my category never counts."""
    _, delivery, _ = history
    stranger = make_user(db, "stray@example.com")
    theirs = make_account(db, stranger.id, "Theirs")
    for w in (1, 3, 4, 6, 7, 9):
        spend(db, stranger, theirs, delivery, monday(w), 999.0)

    (lift,) = spending_guard(db, user.id, TODAY).lifts
    assert lift.usual_weekly == 40.0


# ------------------------------------------------- setting aside, waving off --

@pytest.fixture
def ahead(db, user, history):
    """A crunch week next week."""
    exam(db, user, NEXT_WEEK + timedelta(days=1))
    exam(db, user, NEXT_WEEK + timedelta(days=2), "final")
    return history


def test_setting_money_aside_for_the_week_ahead(db, user, ahead):
    _, delivery, _ = ahead

    allocate(db, user.id, AllocateIn(category_id=delivery.id, week_start=NEXT_WEEK, amount=60), TODAY)
    allocate(db, user.id, AllocateIn(category_id=delivery.id, week_start=NEXT_WEEK, amount=75), TODAY)

    result = spending_guard(db, user.id, TODAY)
    (lift,) = result.lifts
    assert (lift.set_aside, lift.dismissed) == (75.0, False)
    assert db.query(CrunchAllocationModel).count() == 1
    # A week not yet over has no report card.
    assert (result.report_week, result.report) == (None, [])


def test_waving_it_off_and_three_times_stops_it(db, user, ahead):
    _, delivery, _ = ahead
    dismiss(db, user.id, DismissIn(category_id=delivery.id, week_start=NEXT_WEEK), TODAY)
    assert spending_guard(db, user.id, TODAY).lifts[0].dismissed is True

    for w in range(1, DISMISSALS_TO_STOP):
        db.add(CrunchAllocationModel(id=uuid.uuid4(), user_id=user.id, category_id=delivery.id,
                                     week_start=monday(w * 3), dismissed=True))
    db.commit()

    assert spending_guard(db, user.id, TODAY).lifts == []


def test_the_report_card_follows_the_week(db, user, ahead):
    account, delivery, _ = ahead
    db.add(CrunchAllocationModel(id=uuid.uuid4(), user_id=user.id, category_id=delivery.id,
                                 week_start=monday(2), amount=60.0))
    db.commit()

    result = spending_guard(db, user.id, TODAY)

    assert result.report_week == monday(2)
    (line,) = result.report
    assert (line.category, line.set_aside, line.spent) == ("Delivery", 60.0, 90.0)


def test_only_your_categories_and_only_this_week_or_next(db, user, ahead):
    stranger = make_user(db, "stranger@example.com")
    theirs = make_category(db, stranger.id, "Theirs")
    _, delivery, _ = ahead

    with pytest.raises(LookupError):
        allocate(db, user.id, AllocateIn(category_id=theirs.id, week_start=NEXT_WEEK, amount=10), TODAY)
    with pytest.raises(LookupError):
        dismiss(db, user.id, DismissIn(category_id=uuid.uuid4(), week_start=NEXT_WEEK), TODAY)
    for week in (NEXT_WEEK + timedelta(weeks=1), monday(1), NEXT_WEEK + timedelta(days=1)):
        with pytest.raises(ValueError):
            allocate(db, user.id, AllocateIn(category_id=delivery.id, week_start=week, amount=10), TODAY)
    assert db.query(CrunchAllocationModel).count() == 0


def test_deleting_the_category_clears_its_allocations(db, user, ahead):
    _, delivery, _ = ahead
    allocate(db, user.id, AllocateIn(category_id=delivery.id, week_start=NEXT_WEEK, amount=60), TODAY)

    delete_category(db, user.id, delivery.id)

    assert db.query(CrunchAllocationModel).count() == 0


def test_another_users_allocations_never_count(db, user, ahead):
    _, delivery, _ = ahead
    stranger = make_user(db, "stranger@example.com")
    db.add(CrunchAllocationModel(id=uuid.uuid4(), user_id=stranger.id, category_id=delivery.id,
                                 week_start=NEXT_WEEK, dismissed=True))
    for w in (3, 6, 9):
        db.add(CrunchAllocationModel(id=uuid.uuid4(), user_id=stranger.id, category_id=delivery.id,
                                     week_start=monday(w), dismissed=True))
    db.commit()

    (lift,) = spending_guard(db, user.id, TODAY).lifts
    assert lift.dismissed is False


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, client):
    body = client.get(f"/api/finances/{user.id}/spending-guard").json()

    assert body["ready"] is False and body["needed_crunch_weeks"] == NEEDED_CRUNCH_WEEKS
