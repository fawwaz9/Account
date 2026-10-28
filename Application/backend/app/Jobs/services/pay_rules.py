"""British Columbia's pay rules as pure arithmetic over shifts; no session.

Overtime follows the Employment Standards Act s.40: time and a half past 8 hours
in a day up to 12, double time past 12, and time and a half past 40 regular
hours in a Sunday-to-Saturday week. Vacation pay follows s.58: 4% of gross
wages, 6% after five years with the employer. Statutory holiday pay is
deliberately not modelled. `paycheck_service` and `paycheque_service` use these.
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
    """One shift's time, as the pay rules take it.

    Attributes:
        on_date: The day it was worked.
        minutes: Minutes counted for it.
        rate: Hourly rate in dollars, before any multiplier.
        starts_at: Local start time, which orders shifts within a day; None sorts
            first.
    """

    on_date: date
    minutes: int
    rate: float
    starts_at: time | None = None


@dataclass(frozen=True)
class Portion:
    """Some of a shift's minutes, all paid under one rule.

    Attributes:
        on_date: The day worked.
        kind: "regular", "daily_overtime", "double_time" or "weekly_overtime".
        minutes: Minutes paid this way.
        rate: The base hourly rate, before the multiplier.
    """

    on_date: date
    kind: str
    minutes: int
    rate: float

    @property
    def amount(self) -> float:
        """Dollars these minutes earn: hours times rate times the rule's multiplier."""
        return self.minutes / 60 * self.rate * MULTIPLIER[self.kind]


def week_start(day: date) -> date:
    """Return the Sunday that begins the overtime week a day falls in.

    Args:
        day: Any date.

    Returns:
        The Sunday on or before `day`.
    """
    return day - timedelta(days=(day.weekday() + 1) % 7)


def split(shifts: list[Worked]) -> list[Portion]:
    """Divide shifts' minutes into regular, daily overtime, double and weekly overtime.

    Daily rules apply first, over each day's shifts in the order worked. The weekly
    cap then applies to what is still regular, taking the latest regular minutes in
    a week past 40 hours as weekly overtime.

    Args:
        shifts: The shifts, in any order.

    Returns:
        The portions, each with its own rule and rate; empty for no shifts.
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
    """Return the vacation-pay rate that applies on a day.

    Args:
        started_on: When employment began; None is taken as under five years.
        on_day: The day to judge on, such as the pay period's end.

    Returns:
        6.0 once five years have passed since `started_on`, otherwise 4.0.
    """
    if started_on is None:
        return 4.0
    try:
        fifth = started_on.replace(year=started_on.year + 5)
    except ValueError:  # 29 February
        fifth = started_on.replace(year=started_on.year + 5, day=28)
    return 6.0 if on_day >= fifth else 4.0
