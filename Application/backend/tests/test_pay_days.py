"""Pay on set days of the month (next.md, decided with the owner 2026-10-03).

The shared repeat rule cannot say "the 15th and the last day" or "the last
Friday", and it skips a month that lacks the date -- right for rent, wrong for
pay, where it means no cheque in February. These tests pin the decisions:

- three patterns: set dates, the last day of the month, an Nth weekday;
- a date a month lacks pays on the month's last day;
- a weekend date moves to the previous weekday, the next, or stays, per job;
- every reader of pay dates (safe to spend, earnings, the forecast) sees them.

October 2026 starts on a Thursday; the 31st is a Saturday. November's 15th is a
Sunday. Late January 2027 has Saturday the 30th and Sunday the 31st.
"""
import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main
from app._database.db import get_db
from app._database.models import JobModel
from app.Auth.services.session_service import create_access_token
from app.Calendar.schemas.event import Frequency, Recurrence, Weekday
from app.Finances.services.forecast_service import pay_dates as forecast_pay_dates
from app.Finances.services.safe_service import window
from app.Jobs.schemas.job import JobCreate, JobKind, JobUpdate, NthWeekday, PayDays, WeekendRule
from app.Jobs.services.earnings_service import periods_in
from app.Jobs.services.job_service import create_job, get_job, next_pay_on, update_job
from app.Jobs.services.pay_schedule import Pattern, pattern_dates

D = datetime.date
EARLY = D(2026, 1, 1)


def pattern(dates=(), last_day=False, nth=(), weekend=WeekendRule.KEEP, until=None):
    return Pattern(dates=tuple(dates), last_day=last_day, nth=tuple(nth), weekend=weekend, until=until)


def dates_in(p, start, end, starts_on=EARLY):
    return pattern_dates(p, starts_on, start, end)


# --- the patterns ------------------------------------------------------------

def test_the_15th_and_the_last_day():
    p = pattern(dates=[15], last_day=True)
    assert dates_in(p, D(2026, 10, 1), D(2026, 11, 30)) == [
        D(2026, 10, 15), D(2026, 10, 31), D(2026, 11, 15), D(2026, 11, 30)]


def test_a_date_the_month_lacks_pays_on_its_last_day():
    """The opposite of the shared rule, which skips the month: the 30th in
    February is the 28th, and the 31st in April is the 30th."""
    assert dates_in(pattern(dates=[30]), D(2027, 2, 1), D(2027, 2, 28)) == [D(2027, 2, 28)]
    assert dates_in(pattern(dates=[31]), D(2026, 4, 1), D(2026, 4, 30)) == [D(2026, 4, 30)]


def test_the_last_friday():
    p = pattern(nth=[(-1, "FR")])
    assert dates_in(p, D(2026, 10, 1), D(2026, 11, 30)) == [D(2026, 10, 30), D(2026, 11, 27)]


def test_the_2nd_and_4th_thursday():
    p = pattern(nth=[(2, "TH"), (4, "TH")])
    assert dates_in(p, D(2026, 10, 1), D(2026, 10, 31)) == [D(2026, 10, 8), D(2026, 10, 22)]


# --- weekends ----------------------------------------------------------------

def test_a_weekend_date_moves_to_the_friday_before():
    p = pattern(dates=[15], last_day=True, weekend=WeekendRule.PREVIOUS)
    assert dates_in(p, D(2026, 10, 1), D(2026, 11, 30)) == [
        D(2026, 10, 15), D(2026, 10, 30), D(2026, 11, 13), D(2026, 11, 30)]


def test_a_weekend_date_moves_to_the_monday_after():
    p = pattern(dates=[15], last_day=True, weekend=WeekendRule.NEXT)
    assert dates_in(p, D(2026, 10, 1), D(2026, 11, 30)) == [
        D(2026, 10, 15), D(2026, 11, 2), D(2026, 11, 16), D(2026, 11, 30)]


def test_a_weekend_date_can_stay_where_it_is():
    p = pattern(last_day=True, weekend=WeekendRule.KEEP)
    assert dates_in(p, D(2026, 10, 1), D(2026, 10, 31)) == [D(2026, 10, 31)]


def test_the_short_month_and_the_weekend_both_apply():
    """The 30th in February 2027 is the 28th, a Sunday, so it pays Friday the 26th."""
    p = pattern(dates=[30], weekend=WeekendRule.PREVIOUS)
    assert dates_in(p, D(2027, 2, 1), D(2027, 2, 28)) == [D(2027, 2, 26)]


