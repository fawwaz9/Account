"""Earnings: what the hours say, against what the cheques actually paid.

The distinction running through all of it is earned vs paid. Earned comes from
shifts and is a prediction; paid comes from cheques that arrived. Collapsing
them would hide the thing the page exists to show -- a fortnight worked that
nobody has paid for, or paid short.
"""
import datetime

import pytest

from app.Jobs.schemas.job import (
    JobCreate,
    JobKind,
    ShiftMeeting,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.schemas.paycheque import DeductionEntry, PaychequeCreate
from app.Jobs.services.earnings_service import earnings_summary
from app.Jobs.services.job_service import (
    confirm_shift,
    create_job,
    list_shifts,
    set_shift_schedule,
)
from app.Jobs.services.paycheque_service import record_paycheque
from tests.conftest import make_account, make_course

TERM_START = datetime.date(2026, 9, 7)
TERM_END = datetime.date(2026, 12, 11)
# A Sunday, so "the past week" is Mon 5th to Sun 11th of October.
ANCHOR = datetime.date(2026, 10, 11)
CENT = 0.011


@pytest.fixture
def accounts(db, user):
    return [make_account(db, user.id, "Chequing", share=100.0)]


@pytest.fixture
def hourly(db, user):
    """Tue and Thu, 09:00-14:00, at $18.50."""
    job = create_job(db, user.id, JobCreate(
        name="Campus Bookstore", kind=JobKind.HOURLY, hourly_rate=18.5,
        started_on=TERM_START,
    ))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU", "TH"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(14, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))
    return job


def summary(db, user):
    return earnings_summary(db, user.id, on_day=ANCHOR)


# --- earned, from the hours ---------------------------------------------

def test_the_week_reports_hours_and_what_they_earned(db, user, hourly):
    week = summary(db, user).week

    assert week.counted_minutes == 600, "two five-hour shifts"
    assert week.gross_earned == pytest.approx(185.00, abs=CENT)


def test_a_job_is_broken_out_on_its_own(db, user, hourly):
    week = summary(db, user).week

    assert len(week.per_job) == 1
    assert week.per_job[0].job_name == "Campus Bookstore"
    assert week.per_job[0].counted_minutes == 600


def test_assumed_shifts_are_counted_and_declared(db, user, hourly):
    """The figure still includes them; it just says how much of itself is a guess."""
    week = summary(db, user).week

    assert week.per_job[0].shift_count == 2
    assert week.per_job[0].assumed_count == 2

    shifts = list_shifts(db, user.id, datetime.date(2026, 10, 5), ANCHOR)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date, ShiftRecordUpsert())

    assert summary(db, user).week.per_job[0].assumed_count == 1


def test_confirmed_hours_beat_the_schedule(db, user, hourly):
    shifts = list_shifts(db, user.id, datetime.date(2026, 10, 5), ANCHOR)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(worked_start=datetime.time(9, 0),
                                    worked_end=datetime.time(15, 30)))

    week = summary(db, user).week
    assert week.counted_minutes == 690
    assert week.gross_earned == pytest.approx(185.0 + 27.75, abs=CENT)


def test_a_salaried_job_earns_by_period_not_by_hour(db, user):
    """Hours are what the job costs you, never what it pays."""
    job = create_job(db, user.id, JobCreate(
        name="TA-ship", kind=JobKind.SALARIED, period_amount=1200.0,
        started_on=TERM_START,
        pay_starts_on=datetime.date(2026, 10, 9),
        pay_schedule={"freq": "weekly", "interval": 2, "byday": [],
                      "until": None, "count": None},
    ))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["MO", "TU", "WE", "TH", "FR"],
                               start_time=datetime.time(9, 0),
                               end_time=datetime.time(17, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))

    week = summary(db, user).week
    assert week.counted_minutes > 0, "the hours are still recorded"
    assert week.gross_earned == pytest.approx(1200.0, abs=CENT), "one pay date in the week"


def test_a_salaried_jobs_earnings_do_not_move_with_its_hours(db, user):
    """The promise behind the salaried rule: a long week is not extra pay."""
    job = create_job(db, user.id, JobCreate(
        name="TA-ship", kind=JobKind.SALARIED, period_amount=1200.0,
        started_on=TERM_START,
        pay_starts_on=datetime.date(2026, 10, 9),
        pay_schedule={"freq": "weekly", "interval": 2, "byday": [],
                      "until": None, "count": None},
    ))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(12, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))
    before = summary(db, user).week.gross_earned

    shifts = list_shifts(db, user.id, datetime.date(2026, 10, 5), ANCHOR)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(worked_start=datetime.time(9, 0),
                                    worked_end=datetime.time(21, 0)))

    after = summary(db, user)
    assert after.week.gross_earned == pytest.approx(before, abs=CENT)
    assert after.week.counted_minutes == 720, "the hours are still recorded"


