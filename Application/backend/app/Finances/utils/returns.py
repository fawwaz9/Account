"""What an investment is actually worth, and what that makes the return.

An account's balance is the sum of its ledger -- what you put in. It says nothing
about what the holding is now worth, so an account that has doubled and one that
has halved read identically. The fix is to record, per month, the dollar amount
the holding sits **above or below** that plain value.

Pure: numbers in, a number out, no session. Here rather than in a service because
three screens read the same rule -- the account card, the account page's tile and
the net-worth headline -- and the design notes say a rule several callers share
belongs in `utils`. Shaped on `planned_for_account` in `limits.py`, which likewise
returns a figure together with the fact a caller needs to describe it honestly.

THE ONE THING TO GET RIGHT
--------------------------
What is recorded is a **level, not a flow**. "$500 above plain value" is a
snapshot of market minus cost, so **the readings do not sum**. All-time gain is
the *latest* reading, never the total of them. Three readings of +100, +200 and
+300 describe a holding that is +300 up, not +600, and summing them is the single
mistake that makes every figure on every screen wrong at once. `latest_reading`
exists so that no caller can express that mistake, and a test mutates it to `sum`
to prove the mistake would be caught.

WHY A LEVEL IS ENOUGH, which is why this is small
-------------------------------------------------
The difference is **contribution-neutral**. Put $1,000 in: plain value rises
$1,000 and market value rises $1,000, so the difference does not move. Gain $50:
market moves, plain does not, the difference moves $50. So the difference *is*
cumulative gain, with no time-weighting and no adjusting for deposits -- a
month's gain is just `difference(m) - difference(m-1)`.

It also rules out storing the market value and deriving the difference on read,
which looks friendlier and is broken. Record $10,543 on the 15th, deposit $1,000
on the 20th, and the month-end ledger is $11,000 -- so a derived difference reads
**-$457** and a gain is reported as a loss. The difference is stored because it is
the only figure that survives a later deposit.
"""
from datetime import date


#: A reading, as this module takes them: the month it was taken for, and the
#: dollar amount the holding sat above (positive) or below (negative) the ledger.
Reading = tuple[date, float]


def latest_reading(
    readings: list[Reading], on_or_before: date | None = None
) -> Reading | None:
    """The most recent reading, with the month it was taken for.

    **The latest, never the sum.** See the module docstring: these are levels, so
    the newest one already describes the whole gain to date. A caller that added
    them up would report a holding up $300 as up $600, and would get further from
    the truth with every month recorded.

    `on_or_before` is what makes a month with no reading of its own show the last
    one taken -- an investment you have not checked has not lost its value. It
    only ever looks **backwards**: viewing July when the only reading is from
    September returns None rather than September's, because a figure from the
    future is not a stale figure, it is a wrong one.

    Returns the month alongside the amount so that no caller can render the
    figure without being able to say when it was taken. That is the whole safety
    of carrying a reading forward: dated, it is honest; undated, a reading from
    March reads as today's.
    """
    usable = [
        reading for reading in readings
        if on_or_before is None or reading[0] <= on_or_before
    ]
    if not usable:
        return None

    return max(usable, key=lambda reading: reading[0])


def return_percent(difference: float, ledger_balance: float) -> float | None:
    """The gain as a percentage of what was put in, or None when that is meaningless.

    Measured against the ledger balance, which means it reads as *return on what
    you put in*. That has a property the alternatives do not: the reader can check
    it against the balance printed next to it. It also behaves correctly when you
    add money -- deposit $10,000 against a $500 gain and the percentage falls,
    because you now hold $20,500 on $20,000 of cost, and 2.5% is the truth.

    **None, not a number, when the balance is zero or negative.** Zero is a
    division by zero. A negative balance is worse than an error: dividing by it
    flips the sign, so a holding that had gained would render as a loss, which is
    the one failure nobody would think to check. Callers show the dollar figure
    and no percentage.

    Rounded here, server-side, following the rule recorded on `ProgressBar`: the
    server rounds and the client renders, because a client that recomputes the
    division gives a second opinion that disagrees at the boundary.
    """
    if ledger_balance <= 0:
        return None

    return round(difference / ledger_balance * 100, 1)


def month_gain(readings: list[Reading], month: date) -> float | None:
    """How much the holding moved during one month, or None if unknowable.

    `difference(month) - difference(the reading before it)`, which is all a
    month's gain is once the level is contribution-neutral -- no deposit
    adjustment, no time-weighting.

    **None in two cases, and neither of them is zero.** A month with no reading of
    its own is unknown, not flat: carrying a level forward keeps the all-time
    figure honest, but reporting the month's movement as `0` would assert that
    nothing happened, which nobody recorded. And the first reading ever taken has
    nothing to subtract from, so its month has no movement to report either --
    its level is the whole story and a caller shows that instead.
    """
    this_month = next((r for r in readings if r[0] == month), None)
    if this_month is None:
        return None

    earlier = [reading for reading in readings if reading[0] < month]
    if not earlier:
        return None

    previous = max(earlier, key=lambda reading: reading[0])
    return round(this_month[1] - previous[1], 2)
