"""Paycheques: gross here, deductions here, only the net in the ledger.

The tuition payment in reverse, and the tests mirror its concerns: the net has
to equal the parts it was split into, a deduction must never read as income, and
deleting either side must take the other with it.
"""
import datetime
import uuid

import pytest

from app._database.models import (
    AccountModel,
    PaychequeDeductionModel,
    PaychequeModel,
    TransactionModel,
)
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Finances.schemas.deposit import DepositAllocation
from app.Finances.services.transaction_service import delete_transaction
from app.Jobs.schemas.job import (
    JobCreate,
    JobKind,
    ShiftMeeting,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.schemas.paycheque import DeductionEntry, PaychequeCreate, PaychequeUpdate
from app.Jobs.services.job_service import confirm_shift, create_job, list_shifts, set_shift_schedule
from app.Jobs.services.paycheque_service import (
    delete_paycheque,
    list_paycheques,
    preview_paycheque,
    record_paycheque,
    update_paycheque,
)
from tests.conftest import make_account

TERM_START = datetime.date(2026, 9, 7)
TERM_END = datetime.date(2026, 12, 11)
PERIOD_START = datetime.date(2026, 10, 5)
PERIOD_END = datetime.date(2026, 10, 11)
PAID_ON = datetime.date(2026, 10, 16)
CENT = 0.011  # money is float here, so compare with a tolerance


@pytest.fixture
def accounts(db, user):
    """Two accounts sharing income 70/30."""
    return [
        make_account(db, user.id, "Chequing", share=70.0),
        make_account(db, user.id, "Savings", share=30.0),
    ]


@pytest.fixture
def job(db, user):
    return create_job(db, user.id, JobCreate(
        name="Campus Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=TERM_START,
    ))


@pytest.fixture
def worked(db, user, job):
    """Tue and Thu, 09:00-14:00, across the pay period."""
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU", "TH"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))
    return job


def a_cheque(job, gross=612.0, deductions=None, allocations=None):
    return PaychequeCreate(
        job_id=job.id, occurred_on=PAID_ON, gross_amount=gross,
        period_start=PERIOD_START, period_end=PERIOD_END,
        deductions=deductions if deductions is not None else [
            DeductionEntry(description="Income tax", amount=73.44),
            DeductionEntry(description="EI", amount=10.10),
            DeductionEntry(description="CPP", amount=33.66),
        ],
        allocations=allocations or [],
    )


def income_rows(db, user):
    return db.query(TransactionModel).filter(
        TransactionModel.user_id == user.id,
        TransactionModel.kind == "income",
    ).all()


# --- the net, and only the net ------------------------------------------

def test_the_net_is_gross_less_deductions(db, user, accounts, job):
    cheque = record_paycheque(db, user.id, a_cheque(job))

    assert cheque.gross_amount == 612.0
    assert cheque.net_amount == pytest.approx(494.80, abs=CENT)


def test_only_the_net_reaches_the_ledger(db, user, accounts, job):
    """A deduction is money that never entered the account."""
    record_paycheque(db, user.id, a_cheque(job))

    total = sum(row.amount for row in income_rows(db, user))
    assert total == pytest.approx(494.80, abs=CENT)


def test_a_deduction_never_appears_as_income(db, user, accounts, job):
    record_paycheque(db, user.id, a_cheque(job))

    descriptions = {row.description for row in income_rows(db, user)}
    assert not any("tax" in d.lower() or "EI" in d or "CPP" in d for d in descriptions)


def test_the_net_splits_by_income_share_and_the_parts_sum_to_the_whole(db, user, accounts, job):
    cheque = record_paycheque(db, user.id, a_cheque(job))
    rows = income_rows(db, user)

    assert len(rows) == 2
    by_account = {row.account_id: row.amount for row in rows}
    assert by_account[accounts[0].id] == pytest.approx(346.36, abs=CENT)
    assert by_account[accounts[1].id] == pytest.approx(148.44, abs=CENT)
    assert sum(rows_amount := [r.amount for r in rows]) == pytest.approx(
        cheque.net_amount, abs=CENT
    ), rows_amount


def test_the_rows_share_one_group(db, user, accounts, job):
    record_paycheque(db, user.id, a_cheque(job))
    groups = {row.group_id for row in income_rows(db, user)}

    assert len(groups) == 1 and None not in groups


def test_an_explicit_split_overrides_the_shares(db, user, accounts, job):
    cheque = a_cheque(job, allocations=[
        DepositAllocation(account_id=accounts[0].id, amount=494.80),
    ])
    record_paycheque(db, user.id, cheque)

    rows = income_rows(db, user)
    assert len(rows) == 1 and rows[0].account_id == accounts[0].id


def test_deductions_may_not_exceed_the_gross(db, user, accounts, job):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        a_cheque(job, gross=100.0, deductions=[
            DeductionEntry(description="Income tax", amount=120.0)])


def test_a_cheque_with_no_account_taking_income_is_refused(db, user, job):
    """No accounts fixture here, so there is nowhere for the net to land."""
    with pytest.raises(ValueError, match="income share"):
        record_paycheque(db, user.id, a_cheque(job))


# --- reconciliation ------------------------------------------------------

def test_an_hourly_cheque_is_measured_against_hours_times_rate(db, user, accounts, worked):
    """Two 5-hour shifts at 18.50 is 185.00."""
    preview = preview_paycheque(db, user.id, worked.id, PERIOD_START, PERIOD_END)

    assert preview.shift_count == 2
    assert preview.counted_minutes == 600
    assert preview.expected_gross == pytest.approx(185.00, abs=CENT)


def test_a_short_cheque_shows_a_negative_variance(db, user, accounts, worked):
    cheque = record_paycheque(db, user.id, a_cheque(worked, gross=170.0, deductions=[]))

    assert cheque.expected_gross == pytest.approx(185.00, abs=CENT)
    assert cheque.variance == pytest.approx(-15.00, abs=CENT)


def test_a_rate_override_is_honoured_in_the_expectation(db, user, accounts, worked):
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(rate_override=37.0))

    preview = preview_paycheque(db, user.id, worked.id, PERIOD_START, PERIOD_END)
    # One shift at double time, one at the ordinary rate.
    assert preview.expected_gross == pytest.approx(185.0 + 92.5, abs=CENT)


