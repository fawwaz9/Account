"""Shifts against exams, and the tax packet (Phase 2 item 14, D21)."""
import uuid
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import (
    EventModel, JobModel, PaychequeDeductionModel, PaychequeModel, ShiftRecordModel, TransactionModel,
    TuitionPaymentModel,
)
from app.Auth.dependencies import get_current_user
from app.Jobs.services.conflict_service import shift_conflicts
from app.Jobs.services.tax_packet_service import deduction_kind, tax_packet
from conftest import make_account

EXAM_DAY = date(2026, 12, 14)


def job(db, user, name="Cafe"):
    row = JobModel(id=uuid.uuid4(), user_id=user.id, name=name, employer=f"{name} Ltd", kind="hourly",
                   hourly_rate=18.0, started_on=date(2026, 1, 1), archived=False, position=0)
    db.add(row)
    db.commit()
    return row


def shift(db, user, worker, on, start=None, end=None, **rule):
    row = EventModel(id=uuid.uuid4(), user_id=user.id, job_id=worker.id, title="Shift", kind="personal",
                     starts_on=on, start_time=start, end_time=end, skipped_dates=[], recur_interval=1, **rule)
    db.add(row)
    db.commit()
    return row


def exam(db, user, on=EXAM_DAY, start=time(8, 30), end=time(11, 0), kind="final"):
    row = EventModel(id=uuid.uuid4(), user_id=user.id, title="CPSC 221 Final", kind=kind, starts_on=on,
                     start_time=start, end_time=end, skipped_dates=[], recur_interval=1)
    db.add(row)
    db.commit()
    return row


def found(db, user):
    return shift_conflicts(db, user.id, EXAM_DAY - timedelta(days=7), EXAM_DAY + timedelta(days=7)).conflicts


# --- conflicts ----------------------------------------------------------------

def test_a_shift_during_an_exam_overlaps(db, user):
    exam(db, user)
    shift(db, user, job(db, user), EXAM_DAY, time(10, 0), time(14, 0))
    [c] = found(db, user)
    assert (c.kind, c.hours_between, c.job_name, c.exam_title) == ("overlap", 0.0, "Cafe", "CPSC 221 Final")


def test_a_closing_shift_the_night_before_crowds_the_exam(db, user):
    exam(db, user)
    shift(db, user, job(db, user), EXAM_DAY - timedelta(days=1), time(17, 0), time(23, 0))
    [c] = found(db, user)
    assert (c.kind, c.hours_between) == ("crowds", 9.5)


def test_a_morning_shift_before_an_afternoon_midterm_crowds_it(db, user):
    exam(db, user, start=time(15, 30), end=time(17, 0), kind="midterm")
    shift(db, user, job(db, user), EXAM_DAY, time(7, 0), time(12, 0))
    [c] = found(db, user)
    assert (c.kind, c.exam_kind, c.hours_between) == ("crowds", "midterm", 3.5)


def test_a_shift_well_before_is_fine(db, user):
    exam(db, user)
    shift(db, user, job(db, user), EXAM_DAY - timedelta(days=1), time(9, 0), time(13, 0))
    assert found(db, user) == []


def test_a_shift_after_the_exam_is_fine(db, user):
    exam(db, user)
    shift(db, user, job(db, user), EXAM_DAY, time(13, 0), time(18, 0))
    assert found(db, user) == []


def test_an_overnight_shift_into_exam_morning_overlaps(db, user):
    exam(db, user)
    shift(db, user, job(db, user), EXAM_DAY - timedelta(days=1), time(22, 0), time(9, 0))
    assert [c.kind for c in found(db, user)] == ["overlap"]


def test_an_untimed_exam_is_taken_to_start_at_eight(db, user):
    exam(db, user, start=None, end=None)
    shift(db, user, job(db, user), EXAM_DAY - timedelta(days=1), time(18, 0), time(23, 0))
    [c] = found(db, user)
    assert (c.kind, c.hours_between) == ("crowds", 9.0)


def test_a_repeating_shift_is_read_on_the_exam_week(db, user):
    exam(db, user)
    shift(db, user, job(db, user), date(2026, 9, 7), time(9, 0), time(12, 0), recur_freq="daily")
    assert [c.kind for c in found(db, user)] == ["overlap"]


def test_the_buffer_is_yours_to_set(db, user):
    exam(db, user)
    shift(db, user, job(db, user), EXAM_DAY - timedelta(days=1), time(17, 0), time(23, 0))
    user.preferences = {**(user.preferences or {}), "exam_buffer_hours": 6}
    db.commit()
    assert found(db, user) == []
    user.preferences = {**user.preferences, "exam_buffer_hours": 10}
    db.commit()
    result = shift_conflicts(db, user.id, EXAM_DAY - timedelta(days=7), EXAM_DAY + timedelta(days=7))
    assert result.buffer_hours == 10 and [c.kind for c in result.conflicts] == ["crowds"]


