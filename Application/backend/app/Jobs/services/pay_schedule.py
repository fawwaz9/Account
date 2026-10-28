"""Turn a job's pay schedule into the dates it pays; the one place that does.

A job pays by the shared repeat rule (every other Friday, the 25th) or by set
days of the month: dates such as the 15th, the last day, or an Nth weekday such
as the last Friday. A set date the month lacks pays on its last day, and a set
date on a weekend moves as the job says. Safe-to-spend, the earnings figures,
the forecast and the year plan all read `pay_dates`; nothing is materialised.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.Calendar.schemas.event import Weekday
from app.Calendar.utils.recurrence import occurrences
from app.Calendar.utils.rule_columns import rule_of
from app.Jobs.schemas.job import NthWeekday, PayDays, WeekendRule

#: Weekday codes in `date.weekday()` order, Monday first.
CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


@dataclass(frozen=True)
class Pattern:
    """A job's set-days-of-the-month schedule, as read from its columns.

    Attributes:
        dates: Days of the month, 1-31.
        last_day: Whether it also pays on the month's last day.
        nth: (n, weekday code) pairs; n is 1-4, or -1 for the last.
        weekend: Where a set date on a weekend moves.
        until: Last scheduled pay date, inclusive; None for no end.
    """

    dates: tuple[int, ...]
    last_day: bool
    nth: tuple[tuple[int, str], ...]
    weekend: WeekendRule
    until: date | None


def parse_nth(text: str | None) -> tuple[tuple[int, str], ...]:
    """Parse a stored Nth-weekday list such as "-1FR,2TH" into (n, code) pairs.

    Args:
        text: The stored `pay_nth_weekdays` value.

    Returns:
        The pairs in stored order; empty for None or an empty string.
    """
    if not text:
        return ()
    return tuple((int(item[:-2]), item[-2:]) for item in text.split(",") if item)


def format_nth(items: list[NthWeekday]) -> str | None:
    """Format Nth weekdays as the stored string ("-1FR,2TH"), or None for none.

    Args:
        items: Nth weekdays; may be empty.

    Returns:
        Comma-joined `n` and weekday codes, or None when `items` is empty.
    """
    return ",".join(f"{item.n}{item.day.value}" for item in items) or None


def pattern_of(job) -> Pattern | None:
    """Return the job's set-days pattern, or None when it pays by the shared rule.

    Args:
        job: A job row.

    Returns:
        The pattern, with its end taken from `recur_until`; None when no set
        dates, last day or Nth weekdays are stored.
    """
    dates = tuple(int(day) for day in (job.pay_month_days or "").split(",") if day)
    nth = parse_nth(job.pay_nth_weekdays)
    if not dates and not job.pay_last_day and not nth:
        return None
    return Pattern(
        dates=dates,
        last_day=bool(job.pay_last_day),
        nth=nth,
        weekend=WeekendRule(job.pay_weekend or WeekendRule.PREVIOUS.value),
        until=job.recur_until,
    )


def pay_days_of(job) -> PayDays | None:
    """Return the job's set-days pattern as the API's `PayDays`, or None.

    Args:
        job: The job row.

    Returns:
        The pattern, or None when the job pays by its repeat rule or not at all.
    """
    pattern = pattern_of(job)
    if pattern is None:
        return None
    return PayDays(
        dates=list(pattern.dates),
        last_day=pattern.last_day,
        nth_weekdays=[NthWeekday(n=n, day=Weekday(day)) for n, day in pattern.nth],
        weekend=pattern.weekend,
        until=pattern.until,
    )


def apply_pay_days(job, pay_days: PayDays | None) -> None:
    """Write a set-days pattern onto a job's columns, or clear the pattern.

    Writing also sets the shared rule's columns to a plain monthly rule ending on
    the pattern's `until`, so "has a pay schedule" is still one column. Clearing
    touches only the pattern's own columns; the caller writes the rule. Only
    changes the row.

    Args:
        job: A job row.
        pay_days: The pattern to store; None clears it.
    """
    if pay_days is None:
        job.pay_month_days = None
        job.pay_last_day = False
        job.pay_nth_weekdays = None
        job.pay_weekend = None
        return

    job.pay_month_days = ",".join(str(day) for day in sorted(pay_days.dates)) or None
    job.pay_last_day = pay_days.last_day
    job.pay_nth_weekdays = format_nth(pay_days.nth_weekdays)
    job.pay_weekend = pay_days.weekend.value
    job.recur_freq = "monthly"
    job.recur_interval = 1
    job.recur_byday = None
    job.recur_until = pay_days.until
    job.recur_count = None


def nth_weekday(year: int, month: int, n: int, code: str) -> date | None:
    """Return the Nth (or with n=-1, the last) given weekday of a month.

    Args:
        year: The year.
        month: The month, 1-12.
        n: 1 to 4, or -1 for the last.
        code: A weekday code, "MO" to "SU".

    Returns:
        The date; None when the month has no Nth such weekday.
    """
    target = CODES.index(code)
    days = calendar.monthrange(year, month)[1]
    matching = [day for day in range(1, days + 1) if date(year, month, day).weekday() == target]
    if n == -1:
        return date(year, month, matching[-1])
    return date(year, month, matching[n - 1]) if n <= len(matching) else None


def off_weekend(day: date, rule: WeekendRule) -> date:
    """Move a Saturday or Sunday pay date as the job's weekend rule says.

    Args:
        day: The scheduled date.
        rule: Previous (the Friday before), next (the Monday after) or keep.

    Returns:
        The date it is paid; weekdays are returned unchanged.
    """
    if day.weekday() < 5 or rule == WeekendRule.KEEP:
        return day
    if rule == WeekendRule.PREVIOUS:
        return day - timedelta(days=day.weekday() - 4)
    return day + timedelta(days=7 - day.weekday())


def months_between(start: date, end: date):
    """Yield (year, month) for every month from `start`'s through `end`'s, inclusive.

    Args:
        start: Any date in the first month.
        end: Any date in the last month.

    Yields:
        (year, month) pairs in order; nothing when `end` is in an earlier month.
    """
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def pattern_dates(pattern: Pattern, starts_on: date, start: date, end: date) -> list[date]:
    """Return every pay date a set-days pattern produces in a window.

    Months are expanded a week beyond each end of the window so a date the weekend
    rule moves across the edge is still found. `starts_on` and `until` are compared
    with the scheduled date, before any weekend move.

    Args:
        pattern: The job's pattern.
        starts_on: The job's first pay date.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The dates paid, ascending and without duplicates.
    """
    found: set[date] = set()
    for year, month in months_between(start - timedelta(days=7), end + timedelta(days=7)):
        last = calendar.monthrange(year, month)[1]
        scheduled: list[tuple[date, bool]] = []
        for n, code in pattern.nth:
            day = nth_weekday(year, month, n, code)
            if day is not None:
                scheduled.append((day, False))
        for number in pattern.dates:
            # A day the month lacks pays on its last day (decided 2026-10-03).
            scheduled.append((date(year, month, min(number, last)), True))
        if pattern.last_day:
            scheduled.append((date(year, month, last), True))

        for day, movable in scheduled:
            if day < starts_on or (pattern.until is not None and day > pattern.until):
                continue
            paid = off_weekend(day, pattern.weekend) if movable else day
            if start <= paid <= end:
                found.add(paid)
    return sorted(found)


def pay_dates(job, start: date, end: date) -> list[date]:
    """Return every date a job pays in a window, by whichever schedule it has.

    Args:
        job: A job row.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The pay dates, ascending; empty when the job has no schedule or no first
        pay date.
    """
    if job.pay_starts_on is None or not job.recur_freq:
        return []
    pattern = pattern_of(job)
    if pattern is not None:
        return pattern_dates(pattern, job.pay_starts_on, start, end)
    return occurrences(rule_of(job), job.pay_starts_on, start, end)
