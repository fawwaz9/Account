"""The recurrence engine, which three features are going to depend on.

Expansion is pure arithmetic over dates, so it is testable without a database
and there is no excuse for it to be wrong. The cases here are the ones that are
easy to get subtly wrong and hard to notice: the count/window interaction, a
weekly rule starting mid-week, and a monthly rule on the 31st.
"""
from datetime import date

from app.Calendar.utils.recurrence import (
    Rule,
    add_months,
    format_byday,
    occurrences,
    parse_byday,
)

SEPTEMBER = date(2026, 9, 1)


def expand(rule, starts_on, start, end, skipped=()):
    return occurrences(rule, starts_on, start, end, skipped)


# ------------------------------------------------------------------ one-off --

def test_a_one_off_falls_on_its_own_date():
    rule = Rule()
    assert expand(rule, SEPTEMBER, date(2026, 9, 1), date(2026, 9, 30)) == [SEPTEMBER]


def test_a_one_off_outside_the_window_does_not_appear():
    assert expand(Rule(), SEPTEMBER, date(2026, 10, 1), date(2026, 10, 31)) == []


# -------------------------------------------------------------------- daily --

def test_daily_every_other_day():
    dates = expand(Rule(freq="daily", interval=2), SEPTEMBER, SEPTEMBER, date(2026, 9, 7))
    assert dates == [date(2026, 9, d) for d in (1, 3, 5, 7)]


# ------------------------------------------------------------------- weekly --

def test_weekly_uses_the_starting_weekday_when_no_days_are_given():
    # 1 Sep 2026 is a Tuesday.
    dates = expand(Rule(freq="weekly"), SEPTEMBER, SEPTEMBER, date(2026, 9, 30))
    assert dates == [date(2026, 9, d) for d in (1, 8, 15, 22, 29)]


def test_weekly_on_several_days_starting_mid_week():
    """A Monday/Wednesday/Friday class that starts on the Wednesday.

    The Monday of that first week is before the course begins, so it must not
    appear -- but every later Monday must. Anchoring the rule to the start date
    rather than to the week is what gets this wrong.
    """
    wednesday = date(2026, 9, 2)
    rule = Rule(freq="weekly", byday=("MO", "WE", "FR"))
    dates = expand(rule, wednesday, date(2026, 9, 1), date(2026, 9, 14))

    assert dates == [date(2026, 9, d) for d in (2, 4, 7, 9, 11, 14)]


def test_weekly_with_an_interval_skips_whole_weeks():
    rule = Rule(freq="weekly", interval=2, byday=("TU",))
    dates = expand(rule, SEPTEMBER, SEPTEMBER, date(2026, 10, 31))
    assert dates == [date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 29), date(2026, 10, 13), date(2026, 10, 27)]


# ------------------------------------------------------------------ monthly --

def test_monthly_keeps_the_day_of_the_month():
    rule = Rule(freq="monthly")
    dates = expand(rule, date(2026, 1, 15), date(2026, 1, 1), date(2026, 4, 30))
    assert dates == [date(2026, m, 15) for m in (1, 2, 3, 4)]


def test_monthly_on_the_31st_skips_months_that_have_no_31st():
    """February has no 31st, and inventing the 28th would move a rent day."""
    rule = Rule(freq="monthly")
    dates = expand(rule, date(2026, 1, 31), date(2026, 1, 1), date(2026, 5, 31))
    assert dates == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]


# --------------------------------------------------------------------- ends --

def test_until_is_inclusive():
    rule = Rule(freq="daily", until=date(2026, 9, 3))
    assert expand(rule, SEPTEMBER, SEPTEMBER, date(2026, 9, 30)) == [
        date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3),
    ]


def test_count_is_measured_from_the_start_not_from_the_window():
    """Paging forward must not hand back occurrences the series never had.

    A five-times rule starting 1 September is finished by the 5th. Asking for
    the 4th to the 30th may return two dates; counting from the window start
    would return twenty-seven.
    """
    rule = Rule(freq="daily", count=5)
    assert expand(rule, SEPTEMBER, date(2026, 9, 4), date(2026, 9, 30)) == [
        date(2026, 9, 4), date(2026, 9, 5),
    ]


def test_a_skipped_date_still_consumes_one_of_the_count():
    """Cancelling one week of a five-week booking leaves four, not five."""
    rule = Rule(freq="daily", count=5)
    dates = expand(rule, SEPTEMBER, SEPTEMBER, date(2026, 9, 30), skipped=[date(2026, 9, 3)])
    assert dates == [date(2026, 9, d) for d in (1, 2, 4, 5)]


def test_skipped_dates_are_removed_from_the_series():
    rule = Rule(freq="weekly", byday=("TU",))
    dates = expand(rule, SEPTEMBER, SEPTEMBER, date(2026, 9, 30), skipped=[date(2026, 9, 15)])
    assert date(2026, 9, 15) not in dates
    assert date(2026, 9, 22) in dates


def test_an_endless_daily_rule_is_bounded_by_the_window():
    dates = expand(Rule(freq="daily"), SEPTEMBER, date(2026, 9, 1), date(2026, 9, 30))
    assert len(dates) == 30


# ------------------------------------------------------------------ codings --

def test_byday_round_trips_in_week_order():
    assert format_byday(["FR", "mo", "WE"]) == "MO,WE,FR"
    assert parse_byday("MO,WE,FR") == ("MO", "WE", "FR")


def test_byday_ignores_anything_unrecognised():
    assert parse_byday("MO,XX,FR") == ("MO", "FR")
    assert parse_byday(None) == ()
    assert format_byday([]) is None


def test_add_months_returns_none_for_a_day_the_month_does_not_have():
    assert add_months(date(2026, 1, 31), 1) is None
    assert add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)
