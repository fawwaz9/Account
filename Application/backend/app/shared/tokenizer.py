"""One parser for quick-typed text: course codes, dates, durations, amounts and scores.

`parse` turns a line such as "CPSC 221 midterm 78/100 fri" into structured fields
plus the leftover title; quick capture and the omnibox both read it. Pure text in,
fields out: resolving a code to a course needs the database and happens elsewhere.
More specific patterns claim their text first, a bare number is never an amount,
and a weekday means the next one on or after today.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

#: Words that only ever glue a date to the rest of a phrase. Dropped from the
#: leftover title when they sit beside something that parsed.
FILLER = {"due", "by", "on", "at", "the", "for", "in", "next", "this"}

WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
"""Weekday words and abbreviations, mapped to `date.weekday()` numbers (Monday is 0)."""

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
"""Month names and abbreviations, mapped to month numbers."""

MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))
"""Regex alternation of every month word, longest first so "june" beats "jun"."""
WEEKDAY_NAMES = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
"""Regex alternation of every weekday word, longest first so "friday" beats "fri"."""

#: A course code as this app stores them: COSC 101, CPSC_V 210, ENG 109. The
#: separator is optional so "cs221" typed in a hurry still matches; whether such
#: a code exists is the resolver's problem, not this one's.
COURSE_PATTERN = re.compile(
    r"\b([A-Za-z]{2,5}(?:_[A-Za-z])?)[\s\-_]*(\d{3}[A-Za-z]?)\b"
)

SCORE_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\b")
"""A score over a maximum, such as "78/100" or "7.5 / 10"."""

#: Money needs saying so. A bare integer is far more often a course number, a
#: question count or a week number than it is a price.
AMOUNT_PATTERN = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)|\b(\d+\.\d{2})\b")

HOURS_MINUTES_PATTERN = re.compile(
    r"\b(\d+)\s*(?:h|hr|hrs|hour|hours)\s*(\d{1,2})?\s*(?:m|min|mins|minute|minutes)?\b",
    re.IGNORECASE,
)
MINUTES_PATTERN = re.compile(r"\b(\d+)\s*(?:m|min|mins|minute|minutes)\b", re.IGNORECASE)

ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
MONTH_FIRST_PATTERN = re.compile(rf"\b({MONTH_NAMES})\.?\s+(\d{{1,2}})\b", re.IGNORECASE)
DAY_FIRST_PATTERN = re.compile(rf"\b(\d{{1,2}})\s+({MONTH_NAMES})\.?\b", re.IGNORECASE)
RELATIVE_PATTERN = re.compile(
    r"\bin\s+(\d+)\s*(day|days|week|weeks)\b", re.IGNORECASE
)
NAMED_DAY_PATTERN = re.compile(r"\b(today|tonight|tomorrow|tmr|tmrw|yesterday)\b", re.IGNORECASE)
WEEKDAY_PATTERN = re.compile(rf"\b(next\s+)?({WEEKDAY_NAMES})\b", re.IGNORECASE)


@dataclass
class Parsed:
    """Everything `parse` found in one line of text, plus what was left of it.

    Attributes:
        text: The input, unchanged.
        title: What remains once every match and the filler beside it is removed.
        course_code: A course code's letters and number joined by one space, such as "cs
            221"; None if none was found.
        on_date: The date a date word resolved to; None if none was found.
        minutes: A duration in minutes; None if none was found.
        amount: Dollars, from "$4" or a two-decimal figure; None if none was found.
        score: Points earned from "78/100"; None if no score was found.
        max_score: Points possible from "78/100"; None if no score was found.
        matched: Kinds found, in order: "score", "duration", "date", "course", "amount".
    """

    #: The raw text, unchanged, so a caller can always fall back to it.
    text: str
    #: What is left once every match is removed -- the title, in practice.
    title: str = ""
    #: As typed: "cs221", "CPSC_V 210". Normalising it is the resolver's job,
    #: since only the database knows which spellings exist.
    course_code: str | None = None
    on_date: date | None = None
    minutes: int | None = None
    amount: float | None = None
    score: float | None = None
    max_score: float | None = None
    #: Which kinds matched, so a caller can say what it understood without
    #: comparing every field against None.
    matched: list[str] = field(default_factory=list)

    @property
    def found_anything(self) -> bool:
        """Whether any token was recognised."""
        return bool(self.matched)


def parse(text: str, today: date) -> Parsed:
    """Pull every recognisable token out of one line, most specific pattern first.

    The order is score, duration, date, course code, then amount, and each match claims
    its span so a later, looser pattern cannot re-read its digits. Only the first match
    of each kind is kept.

    Args:
        text: The line as typed.
        today: The user's local today, which every relative date word resolves against.

    Returns:
        The parsed fields, with the unmatched remainder as the title.
    """
    now = today
    result = Parsed(text=text)

    # Spans already claimed. A later, looser pattern must not re-read digits a
    # tighter one has taken -- without this, the 100 in "78/100" becomes a
    # course number and the 1 in "1h30" becomes an amount.
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        """Return True when no claimed span overlaps `start`-`end`."""
        return not any(start < claimed_end and end > claimed_start
                       for claimed_start, claimed_end in taken)

    def claim(start: int, end: int, kind: str) -> None:
        """Mark a span as taken and record the kind of token found in it."""
        taken.append((start, end))
        if kind not in result.matched:
            result.matched.append(kind)

    # 1. Score, before anything else reads either of its numbers.
    match = SCORE_PATTERN.search(text)
    if match and free(*match.span()):
        result.score = float(match.group(1))
        result.max_score = float(match.group(2))
        claim(*match.span(), "score")

    # 2. Duration, before an amount can read its leading number.
    for pattern, reader in (
        (HOURS_MINUTES_PATTERN, _hours_minutes),
        (MINUTES_PATTERN, _minutes),
    ):
        if result.minutes is not None:
            break
        for match in pattern.finditer(text):
            if free(*match.span()):
                result.minutes = reader(match)
                claim(*match.span(), "duration")
                break

    # 3. Dates, most explicit form first.
    for pattern, reader in (
        (ISO_DATE_PATTERN, _iso_date),
        (MONTH_FIRST_PATTERN, _month_first),
        (DAY_FIRST_PATTERN, _day_first),
        (RELATIVE_PATTERN, _relative),
        (NAMED_DAY_PATTERN, _named_day),
        (WEEKDAY_PATTERN, _weekday),
    ):
        if result.on_date is not None:
            break
        for match in pattern.finditer(text):
            if not free(*match.span()):
                continue
            parsed_date = reader(match, now)
            if parsed_date is None:
                continue
            result.on_date = parsed_date
            claim(*match.span(), "date")
            break

    # 4. Course code. After dates, so "sep 12" is never read as a code, and
    #    after the score so "78/100" keeps its numbers.
    for match in COURSE_PATTERN.finditer(text):
        if not free(*match.span()):
            continue
        result.course_code = f"{match.group(1)} {match.group(2)}".strip()
        claim(*match.span(), "course")
        break

    # 5. Amount, last: by now every number that meant something else is claimed.
    for match in AMOUNT_PATTERN.finditer(text):
        if not free(*match.span()):
            continue
        result.amount = float(match.group(1) or match.group(2))
        claim(*match.span(), "amount")
        break

    result.title = _leftover(text, taken)
    return result


def _hours_minutes(match: re.Match) -> int:
    """Return the minutes in an "1h30"-style match."""
    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def _minutes(match: re.Match) -> int:
    """Return the minutes in a "45m"-style match."""
    return int(match.group(1))


def _iso_date(match: re.Match, _today: date) -> date | None:
    """Return the date in a "2026-10-23" match, or None if it is not a real date."""
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _month_first(match: re.Match, today: date) -> date | None:
    """Return the next occurrence of a "sep 12"-style month and day."""
    return _month_and_day(MONTHS[match.group(1).lower()], int(match.group(2)), today)


def _day_first(match: re.Match, today: date) -> date | None:
    """Return the next occurrence of a "12 sep"-style day and month."""
    return _month_and_day(MONTHS[match.group(2).lower()], int(match.group(1)), today)


def _month_and_day(month: int, day: int, today: date) -> date | None:
    """Return the next date on or after today with this month and day.

    Tries this year, then next; returns None for a day the month never has, or as soon
    as this year lacks it (February 29 outside a leap year).
    """
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def _relative(match: re.Match, today: date) -> date:
    """Return today plus the days or weeks in an "in 3 days" match."""
    count = int(match.group(1))
    unit = match.group(2).lower()
    return today + timedelta(weeks=count) if unit.startswith("week") else today + timedelta(days=count)


def _named_day(match: re.Match, today: date) -> date:
    """Return the date a word such as "today", "tomorrow" or "yesterday" names."""
    word = match.group(1).lower()
    if word in ("tomorrow", "tmr", "tmrw"):
        return today + timedelta(days=1)
    if word == "yesterday":
        return today - timedelta(days=1)
    return today


def _weekday(match: re.Match, today: date) -> date:
    """Return the next such weekday counting today; "next" adds a week."""
    wanted = WEEKDAYS[match.group(2).lower()]
    ahead = (wanted - today.weekday()) % 7
    # "next fri" is the Friday of the following week, whichever day it is said
    # on -- including on a Friday, where plain "fri" is today.
    if match.group(1):
        ahead += 7
    return today + timedelta(days=ahead)


def _leftover(text: str, taken: list[tuple[int, int]]) -> str:
    """Return the text minus every claimed span, with filler trimmed from the ends."""
    kept = []
    cursor = 0
    for start, end in sorted(taken):
        kept.append(text[cursor:start])
        cursor = max(cursor, end)
    kept.append(text[cursor:])

    remainder = " ".join(" ".join(kept).split())
    # Filler only ever glued a date to the rest, so with the date gone it is
    # noise. Stripped from the ends only: "read the handout" keeps its "the".
    words = remainder.split()
    while words and words[0].lower().strip(".,") in FILLER:
        words.pop(0)
    while words and words[-1].lower().strip(".,") in FILLER:
        words.pop()

    return " ".join(words).strip(" ,-")