def test_an_on_cheque_tip_is_not_added_to_a_salary(db, user):
    """What the kind check in earned_from_shifts actually protects."""
    job = create_job(db, user.id, JobCreate(
        name="TA-ship", kind=JobKind.SALARIED, period_amount=1200.0,
        started_on=TERM_START,
        pay_starts_on=datetime.date(2026, 10, 9),
        pay_schedule={"freq": "weekly", "interval": 2, "byday": [],
                      "until": None, "count": None},
    ))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(12, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))

    shifts = list_shifts(db, user.id, datetime.date(2026, 10, 5), ANCHOR)
    confirm_shift(db, user.id, shifts[0].event_id, shifts[0].on_date,
                  ShiftRecordUpsert(tip_amount=50.0, tip_is_cash=False))

    assert summary(db, user).week.gross_earned == pytest.approx(1200.0, abs=CENT)


def test_a_contract_job_earns_nothing_from_hours(db, user):
    job = create_job(db, user.id, JobCreate(
        name="Freelance", kind=JobKind.CONTRACT, started_on=TERM_START))
    set_shift_schedule(db, user.id, job.id, ShiftScheduleCreate(
        meetings=[ShiftMeeting(days=["TU"], start_time=datetime.time(9, 0),
                               end_time=datetime.time(17, 0), location=None)],
        starts_on=TERM_START, ends_on=TERM_END,
    ))

    week = summary(db, user).week
    assert week.counted_minutes > 0
    assert week.gross_earned == 0.0


# --- paid, from the cheques ----------------------------------------------

def test_earned_and_paid_are_reported_apart(db, user, accounts, hourly):
    """A fortnight worked but not yet paid must not read as a fortnight unpaid."""
    week = summary(db, user).week

    assert week.gross_earned == pytest.approx(185.0, abs=CENT)
    assert week.gross_paid == 0.0, "no cheque has arrived"
    assert week.net_paid == 0.0


def test_a_cheque_fills_in_the_paid_side(db, user, accounts, hourly):
    record_paycheque(db, user.id, PaychequeCreate(
        job_id=hourly.id, occurred_on=datetime.date(2026, 10, 9),
        gross_amount=185.0, period_start=datetime.date(2026, 10, 5),
        period_end=ANCHOR,
        deductions=[DeductionEntry(description="Income tax", amount=37.0)],
    ))

    week = summary(db, user).week
    assert week.gross_paid == pytest.approx(185.0, abs=CENT)
    assert week.deducted == pytest.approx(37.0, abs=CENT)
    assert week.net_paid == pytest.approx(148.0, abs=CENT)


# --- the effective rate ---------------------------------------------------

def test_the_effective_rate_is_what_survives_deductions(db, user, accounts, hourly):
    """10 hours, $185 gross, $37 off: $18.50 advertised, $14.80 in hand."""
    record_paycheque(db, user.id, PaychequeCreate(
        job_id=hourly.id, occurred_on=datetime.date(2026, 10, 9),
        gross_amount=185.0, period_start=datetime.date(2026, 10, 5),
        period_end=ANCHOR,
        deductions=[DeductionEntry(description="Income tax", amount=37.0)],
    ))

    rate = summary(db, user).effective_rate
    assert rate.gross_per_hour == pytest.approx(18.50, abs=CENT)
    assert rate.net_per_hour == pytest.approx(14.80, abs=CENT)
    assert rate.deduction_percent == pytest.approx(20.0, abs=0.05)


def test_the_rate_is_null_before_anything_is_paid(db, user, accounts, hourly):
    """Null rather than zero, which would read as working for nothing."""
    rate = summary(db, user).effective_rate

    assert rate.net_per_hour is None
    assert rate.paid_minutes == 0


def test_unpaid_hours_do_not_drag_the_rate_down(db, user, accounts, hourly):
    """Measured over what cheques covered, not over every hour ever worked.

    Otherwise a cheque still to come reads as a pay cut.
    """
    record_paycheque(db, user.id, PaychequeCreate(
        job_id=hourly.id, occurred_on=datetime.date(2026, 9, 18),
        gross_amount=185.0, period_start=datetime.date(2026, 9, 14),
        period_end=datetime.date(2026, 9, 20),
        deductions=[DeductionEntry(description="Income tax", amount=37.0)],
    ))

    # Three further weeks of shifts have happened with no cheque for them.
    rate = summary(db, user).effective_rate
    assert rate.net_per_hour == pytest.approx(14.80, abs=CENT)


# --- what is owed, and when -----------------------------------------------

def test_unpaid_work_is_counted_from_the_last_period(db, user, accounts, hourly):
    record_paycheque(db, user.id, PaychequeCreate(
        job_id=hourly.id, occurred_on=datetime.date(2026, 10, 2),
        gross_amount=1.0, period_start=TERM_START,
        period_end=datetime.date(2026, 10, 4),
        deductions=[],
    ))

    owed = summary(db, user).upcoming[0]
    assert owed.unpaid_minutes == 600, "only the week since that period"
    assert owed.unpaid_estimate == pytest.approx(185.0, abs=CENT)


def test_a_job_you_have_left_is_not_listed_as_owing(db, user, hourly):
    from app.Jobs.schemas.job import JobUpdate
    from app.Jobs.services.job_service import update_job

    update_job(db, user.id, hourly.id, JobUpdate(ended_on=datetime.date(2026, 9, 30)))
    assert summary(db, user).upcoming == []