def test_an_nth_weekday_is_never_moved():
    """The weekend rule is for dates. A weekday of the month was picked as that day."""
    p = pattern(nth=[(1, "SA")], weekend=WeekendRule.PREVIOUS)
    assert dates_in(p, D(2026, 10, 1), D(2026, 10, 31)) == [D(2026, 10, 3)]


def test_two_pay_days_landing_on_one_date_are_one_cheque():
    # The 30th and the last day are the same day in November.
    assert dates_in(pattern(dates=[30], last_day=True), D(2026, 11, 1), D(2026, 11, 30)) == [D(2026, 11, 30)]
    # Saturday the 30th and Sunday the 31st both move to Friday the 29th.
    p = pattern(dates=[30], last_day=True, weekend=WeekendRule.PREVIOUS)
    assert dates_in(p, D(2027, 1, 1), D(2027, 1, 31)) == [D(2027, 1, 29)]


def test_a_date_moved_across_the_window_edge_is_still_found():
    """Saturday 31 October, paid the Monday after, is a November cheque."""
    p = pattern(last_day=True, weekend=WeekendRule.NEXT)
    assert dates_in(p, D(2026, 11, 1), D(2026, 11, 10)) == [D(2026, 11, 2)]
    assert dates_in(p, D(2026, 10, 1), D(2026, 10, 31)) == []


# --- the first and last pay dates -------------------------------------------

def test_nothing_before_the_first_pay_date():
    p = pattern(dates=[15], last_day=True)
    assert dates_in(p, D(2026, 10, 1), D(2026, 10, 31), starts_on=D(2026, 10, 20)) == [D(2026, 10, 31)]


def test_the_first_and_last_dates_are_the_scheduled_ones_not_the_moved_ones():
    """'The first cheque is the 31st' means the 31st's cheque, though the
    weekend pays it on the 30th; 'until the 14th' leaves out the 15th's, though
    it pays on the 13th."""
    p = pattern(last_day=True, weekend=WeekendRule.PREVIOUS)
    assert dates_in(p, D(2026, 10, 1), D(2026, 10, 31), starts_on=D(2026, 10, 31)) == [D(2026, 10, 30)]
    p = pattern(dates=[15], weekend=WeekendRule.PREVIOUS, until=D(2026, 11, 14))
    assert dates_in(p, D(2026, 10, 1), D(2026, 11, 30)) == [D(2026, 10, 15)]


# --- what the API accepts ----------------------------------------------------

@pytest.mark.parametrize("bad", [
    dict(dates=[15], nth_weekdays=[NthWeekday(n=-1, day=Weekday.FR)]),
    dict(last_day=True, nth_weekdays=[NthWeekday(n=1, day=Weekday.MO)]),
    dict(),
    dict(dates=[0]),
    dict(dates=[32]),
    dict(dates=[15, 15]),
])
def test_a_pattern_the_decisions_do_not_allow_is_refused(bad):
    with pytest.raises(ValidationError):
        PayDays(**bad)


def test_only_the_first_four_weekdays_or_the_last():
    with pytest.raises(ValidationError):
        NthWeekday(n=5, day=Weekday.FR)
    with pytest.raises(ValidationError):
        NthWeekday(n=0, day=Weekday.FR)


def job_create(**over):
    fields = dict(name="Bookstore", kind=JobKind.SALARIED, period_amount=1500.0,
                  started_on=D(2026, 9, 1), pay_starts_on=D(2026, 9, 15))
    fields.update(over)
    return JobCreate(**fields)


SEMI_MONTHLY = PayDays(dates=[15], last_day=True, weekend=WeekendRule.PREVIOUS)
FORTNIGHTLY = Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[], until=None, count=None)


def test_a_job_pays_by_a_rule_or_by_days_never_both():
    with pytest.raises(ValidationError):
        job_create(pay_days=SEMI_MONTHLY, pay_schedule=FORTNIGHTLY)


def test_days_of_the_month_need_a_first_pay_date():
    with pytest.raises(ValidationError):
        job_create(pay_days=SEMI_MONTHLY, pay_starts_on=None)


# --- through the service -----------------------------------------------------

def row(db, job):
    return db.query(JobModel).filter(JobModel.id == job.id).one()


def test_a_job_saved_with_days_of_the_month_reads_back_as_them(db, user):
    job = create_job(db, user.id, job_create(pay_days=SEMI_MONTHLY))
    back = get_job(db, user.id, job.id)
    assert back.pay_days == SEMI_MONTHLY
    # The rule columns read "monthly" underneath; that is not a second schedule.
    assert back.pay_schedule is None


def test_the_next_pay_date_follows_the_weekend_rule(db, user):
    job = create_job(db, user.id, job_create(pay_days=SEMI_MONTHLY))
    assert next_pay_on(row(db, job), D(2026, 10, 16)) == D(2026, 10, 30)