def test_a_salaried_job_expects_its_period_amount_not_its_hours(db, user, accounts):
    """Working a long week is not evidence of being underpaid."""
    salaried = create_job(db, user.id, JobCreate(
        name="TA-ship", kind=JobKind.SALARIED, period_amount=1200.0,
        started_on=TERM_START,
    ))
    set_shift_schedule(db, user.id, salaried.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["MO", "TU", "WE", "TH", "FR"],
                               start_time=datetime.time(9, 0),
                               end_time=datetime.time(17, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))

    preview = preview_paycheque(db, user.id, salaried.id, PERIOD_START, PERIOD_END)
    assert preview.counted_minutes > 0, "the hours are still recorded"
    assert preview.expected_gross == pytest.approx(1200.0, abs=CENT)


def test_a_contract_job_expects_nothing(db, user, accounts):
    """You invoiced it; there is nothing to predict from hours."""
    contract = create_job(db, user.id, JobCreate(
        name="Freelance", kind=JobKind.CONTRACT, started_on=TERM_START))

    preview = preview_paycheque(db, user.id, contract.id, PERIOD_START, PERIOD_END)
    assert preview.expected_gross is None


def test_the_expectation_is_frozen_when_the_cheque_is_recorded(db, user, accounts, worked):
    """Editing a shift later must not overturn a verdict already reached."""
    cheque = record_paycheque(db, user.id, a_cheque(worked, gross=185.0, deductions=[]))
    assert cheque.variance == pytest.approx(0.0, abs=CENT)

    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(worked_start=datetime.time(9, 0),
                                    worked_end=datetime.time(20, 0)))

    again = list_paycheques(db, user.id)[0]
    assert again.expected_gross == pytest.approx(185.00, abs=CENT)


# --- tips ----------------------------------------------------------------

def test_a_cash_tip_reaches_the_ledger(db, user, accounts, worked):
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=True))

    assert sum(row.amount for row in income_rows(db, user)) == pytest.approx(45.0, abs=CENT)


