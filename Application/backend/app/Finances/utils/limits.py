"""What an account is meant to spend, and where that figure comes from.

Pure: numbers in, a number out, no session. Here rather than in a service
because two services read the same rule -- the account page and the budget
summary -- and the design notes say a rule two callers share belongs in
`utils`. If they ever disagreed, one screen would report a different target
from the other for the same account and the same month.

Shaped on `effective_target` in `Grades/utils/terms.py`, which answers the same
question for a course's target grade: the specific value when there is one, the
standing default otherwise.
"""


def planned_for_account(
    category_limits: list[float],
    manual_target: float,
) -> tuple[float, bool]:
    """The account's target, and whether it was derived from its categories.

    An account that budgets by category is budgeted **by the sum of those
    categories** -- itemising the spending and then setting an unrelated total
    would be two answers to one question, and the one you edited last would
    quietly win.

    An account with no category limits keeps the target set by hand, which is
    the case that matters most: Savings and Money Lent carry real targets and
    would never be itemised by "Groceries". Deriving unconditionally would read
    those as budgeting nothing.

    **Emptiness, not falsiness, decides.** A single limit of 0 is a list of one,
    so the account derives a target of 0 -- "nothing is meant to leave here" --
    where `if sum(category_limits):` would fall through to the manual target and
    report a deliberately closed account as merely unbudgeted. The list being
    empty is the only thing that means "not budgeted by category".

    Returns the figure and the flag together so no caller can compute one
    without the other and describe a derived figure as a manual one.
    """
    if not category_limits:
        return manual_target, False

    return round(sum(category_limits), 2), True


def effective_category_limit(
    standing: float | None, override: float | None
) -> float | None:
    """This month's limit for one category: the month's own, else the standing one.

    **Tests for None, not for truthiness, and that is the whole function.** An
    override of `0` is a real instruction -- "nothing is meant to go here this
    month" -- under which any spending at all is over. A falsy check would read
    that as "no override", fall through to the standing figure, and report a
    month deliberately closed as merely budgeted as usual: the exact inversion
    of what was asked, on the month someone cared enough about to set to zero.

    None from both means no limit, which the client renders as a plain total
    rather than a bar against nothing.
    """
    if override is not None:
        return override
    return standing
