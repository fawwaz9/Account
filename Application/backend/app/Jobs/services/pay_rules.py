"""British Columbia's pay rules, as arithmetic over shifts. Pure: no session.

Phase 1 item 11 (account-vision.md §13.11). Hourly student workers are
underpaid routinely and rarely notice, and the two most commonly missed items
are overtime and vacation pay. These are the rules the check applies, and every
figure it produces names the one it came from.

* **Overtime** -- Employment Standards Act s.40. Time and a half for hours over
  8 in a day, up to 12; double time over 12 in a day; time and a half for
  hours over 40 in a week, not counting hours already paid as daily overtime.
  A week is seven days beginning on Sunday.
* **Vacation pay** -- s.58. 4% of gross wages, 6% after five years with the
  same employer. Tips are not wages for this.

Deliberately not here: statutory holiday pay (s.44-45). Its eligibility test
reaches outside the pay period and a wrong "you're short" costs as much trust
as a missed one, so the check says it is not checked rather than guessing.
"""

from dataclasses import dataclass
from datetime import date, time, timedelta

#: Minutes in a day before daily overtime, and before double time.
DAILY_REGULAR = 8 * 60
DAILY_DOUBLE = 12 * 60
#: Regular minutes in a week before weekly overtime.
WEEKLY_REGULAR = 40 * 60

REGULAR = "regular"
DAILY_OVERTIME = "daily_overtime"
DOUBLE_TIME = "double_time"
WEEKLY_OVERTIME = "weekly_overtime"

MULTIPLIER = {REGULAR: 1.0, DAILY_OVERTIME: 1.5, DOUBLE_TIME: 2.0, WEEKLY_OVERTIME: 1.5}
RULE = {
    REGULAR: None,
    DAILY_OVERTIME: "BC Employment Standards Act s.40(1): 1.5x for hours over 8 in a day",
    DOUBLE_TIME: "BC Employment Standards Act s.40(1): 2x for hours over 12 in a day",
    WEEKLY_OVERTIME: "BC Employment Standards Act s.40(2): 1.5x for hours over 40 in a week",
}


@dataclass(frozen=True)
class Worked:
    """One shift's time: when, how long, at what rate."""

    on_date: date
    minutes: int
    rate: float
    starts_at: time | None = None


@dataclass(frozen=True)
class Portion:
    """Some of a shift's minutes, all paid the same way."""

    on_date: date
    kind: str
    minutes: int
    rate: float

    @property
    def amount(self) -> float:
        return self.minutes / 60 * self.rate * MULTIPLIER[self.kind]


def week_start(day: date) -> date:
    """The Sunday a day's week begins on."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def split(shifts: list[Worked]) -> list[Portion]:
    """Divide every shift's minutes into regular, daily overtime, double time
    and weekly overtime.

    Daily first, over the day's shifts in the order they were worked. Then the
    weekly cap over what is still regular, taking the *latest* regular minutes
    in the week as the overtime, since those are the hours past forty.
    """
    ordered = sorted(shifts, key=lambda s: (s.on_date, s.starts_at or time.min))
    daily: list[Portion] = []
    used_today: dict[date, int] = {}
    for shift in ordered:
        before = used_today.get(shift.on_date, 0)
        after = before + shift.minutes
        used_today[shift.on_date] = after
        regular = max(0, min(after, DAILY_REGULAR) - before)
        double = max(0, after - max(before, DAILY_DOUBLE))
        overtime = shift.minutes - regular - double
        for kind, minutes in ((REGULAR, regular), (DAILY_OVERTIME, overtime), (DOUBLE_TIME, double)):
            if minutes > 0:
                daily.append(Portion(shift.on_date, kind, minutes, shift.rate))

    out: list[Portion] = []
    regular_this_week: dict[date, int] = {}
    for portion in daily:
        if portion.kind != REGULAR:
            out.append(portion)
            continue
        week = week_start(portion.on_date)
        used = regular_this_week.get(week, 0)
        keep = max(0, min(portion.minutes, WEEKLY_REGULAR - used))
        regular_this_week[week] = used + keep
        if keep:
            out.append(Portion(portion.on_date, REGULAR, keep, portion.rate))
        if portion.minutes - keep:
            out.append(Portion(portion.on_date, WEEKLY_OVERTIME, portion.minutes - keep, portion.rate))
    return out


def vacation_percent(started_on: date | None, on_day: date) -> float:
    """4%, or 6% once employment with this employer reaches five years (s.58)."""
    if started_on is None:
        return 4.0
    try:
        fifth = started_on.replace(year=started_on.year + 5)
    except ValueError:  # 29 February
        fifth = started_on.replace(year=started_on.year + 5, day=28)
    return 6.0 if on_day >= fifth else 4.0