def test_the_next_pay_date_comes_from_the_rule(db, user, hourly):
    from app.Jobs.schemas.job import JobUpdate
    from app.Jobs.services.job_service import update_job

    update_job(db, user.id, hourly.id, JobUpdate(
        pay_starts_on=datetime.date(2026, 9, 11),
        pay_schedule={"freq": "weekly", "interval": 2, "byday": [],
                      "until": None, "count": None}))

    assert summary(db, user).upcoming[0].next_pay_on == datetime.date(2026, 10, 23)


# --- hours against classes -------------------------------------------------

def test_work_and_class_hours_are_reported_apart(db, user, hourly):
    from app.Calendar.schemas.event import ClassMeeting, ClassScheduleCreate, EventKind
    from app.Calendar.services.class_schedule_service import set_class_schedule

    course = make_course(db, user.id, "COSC 111",
                         start_date=TERM_START, end_date=TERM_END)
    set_class_schedule(db, user.id, course.id, ClassScheduleCreate(
        meetings=[ClassMeeting(kind=EventKind.LECTURE, days=["MO", "WE", "FR"],
                               start_time=datetime.time(10, 0),
                               end_time=datetime.time(11, 0))],
        starts_on=TERM_START, ends_on=TERM_END,
    ))

    week = summary(db, user).this_week
    assert week.work_minutes == 600, "two five-hour shifts"
    assert week.class_minutes == 180, "three one-hour lectures"


def test_booked_minutes_still_means_everything(db, user, hourly):
    """The split is additive: anything already reading booked_minutes is unharmed."""
    from app.Calendar.services.load_service import week_load

    load = week_load(db, user.id, datetime.date(2026, 10, 5), ANCHOR)
    assert load.booked_minutes == 600
    assert load.work_minutes == 600
    assert load.class_minutes == 0


# ------------------------------------------------- the term window --

def in_term(db, user, anchor=ANCHOR):
    """Put the student in Fall of school year 3, anchored so it is 2026."""
    user.current_school_year = 3
    user.current_semester = "Fall"
    user.first_year_calendar_year = 2024
    db.commit()


def test_the_term_window_uses_the_terms_own_dates(db, user, hourly, accounts):
    """Not the courses'. This module used to restate the span rule -- earliest
    start, latest end across the term's courses -- and its own docstring said
    so. Restating is what let the two drift: once Finances began measuring the
    term itself, Jobs went on measuring the teaching weeks, and "This term"
    started on September 9 while the budget's term started September 1.
    """
    in_term(db, user)
    make_course(db, user.id, "CPSC 221", year=3, semester="Fall",
                start_date=datetime.date(2026, 9, 9),
                end_date=datetime.date(2026, 12, 7))

    summary = earnings_summary(db, user.id, on_day=ANCHOR)

    assert summary.term is not None
    assert summary.term.starts_on == datetime.date(2026, 9, 1), "the term, not the teaching"
    assert summary.term.ends_on == ANCHOR, "clamped at today"


def test_jobs_and_finances_agree_about_when_the_term_runs(db, user):
    """The regression test for the whole class of fault. Two modules each
    answering "when does this term run" is fine; two modules each *deciding* it
    is not, and that is what shipped."""
    from app.Finances.services.tuition_service import term_span
    from app.Grades.utils.terms import term_dates

    in_term(db, user)
    course = make_course(db, user.id, "CPSC 221", year=3, semester="Fall",
                         start_date=datetime.date(2026, 9, 9),
                         end_date=datetime.date(2026, 12, 7))

    finances = term_span([course], user.first_year_calendar_year)
    grades = term_dates("Fall", 3, user.first_year_calendar_year)
    summary = earnings_summary(db, user.id, on_day=ANCHOR)

    assert finances == grades
    assert summary.term.starts_on == grades[0]


def test_a_term_with_no_courses_still_has_earnings(db, user, hourly, accounts):
    """It follows from the term having its own dates. Under the old rule a
    student who had not dated any course got no term figure at all, and nothing
    said why."""
    in_term(db, user)

    summary = earnings_summary(db, user.id, on_day=ANCHOR)

    assert summary.term is not None
    assert summary.term.starts_on == datetime.date(2026, 9, 1)


def test_without_the_anchor_there_is_no_term_window(db, user, hourly, accounts):
    """A school year is 1..10, so with nothing to resolve it against the honest
    answer is no window rather than a guessed one."""
    user.current_school_year = 3
    user.current_semester = "Fall"
    user.first_year_calendar_year = None
    db.commit()

    assert earnings_summary(db, user.id, on_day=ANCHOR).term is None


def test_a_term_that_has_not_started_reports_nothing(db, user, hourly, accounts):
    """Earnings cannot be reported for a stretch that has not happened."""
    in_term(db, user)

    before_term = earnings_summary(db, user.id, on_day=datetime.date(2026, 8, 15))

    assert before_term.term is None
