"""Resolve what an account is meant to spend, overall and per category.

Pure functions, no session. `budget_service` (the budget summary) and
`activity_service` (the account page) both call them, so the two screens report
the same target for the same account and month.
"""


def planned_for_account(
    category_limits: list[float],
    manual_target: float,
) -> tuple[float, bool]:
    """Return an account's planned spending and whether its categories set it.

    An account with any category limit is budgeted by their sum; one with none
    keeps its hand-set target.

    Args:
        category_limits: The month's effective limit for each category the account
            budgets, in dollars. Empty means it does not budget by category; a list
            holding only 0 means it plans to spend nothing.
        manual_target: The account's hand-set target for the month, in dollars.

    Returns:
        The sum of `category_limits` rounded to cents and True, or `manual_target`
        unchanged and False when the list is empty.

    Note:
        Emptiness, not a zero sum, selects the manual target: a single limit of 0
        is a real plan to spend nothing.
    """
    if not category_limits:
        return manual_target, False

    return round(sum(category_limits), 2), True


def effective_category_limit(
    standing: float | None, override: float | None
) -> float | None:
    """Return one category's limit for a month: its override, else the standing limit.

    Args:
        standing: The standing monthly limit for the (account, category) pair, in
            dollars; None when there is none.
        override: That month's override, in dollars; None when the month has none.

    Returns:
        The override when present (0 included), otherwise `standing`; None when
        neither exists, which means no limit.

    Note:
        Tests for None, never truthiness: an override of 0 means nothing should be
        spent in that category that month.
    """
    if override is not None:
        return override
    return standing
