"""Work out investment returns from monthly readings of a holding's market value.

A reading is the dollar amount a holding sits above (or below) its ledger
balance in one month. It is a level, not a flow: readings never sum, and the
latest one is the all-time gain. Pure functions, no session; `account_service`
uses them for the account card, the account page and net worth.
"""
from datetime import date


#: A reading, as this module takes them: the month it was taken for, and the
#: dollar amount the holding sat above (positive) or below (negative) the ledger.
Reading = tuple[date, float]


def latest_reading(
    readings: list[Reading], on_or_before: date | None = None
) -> Reading | None:
    """Return the newest reading taken in or before a given month.

    Args:
        readings: The account's readings as (month, difference) pairs, any order.
        on_or_before: Latest month to consider, as its first day; None considers
            every reading.

    Returns:
        The newest qualifying (month, difference) pair, or None when there is
        none. It never looks forward: a month before every reading gets None.

    Note:
        The latest reading is the whole gain to date, so never add readings up.
        The month comes back with the amount so a carried-forward figure can be
        shown with its date.
    """
    usable = [
        reading for reading in readings
        if on_or_before is None or reading[0] <= on_or_before
    ]
    if not usable:
        return None

    return max(usable, key=lambda reading: reading[0])


def return_percent(difference: float, ledger_balance: float) -> float | None:
    """Return a gain as a percentage of the ledger balance, to one decimal place.

    Args:
        difference: The latest reading: dollars above (positive) or below
            (negative) the ledger balance.
        ledger_balance: The account's ledger balance (what was put in), in dollars.

    Returns:
        `difference / ledger_balance * 100`, rounded to 1 dp; None when the balance
        is zero or negative, where the division would fail or flip the sign.
    """
    if ledger_balance <= 0:
        return None

    return round(difference / ledger_balance * 100, 1)


def month_gain(readings: list[Reading], month: date) -> float | None:
    """Return how far a holding moved during one month.

    Args:
        readings: The account's readings as (month, difference) pairs, any order.
        month: The month to measure, as its first day.

    Returns:
        The month's reading minus the nearest earlier reading, signed and rounded
        to cents. None when the month has no reading of its own or nothing earlier
        exists; None means unknown, never a flat month.
    """
    this_month = next((r for r in readings if r[0] == month), None)
    if this_month is None:
        return None

    earlier = [reading for reading in readings if reading[0] < month]
    if not earlier:
        return None

    previous = max(earlier, key=lambda reading: reading[0])
    return round(this_month[1] - previous[1], 2)