def test_a_tip_paid_on_the_cheque_does_not_write_its_own_row(db, user, accounts, worked):
    """It arrives inside the gross; a row here as well would count it twice."""
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=False))

    assert income_rows(db, user) == []


def test_an_on_cheque_tip_is_inside_what_the_cheque_should_come_to(db, user, accounts, worked):
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=False))

    preview = preview_paycheque(db, user.id, worked.id, PERIOD_START, PERIOD_END)
    assert preview.on_cheque_tips == pytest.approx(45.0, abs=CENT)
    assert preview.expected_gross == pytest.approx(185.0 + 45.0, abs=CENT)


def test_a_cash_tip_is_left_out_of_what_the_cheque_should_come_to(db, user, accounts, worked):
    """Counting it would make every cheque look short by the cash earned."""
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=True))

    preview = preview_paycheque(db, user.id, worked.id, PERIOD_START, PERIOD_END)
    assert preview.on_cheque_tips == 0.0
    assert preview.expected_gross == pytest.approx(185.0, abs=CENT)


def test_changing_a_tip_to_on_cheque_removes_the_row_it_wrote(db, user, accounts, worked):
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    event_id, on_date = shifts[0].event_id, shifts[0].on_date

    confirm_shift(db, user.id, event_id, on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=True))
    assert income_rows(db, user) != []

    confirm_shift(db, user.id, event_id, on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=False))
    assert income_rows(db, user) == []


def test_clearing_a_tip_removes_its_row(db, user, accounts, worked):
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    event_id, on_date = shifts[0].event_id, shifts[0].on_date

    confirm_shift(db, user.id, event_id, on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=True))
    confirm_shift(db, user.id, event_id, on_date, ShiftRecordUpsert(tip_amount=0.0))

    assert income_rows(db, user) == []


def test_a_cash_tip_with_nowhere_to_go_still_records_the_tip(db, user, worked):
    """No accounts fixture: logging your hours must not fail over budget setup."""
    shifts = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(tip_amount=45.0, tip_is_cash=True))

    again = list_shifts(db, user.id, PERIOD_START, PERIOD_END)
    assert again[0].tip_amount == 45.0
    assert again[0].tip_in_ledger is False, "and it says the budget has not seen it"


# --- correcting and removing ---------------------------------------------

def test_correcting_the_gross_rewrites_the_ledger_rows(db, user, accounts, job):
    cheque = record_paycheque(db, user.id, a_cheque(job))

    update_paycheque(db, user.id, cheque.id, PaychequeUpdate(gross_amount=700.0))

    total = sum(row.amount for row in income_rows(db, user))
    assert total == pytest.approx(700.0 - 117.20, abs=CENT)


def test_correcting_the_deductions_replaces_them_wholesale(db, user, accounts, job):
    cheque = record_paycheque(db, user.id, a_cheque(job))

    updated = update_paycheque(db, user.id, cheque.id, PaychequeUpdate(
        deductions=[DeductionEntry(description="Income tax", amount=50.0)]))

    assert len(updated.deductions) == 1
    assert updated.net_amount == pytest.approx(562.0, abs=CENT)
    assert sum(r.amount for r in income_rows(db, user)) == pytest.approx(562.0, abs=CENT)


def test_deleting_a_cheque_takes_its_ledger_rows(db, user, accounts, job):
    cheque = record_paycheque(db, user.id, a_cheque(job))

    delete_paycheque(db, user.id, cheque.id)

    assert income_rows(db, user) == []
    assert db.query(PaychequeModel).count() == 0
    assert db.query(PaychequeDeductionModel).count() == 0


def test_deleting_the_ledger_rows_takes_the_cheque(db, user, accounts, job):
    """The other half of the cascade. An orphan here answered for money gone."""
    record_paycheque(db, user.id, a_cheque(job))
    row = income_rows(db, user)[0]

    delete_transaction(db, user.id, row.id, scope="group")

    assert db.query(PaychequeModel).count() == 0
    assert db.query(PaychequeDeductionModel).count() == 0
