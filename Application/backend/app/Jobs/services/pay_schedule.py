"""When a job pays: the one place that turns a job's pay schedule into dates.

A job pays either by the shared repeat rule (every other Friday, the 25th of each
month) or by set days of the month (next.md, decided 2026-10-03): dates such as
the 15th and the 30th, the last day of the month, or an Nth weekday such as the
last Friday. The second exists because the shared rule cannot say any of those,
and because it skips a month that lacks the date. That is right for rent, where
inventing a date would move it, and wrong for pay, where it means no cheque in
February.

Safe to spend (through `next_pay_on`), the earnings figures, the forecast and the
year plan all read pay dates from here. They used to build the rule each on its
own, three copies that a fourth pattern would have had to reach separately.

Nothing is ever materialised: a cheque exists because one arrived and was
entered, never because a date came round.
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
    """Set days of the month, as stored on a job."""

    dates: tuple[int, ...]
    last_day: bool
    nth: tuple[tuple[int, str], ...]
    weekend: WeekendRule
    until: date | None


def parse_nth(text: str | None) -> tuple[tuple[int, str], ...]:
    """'-1FR,2TH' -> ((-1, 'FR'), (2, 'TH'))."""
    if not text:
        return ()
    return tuple((int(item[:-2]), item[-2:]) for item in text.split(",") if item)


def format_nth(items: list[NthWeekday]) -> str | None:
    return ",".join(f"{item.n}{item.day.value}" for item in items) or None


def pattern_of(job) -> Pattern | None:
    """The job's days-of-the-month pattern, or None when it pays by the rule."""
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
    """The pattern as the API's object, for reading a job back."""
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
    """Write a pattern onto the job, or clear it.

    A pattern also sets `recur_freq` to "monthly", with nothing else on the rule
    but its end, so every check of "does this job have a pay schedule" keeps
    reading one column. Clearing touches only the pattern's own columns; the
    caller writes the rule.
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
    """The Nth (or, with -1, the last) given weekday of a month."""
    target = CODES.index(code)
    days = calendar.monthrange(year, month)[1]
    matching = [day for day in range(1, days + 1) if date(year, month, day).weekday() == target]
    if n == -1:
        return date(year, month, matching[-1])
    return date(year, month, matching[n - 1]) if n <= len(matching) else None


def off_weekend(day: date, rule: WeekendRule) -> date:
    """Move a Saturday or Sunday pay date as the job says. Weekdays stay."""
    if day.weekday() < 5 or rule == WeekendRule.KEEP:
        return day
    if rule == WeekendRule.PREVIOUS:
        return day - timedelta(days=day.weekday() - 4)
    return day + timedelta(days=7 - day.weekday())


def months_between(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def pattern_dates(pattern: Pattern, starts_on: date, start: date, end: date) -> list[date]:
    """Every pay date the pattern produces in [start, end], from `starts_on` on.

    A month is expanded a week either side of the window, so a date the
    weekend rule moves across the window's edge is still found. `starts_on` and
    `until` are compared with the date as scheduled, before it moves: "the
    first cheque is the 15th" means the 15th's cheque, wherever the weekend
    puts it.
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
    """Every date this job pays in [start, end], by whichever schedule it has."""
    if job.pay_starts_on is None or not job.recur_freq:
        return []
    pattern = pattern_of(job)
    if pattern is not None:
        return pattern_dates(pattern, job.pay_starts_on, start, end)
    return occurrences(rule_of(job), job.pay_starts_on, start, end)
