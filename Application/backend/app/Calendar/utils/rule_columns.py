"""Map repeat-rule columns to the engine's `Rule` and the API's `Recurrence`.

Events, standing payments, repeating tasks and jobs (their pay rule) all store a
repeat in the same columns: `recur_freq`, `recur_interval`, `recur_byday`,
`recur_until` and `recur_count`. The functions here are duck-typed and accept
any row carrying them; the models share no base class.
"""

from app.Calendar.schemas.event import Frequency, Recurrence, Weekday
from app.Calendar.utils.recurrence import Rule, format_byday, parse_byday


def rule_of(row) -> Rule:
    """Read a row's repeat columns as the engine's rule.

    Args:
        row: Any model row with the five `recur_*` columns.

    Returns:
        A `Rule`; an interval of 0 or None becomes 1, and unknown weekday codes are
        dropped.
    """
    return Rule(
        freq=row.recur_freq,
        interval=row.recur_interval or 1,
        byday=parse_byday(row.recur_byday),
        until=row.recur_until,
        count=row.recur_count,
    )


def recurrence_of(row) -> Recurrence | None:
    """Read a row's repeat columns as the API's nested `Recurrence`.

    Args:
        row: Any model row with the five `recur_*` columns.

    Returns:
        The repeat for a response body, or None when `recur_freq` is empty (a
        one-off).

    Raises:
        ValueError: If the columns do not form a valid `Recurrence`, such as an
            unknown `recur_freq` (pydantic's ValidationError is a ValueError).
    """
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
    """Write a repeat onto a row's columns, or reset them to a one-off.

    Only sets attributes on the row; the caller flushes or commits.

    Args:
        row: Any model row with the five `recur_*` columns.
        recurrence: The validated repeat to store; None clears the rule (interval
            back to 1, everything else to None).
    """
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
