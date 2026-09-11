"""Turning a repeat rule into the dates it actually falls on.

A repeating event is stored as the rule that generates it and nothing else.
Writing the occurrences out as rows would mean thirty-six lecture rows per
course per term, all of which need rewriting when the room changes, and no way
to ask "does this repeat?" without counting them. So occurrences are
materialised here, on read, for the window the caller asked for.

The rule is a small fixed set -- frequency, interval, weekdays, and an end
expressed either as a last date or a number of occurrences -- rather than a full
RFC 5545 RRULE string. A timetable, a monthly payment and a weekly chore are all
expressible in it, it survives being read in a database browser, and it needs no
parser. If something later genuinely needs BYSETPOS, that is the point to reach
for a library, not before.

This module is pure: dates in, dates out, no session and no models. It is meant
to be the one scheduler in the app -- class times, recurring payments and
repeating tasks all resolve through it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Iterator

DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"

FREQUENCIES = (DAILY, WEEKLY, MONTHLY)

#: Index matches date.weekday(), so a code converts to an offset by position.
WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

#: Ceiling on what one read can materialise. A daily event over a year is 365,
#: so this is generous for any real window while still bounding the response.
MAX_OCCURRENCES = 750

#: Ceiling on rule steps walked per read, so an event that started years before
#: the window cannot spin for long looking for its first date in range.
MAX_STEPS = 20_000


@dataclass(frozen=True)
class Rule:
    """How an event repeats. `freq` of None is a one-off."""

    freq: str | None = None
    interval: int = 1
    #: Weekly only. Empty means "the weekday the event starts on".
    byday: tuple[str, ...] = ()
    #: Inclusive. Never set alongside `count`.
    until: date | None = None
    count: int | None = None

    @property
    def repeats(self) -> bool:
        return self.freq in FREQUENCIES


def weekday_code(day: date) -> str:
    return WEEKDAY_CODES[day.weekday()]


def parse_byday(raw: str | None) -> tuple[str, ...]:
    """"MO,WE,FR" -> ("MO", "WE", "FR"), ignoring anything unrecognised."""
    if not raw:
        return ()

    codes = [part.strip().upper() for part in raw.split(",")]
    return tuple(code for code in codes if code in WEEKDAY_CODES)


def format_byday(codes: Iterable[str]) -> str | None:
    """Back to the stored form, in week order so the column reads sensibly."""
    kept = {code.strip().upper() for code in codes if code.strip().upper() in WEEKDAY_CODES}
    if not kept:
        return None

    return ",".join(code for code in WEEKDAY_CODES if code in kept)


def add_months(anchor: date, months: int) -> date | None:
    """The same day of the month, `months` later.

    None when the target month is too short: the 31st simply does not occur in
    February, and inventing the 28th for it would silently move a rent day.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    try:
        return date(year, month, anchor.day)
    except ValueError:
        return None


def _generated_dates(rule: Rule, starts_on: date) -> Iterator[date]:
    """Every date the rule produces, ascending and unbounded.

    Bounding is the caller's job, since `until`, `count` and the requested
    window each cut the sequence at a different point.
    """
    if not rule.repeats:
        yield starts_on
        return

    interval = max(1, rule.interval)

    if rule.freq == DAILY:
        step = timedelta(days=interval)
        current = starts_on
        while True:
            yield current
            current += step

    elif rule.freq == WEEKLY:
        offsets = sorted(WEEKDAY_CODES.index(code) for code in rule.byday)
        if not offsets:
            offsets = [starts_on.weekday()]

        # Anchored to the Monday of the starting week so that, on a rule like
        # "every Monday and Wednesday" starting on a Wednesday, the Monday of a
        # later week still lands -- while the Monday *before* the start does not.
        week_start = starts_on - timedelta(days=starts_on.weekday())
        while True:
            for offset in offsets:
                day = week_start + timedelta(days=offset)
                if day >= starts_on:
                    yield day
            week_start += timedelta(weeks=interval)

    elif rule.freq == MONTHLY:
        months = 0
        while True:
            day = add_months(starts_on, months)
            if day is not None:
                yield day
            months += interval


def occurrences(
    rule: Rule,
    starts_on: date,
    window_start: date,
    window_end: date,
    skipped: Iterable[date] = (),
) -> list[date]:
    """The dates this event falls on between `window_start` and `window_end`.

    Both ends inclusive. `count` is measured from the event's own start rather
    than from the window, so paging forward a month cannot hand you occurrences
    seven and eight of a series that was only meant to run five times.

    A skipped date consumes one of `count`, matching how an exception to a
    series behaves: cancelling one week of a five-week booking leaves four, not
    five running a week longer.
    """
    excluded = set(skipped)
    found: list[date] = []
    produced = 0

    for step, day in enumerate(_generated_dates(rule, starts_on)):
        if step >= MAX_STEPS:
            break
        if rule.until is not None and day > rule.until:
            break
        if rule.count is not None and produced >= rule.count:
            break

        produced += 1

        if day > window_end:
            break
        if day >= window_start and day not in excluded:
            found.append(day)
            if len(found) >= MAX_OCCURRENCES:
                break

    return found
