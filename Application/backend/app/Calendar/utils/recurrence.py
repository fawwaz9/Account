"""Expand a stored repeat rule into the dates it falls on.

A repeating thing is stored as its rule (five `recur_*` columns), never as a row
per date; this module turns the rule into occurrences on read, for the window a
caller asks for. It is pure (dates in, dates out, no session or models) and is
the one scheduler behind class times, shifts, standing payments, repeating tasks
and pay schedules.
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
    """A repeat rule: how often, on which weekdays, and when it stops.

    Attributes:
        freq: "daily", "weekly" or "monthly"; None, or any other value, is a one-off.
        interval: Units of `freq` between occurrences; values below 1 act as 1.
        byday: Weekday codes ("MO" to "SU") a weekly rule falls on; empty means the
            weekday `starts_on` falls on. Ignored by other frequencies.
        until: Last date the series may produce, inclusive; None for no end date.
        count: How many occurrences the series runs, counted from its first date;
            None for no limit.

    Note:
        The API's `Recurrence` refuses `until` and `count` together; if both reach
        the engine anyway, whichever ends the series first wins.
    """

    freq: str | None = None
    interval: int = 1
    #: Weekly only. Empty means "the weekday the event starts on".
    byday: tuple[str, ...] = ()
    #: Inclusive. Never set alongside `count`.
    until: date | None = None
    count: int | None = None

    @property
    def repeats(self) -> bool:
        """Whether the rule repeats at all, rather than describing a one-off."""
        return self.freq in FREQUENCIES


def parse_byday(raw: str | None) -> tuple[str, ...]:
    """Parse a stored weekday list such as "MO,WE,FR" into a tuple of codes.

    Args:
        raw: Comma-separated weekday codes, any case, as stored in `recur_byday`.

    Returns:
        The recognised codes in the order given; unknown parts are dropped and
        duplicates kept. Empty for None or an empty string.
    """
    if not raw:
        return ()

    codes = [part.strip().upper() for part in raw.split(",")]
    return tuple(code for code in codes if code in WEEKDAY_CODES)


def format_byday(codes: Iterable[str]) -> str | None:
    """Format weekday codes as the stored comma-separated string.

    Args:
        codes: Weekday codes in any order and case; unknown codes are ignored.

    Returns:
        The distinct codes joined in Monday-to-Sunday order (for example
        "MO,WE,FR"), or None when no valid code remains.
    """
    kept = {code.strip().upper() for code in codes if code.strip().upper() in WEEKDAY_CODES}
    if not kept:
        return None

    return ",".join(code for code in WEEKDAY_CODES if code in kept)


def add_months(anchor: date, months: int) -> date | None:
    """Return the same day of the month a number of months later.

    Args:
        anchor: The starting date; its day of the month is kept.
        months: How many months to move forward (negative moves back).

    Returns:
        The shifted date, or None when the target month lacks that day (the 31st in
        April, the 29th of February in a common year).

    Note:
        The missing day is skipped rather than clamped to the month's end, so a
        standing payment on the 31st never quietly moves to the 30th.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    try:
        return date(year, month, anchor.day)
    except ValueError:
        return None


def _generated_dates(rule: Rule, starts_on: date) -> Iterator[date]:
    """Yield every date the rule produces from `starts_on`, ascending and unbounded.

    The caller applies `until`, `count` and its window; a one-off yields only
    `starts_on`.
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
    """Return the dates a repeating item falls on inside a window.

    Walks the series from its own start, so `count` means the whole series rather
    than the part inside the window: paging forward never reveals occurrences past
    the end of a five-time series.

    Args:
        rule: The repeat rule; a one-off rule yields at most `starts_on`.
        starts_on: The first date of the series, which anchors the rule.
        window_start: First date to report, inclusive.
        window_end: Last date to report, inclusive.
        skipped: Cancelled dates to leave out. Each one still uses up one of
            `count`, as cancelling one week of a five-week booking leaves four.

    Returns:
        The occurrence dates in ascending order; empty when none fall in the
        window. Capped at `MAX_OCCURRENCES` dates, and the walk stops after
        `MAX_STEPS` generated dates, so an extreme window is silently truncated.
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