def test_only_exams_are_checked_not_lectures_or_your_own_events(db, user):
    for kind in ("lecture", "lab", "personal", "deadline"):
        exam(db, user, start=time(10, 0), end=time(11, 0), kind=kind)
    shift(db, user, job(db, user), EXAM_DAY, time(9, 0), time(12, 0))
    assert found(db, user) == []


def test_a_skipped_shift_is_not_flagged(db, user):
    exam(db, user)
    row = shift(db, user, job(db, user), EXAM_DAY - timedelta(days=1), time(17, 0), time(23, 0))
    row.skipped_dates = [(EXAM_DAY - timedelta(days=1)).isoformat()]
    db.commit()
    assert found(db, user) == []


# --- the tax packet -------------------------------------------------------------

def cheque(db, user, worker, on, gross, **deductions):
    row = PaychequeModel(id=uuid.uuid4(), user_id=user.id, job_id=worker.id, occurred_on=on, gross_amount=gross)
    db.add(row)
    db.flush()
    for description, amount in deductions.items():
        db.add(PaychequeDeductionModel(id=uuid.uuid4(), paycheque_id=row.id,
                                       description=description.replace("_", " "), amount=amount))
    db.commit()
    return row


@pytest.mark.parametrize(("text", "kind"), [
    ("Income tax", "income_tax"), ("Federal tax", "income_tax"), ("CPP", "cpp"), ("CPP2", "cpp"),
    ("Canada Pension Plan", "cpp"), ("EI", "ei"), ("Employment Insurance", "ei"), ("Union dues", "other"),
    ("Tips", "other"), ("Weird", "other"),
])
def test_a_deduction_is_sorted_by_its_name(text, kind):
    assert deduction_kind(text) == kind


def test_the_packet_sums_the_years_paycheques_and_nothing_else(db, user):
    cafe, library = job(db, user, "Cafe"), job(db, user, "Library")
    cheque(db, user, cafe, date(2026, 1, 15), 1000.0, Income_tax=100.0, CPP=50.0, EI=16.0)
    cheque(db, user, cafe, date(2026, 12, 31), 500.0, Income_tax=40.0, Union_dues=10.0)
    cheque(db, user, library, date(2026, 6, 1), 2000.0, Federal_tax=300.0)
    cheque(db, user, cafe, date(2025, 12, 31), 9999.0, Income_tax=999.0)   # last year
    cheque(db, user, cafe, date(2027, 1, 1), 8888.0)                       # next year
    packet = tax_packet(db, user.id, 2026)

    assert (packet.gross, packet.income_tax, packet.cpp, packet.ei, packet.other_deductions) == (
        3500.0, 440.0, 50.0, 16.0, 10.0)
    assert packet.net == 3500.0 - 440.0 - 50.0 - 16.0 - 10.0
    library_year, cafe_year = packet.employers
    assert (library_year.job_name, library_year.gross, library_year.paycheques) == ("Library", 2000.0, 1)
    assert [(d.label, d.amount) for d in cafe_year.deductions] == [
        ("Income tax", 140.0), ("CPP", 50.0), ("EI", 16.0), ("Union dues", 10.0)]


def test_tips_and_tuition_are_counted_for_the_year(db, user):
    cafe = job(db, user)
    event = shift(db, user, cafe, date(2026, 3, 1), time(9, 0), time(12, 0))
    for on, amount, cash in ((date(2026, 3, 1), 30.0, True), (date(2026, 3, 2), 12.5, False),
                             (date(2025, 3, 1), 99.0, True)):
        db.add(ShiftRecordModel(id=uuid.uuid4(), user_id=user.id, event_id=event.id, job_id=cafe.id,
                                on_date=on, confirmed=True, tip_amount=amount, tip_is_cash=cash))
    account = make_account(db, user.id, "Chequing")
    for on, amount in ((date(2026, 8, 30), -3200.0), (date(2025, 8, 30), -3000.0)):
        txn = TransactionModel(id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
                               amount=amount, description="Tuition", occurred_on=on)
        db.add(txn)
        db.flush()
        db.add(TuitionPaymentModel(id=uuid.uuid4(), user_id=user.id, transaction_id=txn.id,
                                   cost_per_credit=0.0, fees=0.0, occurred_on=on))
    db.commit()
    packet = tax_packet(db, user.id, 2026)
    [cafe_year] = packet.employers
    assert (cafe_year.cash_tips, cafe_year.other_tips, packet.cash_tips) == (30.0, 12.5, 30.0)
    assert packet.tuition_paid == 3200.0


def test_an_empty_year_is_all_zeros(db, user):
    packet = tax_packet(db, user.id, 2026)
    assert packet.employers == [] and packet.gross == 0.0 and packet.tuition_paid == 0.0


def test_the_route_takes_a_calendar_year(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        assert client.get(f"/api/jobs/{user.id}/tax-packet", params={"calendar_year": 2026}).status_code == 200
        assert client.get(f"/api/jobs/{user.id}/tax-packet", params={"calendar_year": 3}).status_code == 422
        assert client.get(f"/api/jobs/{user.id}/shift-conflicts").status_code == 200
    finally:
        app.main.app.dependency_overrides.clear()
