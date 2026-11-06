"""The standing-payment catch-up writes each payment once, and a student's change sticks.

Audit C1: the catch-up knew a payment was written only by finding its row. So an
edit to a rule's dates made every past date of the new pattern look unwritten,
and the next Budget page load wrote them all as real expenses; and deleting or
re-dating a generated payment removed the only evidence it was written, so it
came back. Audit M3: nothing but a read stopped two loads at once writing the
same payment twice, or a double tap funding one month twice.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app._database.models import (
    RecurringTransactionModel,
    SinkingContributionModel,
    TaskModel,
    TransactionModel,
)
from app.Calendar.schemas.event import Recurrence
from app.Finances.schemas.recurring import RecurringCreate, RecurringUpdate
from app.Finances.schemas.sinking import SinkingFundCreate
from app.Finances.schemas.transaction import TransactionUpdate
from app.Finances.services import recurring_service
from app.Finances.services.recurring_service import create_rule, run_due, update_rule
from app.Finances.services.sinking_service import create_fund
from app.Finances.services.transaction_service import delete_transaction, update_transaction
from app.Tasks.services import recurring_task_service
from app.shared.dates import user_today
from conftest import make_account


def monthly(**overrides):
    return Recurrence(**{"freq": "monthly", "interval": 1, "byday": [], "until": None, "count": None, **overrides})


@pytest.fixture
def today(db, user):
    return user_today(db, user.id)


@pytest.fixture
def rent(db, user, today):
    """A $900 monthly rent from five months back, caught up: about five rows."""
    account = make_account(db, user.id, "Spending")
    rule = create_rule(db, user.id, RecurringCreate(
        kind="expense", amount=900.0, description="Rent", account_id=account.id,
        starts_on=(today - timedelta(days=150)).replace(day=1), recurrence=monthly(),
    ))
    run_due(db, user.id)
    return rule


def rows_of(db, rule):
    return sorted(db.query(TransactionModel).filter(TransactionModel.recurring_id == rule.id).all(),
                  key=lambda row: (row.occurred_on, row.amount))


# ------------------------------------------------------------- an edit --

def test_moving_the_day_does_not_back_fill(db, user, today, rent):
    """The audit's case: rent from the 1st to the 5th wrote every past 5th as well."""
    before = [row.occurred_on for row in rows_of(db, rent)]
    assert len(before) >= 4

    update_rule(db, user.id, rent.id, RecurringUpdate(starts_on=rent.starts_on + timedelta(days=4)))
    run_due(db, user.id)

    after = [row.occurred_on for row in rows_of(db, rent)]
    assert [day for day in after if day < today] == [day for day in before if day < today]


def test_changing_the_repeat_does_not_back_fill(db, user, today, rent):
    before = len([row for row in rows_of(db, rent) if row.occurred_on < today])

    update_rule(db, user.id, rent.id, RecurringUpdate(recurrence=Recurrence(
        freq="weekly", interval=1, byday=[], until=None, count=None)))
    run_due(db, user.id)

    assert len([row for row in rows_of(db, rent) if row.occurred_on < today]) == before


def test_an_edit_still_writes_what_falls_due_from_today(db, user, today, rent):
    """The floor is today, not tomorrow: a payment due today under the new rule is owed."""
    update_rule(db, user.id, rent.id, RecurringUpdate(starts_on=today, recurrence=Recurrence(
        freq="weekly", interval=1, byday=[], until=None, count=None)))

    run_due(db, user.id)

    assert today in {row.occurred_on for row in rows_of(db, rent)}


def test_an_amount_change_sets_no_floor(db, user, rent):
    update_rule(db, user.id, rent.id, RecurringUpdate(amount=950.0))

    stored = db.query(RecurringTransactionModel).filter(RecurringTransactionModel.id == rent.id).one()
    assert stored.catchup_from is None


def test_resaving_the_same_dates_sets_no_floor(db, user, rent):
    """The rule's form sends every field on save; unchanged dates are not a change."""
    update_rule(db, user.id, rent.id, RecurringUpdate(starts_on=rent.starts_on, recurrence=monthly()))

    stored = db.query(RecurringTransactionModel).filter(RecurringTransactionModel.id == rent.id).one()
    assert stored.catchup_from is None


# ---------------------------------------------- the student's own change --

def test_a_deleted_payment_stays_deleted(db, user, rent):
    """The audit's second case: a deleted gym payment came back on the next load."""
    doomed = rows_of(db, rent)[0]
    doomed_id, due_on = doomed.id, doomed.occurred_on
    delete_transaction(db, user.id, doomed_id)

    run_due(db, user.id)

    assert due_on not in {row.occurred_on for row in rows_of(db, rent)}
    stored = db.query(RecurringTransactionModel).filter(RecurringTransactionModel.id == rent.id).one()
    assert due_on.isoformat() in stored.skipped_dates


