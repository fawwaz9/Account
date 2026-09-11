"""Reading and writing a repeat rule stored as columns.

Three tables now carry the same five columns -- events, recurring transactions
and recurring tasks -- because they all repeat and they all resolve through one
engine. The conversion between those columns, the engine's `Rule`, and the API's
`Recurrence` was written out twice before the third arrived; this is that
conversion, once.

Any model with `recur_freq`, `recur_interval`, `recur_byday`, `recur_until` and
`recur_count` can be passed here. Deliberately duck-typed rather than a mixin or
a shared base: the three models have nothing else in common, and a base class
would imply they do.
"""

from app.Calendar.schemas.event import Frequency, Recurrence, Weekday
from app.Calendar.utils.recurrence import Rule, format_byday, parse_byday


def rule_of(row) -> Rule:
    """The stored columns as the engine's rule."""
    return Rule(
        freq=row.recur_freq,
        interval=row.recur_interval or 1,
        byday=parse_byday(row.recur_byday),
        until=row.recur_until,
        count=row.recur_count,
    )


def recurrence_of(row) -> Recurrence | None:
    """The stored columns as the API's nested object, or None for a one-off."""
    if not row.recur_freq:
        return None

    return Recurrence(
        freq=Frequency(row.recur_freq),
        interval=row.recur_interval or 1,
        byday=[Weekday(code) for code in parse_byday(row.recur_byday)],
        until=row.recur_until,
        count=row.recur_count,
    )


def apply_recurrence(row, recurrence: Recurrence | None) -> None:
    """Write a recurrence onto the columns, or clear them back to a one-off."""
    if recurrence is None:
        row.recur_freq = None
        row.recur_interval = 1
        row.recur_byday = None
        row.recur_until = None
        row.recur_count = None
        return

    row.recur_freq = recurrence.freq.value
    row.recur_interval = recurrence.interval
    row.recur_byday = format_byday(day.value for day in recurrence.byday)
    row.recur_until = recurrence.until
    row.recur_count = recurrence.count