def test_safe_to_spend_measures_to_the_day_before_the_moved_payday(db, user):
    """The bug this fixes: a payday read as Saturday when it is paid Friday
    made safe to spend count on the money a day late."""
    create_job(db, user.id, job_create(pay_days=SEMI_MONTHLY))
    ends_on, real_payday = window(db, user.id, D(2026, 10, 20))
    assert (ends_on, real_payday) == (D(2026, 10, 29), True)


def test_the_forecast_and_earnings_read_the_same_dates(db, user):
    job = create_job(db, user.id, job_create(pay_days=SEMI_MONTHLY))
    stored = row(db, job)
    assert forecast_pay_dates(stored, D(2026, 10, 1), D(2026, 11, 30)) == [
        D(2026, 10, 15), D(2026, 10, 30), D(2026, 11, 13), D(2026, 11, 30)]
    # A salaried job expects one cheque per pay date: two in October.
    assert periods_in(stored, D(2026, 10, 1), D(2026, 10, 31)) == 2


def test_switching_from_a_rule_to_days_and_back(db, user):
    job = create_job(db, user.id, job_create(pay_schedule=FORTNIGHTLY))
    switched = update_job(db, user.id, job.id, JobUpdate(pay_schedule=None, pay_days=SEMI_MONTHLY))
    assert switched.pay_days == SEMI_MONTHLY and switched.pay_schedule is None

    back = update_job(db, user.id, job.id, JobUpdate(pay_schedule=FORTNIGHTLY, pay_days=None))
    assert back.pay_days is None
    assert back.pay_schedule.freq == Frequency.WEEKLY and back.pay_schedule.interval == 2
    stored = row(db, job)
    assert (stored.pay_month_days, stored.pay_last_day, stored.pay_nth_weekdays) == (None, False, None)


def test_an_edit_that_leaves_the_schedule_out_keeps_it(db, user):
    job = create_job(db, user.id, job_create(pay_days=SEMI_MONTHLY))
    renamed = update_job(db, user.id, job.id, JobUpdate(name="Library"))
    assert renamed.pay_days == SEMI_MONTHLY


def test_choosing_doesnt_repeat_stops_the_schedule(db, user):
    """It did not: a null pay_schedule was skipped, so a schedule once set could
    only be stopped by clearing the first pay date."""
    job = create_job(db, user.id, job_create(pay_schedule=FORTNIGHTLY))
    stopped = update_job(db, user.id, job.id, JobUpdate(pay_schedule=None))
    assert stopped.pay_schedule is None and stopped.next_pay_on is None

    job = create_job(db, user.id, job_create(name="Cafe", pay_days=SEMI_MONTHLY))
    stopped = update_job(db, user.id, job.id, JobUpdate(pay_days=None))
    assert stopped.pay_days is None and stopped.pay_schedule is None and stopped.next_pay_on is None


def test_an_edit_asking_for_both_is_refused(db, user):
    job = create_job(db, user.id, job_create(pay_days=SEMI_MONTHLY))
    with pytest.raises(ValueError):
        update_job(db, user.id, job.id, JobUpdate(pay_schedule=FORTNIGHTLY))


def test_a_rule_job_still_pays_by_its_rule(db, user):
    job = create_job(db, user.id, job_create(pay_schedule=FORTNIGHTLY, pay_starts_on=D(2026, 9, 11)))
    assert next_pay_on(row(db, job), D(2026, 9, 12)) == D(2026, 9, 25)


# --- through the API ---------------------------------------------------------

def test_the_api_saves_and_returns_days_of_the_month(db, user):
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        created = client.post(f"/api/jobs/{user.id}/jobs", headers=headers, json={
            "name": "Bookstore", "kind": "salaried", "period_amount": 1500,
            "pay_starts_on": "2026-09-15",
            "pay_days": {"dates": [15], "last_day": True, "weekend": "previous"},
        })
        assert created.status_code in (200, 201), created.text
        body = created.json()
        assert body["pay_days"]["dates"] == [15] and body["pay_days"]["last_day"] is True
        assert body["pay_schedule"] is None

        refused = client.post(f"/api/jobs/{user.id}/jobs", headers=headers, json={
            "name": "Cafe", "kind": "salaried", "period_amount": 900, "pay_starts_on": "2026-09-15",
            "pay_days": {"dates": [15], "nth_weekdays": [{"n": -1, "day": "FR"}]},
        })
        assert refused.status_code == 422
    finally:
        app.main.app.dependency_overrides.pop(get_db, None)