def test_a_deleted_transfer_stays_deleted(db, user, today):
    spending, savings = make_account(db, user.id, "Spending"), make_account(db, user.id, "Savings")
    rule = create_rule(db, user.id, RecurringCreate(
        kind="transfer", amount=100.0, description="Top-up", account_id=spending.id,
        to_account_id=savings.id, starts_on=today - timedelta(days=60), recurrence=monthly(),
    ))
    run_due(db, user.id)
    first = rows_of(db, rule)[0]
    first_id, due_on = first.id, first.occurred_on

    delete_transaction(db, user.id, first_id)
    run_due(db, user.id)

    assert due_on not in {row.occurred_on for row in rows_of(db, rule)}


def test_a_payment_moved_to_another_day_is_not_written_again(db, user, rent):
    """Rent paid on the 3rd instead of the 1st: one payment, on the 3rd."""
    paid = rows_of(db, rent)[0]
    due_on = paid.occurred_on

    update_transaction(db, user.id, paid.id, TransactionUpdate(occurred_on=due_on + timedelta(days=2)))
    run_due(db, user.id)

    on_or_near = db.query(TransactionModel).filter(
        TransactionModel.user_id == user.id,
        TransactionModel.occurred_on.between(due_on, due_on + timedelta(days=2)),
    ).all()
    assert [(row.occurred_on, row.amount) for row in on_or_near] == [(due_on + timedelta(days=2), -900.0)]
    # The moved row is the student's own now; the day it was due is marked paid.
    assert on_or_near[0].recurring_id is None


def test_a_moved_transfer_keeps_its_two_halves_together(db, user, today):
    spending, savings = make_account(db, user.id, "Spending"), make_account(db, user.id, "Savings")
    rule = create_rule(db, user.id, RecurringCreate(
        kind="transfer", amount=100.0, description="Top-up", account_id=spending.id,
        to_account_id=savings.id, starts_on=today - timedelta(days=60), recurrence=monthly(),
    ))
    run_due(db, user.id)
    leg = rows_of(db, rule)[0]
    moved_to = leg.occurred_on + timedelta(days=1)

    update_transaction(db, user.id, leg.id, TransactionUpdate(occurred_on=moved_to))
    run_due(db, user.id)

    halves = db.query(TransactionModel).filter(TransactionModel.group_id == leg.group_id).all()
    assert {(row.occurred_on, row.recurring_id) for row in halves} == {(moved_to, None)}
    assert leg.occurred_on not in {row.occurred_on for row in rows_of(db, rule)}


def test_an_edit_that_keeps_the_date_keeps_the_link(db, user, rent):
    paid = rows_of(db, rent)[0]

    update_transaction(db, user.id, paid.id, TransactionUpdate(description="Rent, Oct"))

    assert db.query(TransactionModel).filter(TransactionModel.id == paid.id).one().recurring_id == rent.id


# ------------------------------------------------------- one write only --

def test_a_payment_is_written_already_stamped(db, user, rent):
    """One commit: no moment where a payment exists without its rule's id."""
    assert all(row.recurring_id == rent.id for row in rows_of(db, rent))
    assert db.query(TransactionModel).filter(TransactionModel.recurring_id.is_(None)).count() == 0


def test_two_loads_at_once_write_one_payment(db, user, rent, monkeypatch):
    """The second load read 'not written' too; the unique index stops it, quietly."""
    count = len(rows_of(db, rent))
    monkeypatch.setattr(recurring_service, "written_dates", lambda db, rule_id: set())

    result = run_due(db, user.id)

    assert result.created == 0 and result.skipped == []
    assert len(rows_of(db, rent)) == count


def test_the_database_refuses_a_second_payment_for_one_date(db, user, rent):
    paid = rows_of(db, rent)[0]
    db.add(TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=paid.account_id, kind="expense",
                            amount=-900.0, occurred_on=paid.occurred_on, recurring_id=rent.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_two_tasks_loads_at_once_write_one_occurrence(db, user, monkeypatch):
    from app.Calendar.schemas.event import Frequency
    from app.Tasks.schemas.recurring_task import RecurringTaskCreate

    rule = recurring_task_service.create_rule(db, user.id, RecurringTaskCreate(
        title="Bins", notes=None, due_time=None, estimated_minutes=None, course_id=None, tags=[],
        starts_on=user_today(db, user.id), active=True,
        recurrence=Recurrence(freq=Frequency.DAILY, interval=1, byday=[], until=None, count=None),
    ))
    count = db.query(TaskModel).filter(TaskModel.recurring_id == rule.id).count()
    monkeypatch.setattr(recurring_task_service, "written_dates", lambda db, rule_id: set())

    result = recurring_task_service.run_due(db, user.id)

    assert result.created == 0
    assert db.query(TaskModel).filter(TaskModel.recurring_id == rule.id).count() == count


def test_one_contribution_per_fund_per_month(db, user, today):
    spending, savings = make_account(db, user.id, "Spending"), make_account(db, user.id, "Savings")
    fund = create_fund(db, user.id, SinkingFundCreate(
        name="Laptop", target_amount=1200.0, due_on=today + timedelta(days=300),
        from_account_id=spending.id, to_account_id=savings.id,
    ))
    month = today.replace(day=1)
    for _ in range(2):
        db.add(SinkingContributionModel(id=uuid.uuid4(), fund_id=fund.id, for_month=month, amount=100.0))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
