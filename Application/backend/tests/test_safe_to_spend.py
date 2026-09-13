"""What can be spent between now and the next time money arrives.

The figure is a subtraction, so most of what can go wrong is in what is counted:
which accounts, which charges, and where the window ends.
"""
import datetime
import uuid

import pytest

from app._database.models import TransactionModel
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Finances.schemas.recurring import RecurringCreate
from app.Finances.services.recurring_service import create_rule
from app.Finances.services.safe_service import safe_to_spend
from app.Jobs.schemas.job import JobCreate, JobKind, ShiftMeeting, ShiftScheduleCreate
from app.Jobs.services.job_service import create_job, set_shift_schedule
from tests.conftest import make_account

# A Wednesday, comfortably inside October.
ANCHOR = datetime.date(2026, 10, 14)
CENT = 0.011


def deposit(db, user, account, amount, on=ANCHOR):
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        kind="income", amount=amount, description="Opening", occurred_on=on,
    ))
    db.commit()


@pytest.fixture
def chequing(db, user):
    account = make_account(db, user.id, "Chequing", share=100.0)
    deposit(db, user, account, 1840.20)
    return account


def rent(db, user, account, amount=612.0, on=datetime.date(2026, 10, 20)):
    return create_rule(db, user.id, RecurringCreate(
        kind="expense", account_id=account.id, amount=amount, description="Rent",
        starts_on=on,
        recurrence=Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[],
                              until=None, count=None),
        active=True,
    ))


def paid_job(db, user, *, pay_from=datetime.date(2026, 9, 11)):
    """Fortnightly from 11 Sep, so the next pay date after 14 Oct is 23 Oct."""
    return create_job(db, user.id, JobCreate(
        name="Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=datetime.date(2026, 9, 7),
        pay_starts_on=pay_from,
        pay_schedule=Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[],
                                until=None, count=None),
    ))


# --- what is counted ------------------------------------------------------

def test_a_spending_balance_is_what_there_is(db, user, chequing):
    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.spendable == pytest.approx(1840.20, abs=CENT)
    assert safe.safe_now == pytest.approx(1840.20, abs=CENT)


def test_savings_and_investments_are_not_spendable(db, user, chequing):
    """Money already decided against. Counting it gives a useless number."""
    savings = make_account(db, user.id, "Savings")
    savings.kind = "savings"
    investments = make_account(db, user.id, "Investments")
    investments.kind = "investment"
    db.commit()
    deposit(db, user, savings, 3200.0)
    deposit(db, user, investments, 5410.0)

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.spendable == pytest.approx(1840.20, abs=CENT)
    assert [a.name for a in safe.accounts] == ["Chequing"]


def test_an_archived_account_is_not_counted(db, user, chequing):
    other = make_account(db, user.id, "Old chequing")
    deposit(db, user, other, 500.0)
    other.archived = True
    db.commit()

    assert safe_to_spend(db, user.id, on_day=ANCHOR).spendable == pytest.approx(
        1840.20, abs=CENT)


def test_a_commitment_inside_the_window_reduces_it(db, user, chequing):
    paid_job(db, user)          # window runs to 22 Oct
    rent(db, user, chequing)    # rent on 20 Oct

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.committed == pytest.approx(612.0, abs=CENT)
    assert safe.safe_now == pytest.approx(1228.20, abs=CENT)
    assert [c.description for c in safe.commitments] == ["Rent"]


def test_a_commitment_past_the_window_does_not(db, user, chequing):
    paid_job(db, user)
    rent(db, user, chequing, on=datetime.date(2026, 10, 25))  # after 22 Oct

    assert safe_to_spend(db, user.id, on_day=ANCHOR).committed == 0.0


def test_incoming_standing_money_is_not_counted_as_available(db, user, chequing):
    """It has not arrived. Counting it is the optimism this figure avoids."""
    create_rule(db, user.id, RecurringCreate(
        kind="income", account_id=chequing.id, amount=300.0, description="Allowance",
        starts_on=datetime.date(2026, 10, 16),
        recurrence=Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[],
                              until=None, count=None),
        active=True,
    ))
    paid_job(db, user)

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)
    assert safe.committed == 0.0
    assert safe.safe_now == pytest.approx(1840.20, abs=CENT)


# --- the window -----------------------------------------------------------

def test_the_window_ends_the_day_before_the_next_cheque(db, user, chequing):
    paid_job(db, user)

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.ends_on == datetime.date(2026, 10, 22), "cheque lands 23 Oct"
    assert safe.until_payday is True
    assert safe.days == 9


def test_the_soonest_of_several_jobs_ends_it(db, user, chequing):
    """Money arriving is money arriving; the window ends at the first."""
    paid_job(db, user)
    create_job(db, user.id, JobCreate(
        name="Tutoring", kind=JobKind.HOURLY, hourly_rate=25.0,
        started_on=datetime.date(2026, 9, 7),
        pay_starts_on=datetime.date(2026, 10, 16),
        pay_schedule=Recurrence(freq=Frequency.WEEKLY, interval=4, byday=[],
                                until=None, count=None),
    ))

    assert safe_to_spend(db, user.id, on_day=ANCHOR).ends_on == datetime.date(2026, 10, 15)


def test_with_no_pay_rule_it_falls_back_to_month_end(db, user, chequing):
    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.ends_on == datetime.date(2026, 10, 31)
    assert safe.until_payday is False


def test_a_job_you_have_left_does_not_set_the_window(db, user, chequing):
    from app.Jobs.schemas.job import JobUpdate
    from app.Jobs.services.job_service import update_job

    job = paid_job(db, user)
    update_job(db, user.id, job.id, JobUpdate(ended_on=datetime.date(2026, 10, 1)))

    assert safe_to_spend(db, user.id, on_day=ANCHOR).until_payday is False


# --- the second figure ----------------------------------------------------

def test_work_not_yet_paid_for_is_reported_apart(db, user, chequing):
    """safe_soon exceeds safe_now by exactly what is owed, and never silently."""
    job = paid_job(db, user)
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU", "TH"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=datetime.date(2026, 9, 7), ends_on=datetime.date(2026, 12, 11)))

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.owed_to_you > 0
    assert safe.safe_soon == pytest.approx(safe.safe_now + safe.owed_to_you, abs=CENT)


def test_with_no_work_owed_the_two_figures_agree(db, user, chequing):
    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.owed_to_you == 0.0
    assert safe.safe_soon == pytest.approx(safe.safe_now, abs=CENT)


# --- being over-committed -------------------------------------------------

def test_a_negative_result_is_reported_not_hidden(db, user, chequing):
    """Being over-committed is the thing most worth knowing."""
    paid_job(db, user)
    rent(db, user, chequing, amount=2500.0)

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)

    assert safe.safe_now < 0
    assert safe.per_day is None, "a daily allowance of minus money is not guidance"


def test_per_day_divides_by_the_window(db, user, chequing):
    paid_job(db, user)

    safe = safe_to_spend(db, user.id, on_day=ANCHOR)
    assert safe.per_day == pytest.approx(1840.20 / 9, abs=CENT)


def test_a_missing_user_is_not_an_empty_figure(db, user):
    assert safe_to_spend(db, uuid.uuid4(), on_day=ANCHOR) is None
