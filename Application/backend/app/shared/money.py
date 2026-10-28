"""Rounding money to cents, the one shared `money()`; do not write a local copy."""


def money(value: float) -> float:
    """Round a dollar amount to cents, turning an input of negative zero into zero.

    Args:
        value: Dollars, of any sign.

    Returns:
        `value` rounded to two decimals.

    Note:
        The `+ 0.0` runs before the rounding, so `-0.0` becomes `0.0` but a small
        negative that rounds away (`money(-0.004)`) stays `-0.0`; a test pins both.
    """
    return round(value + 0.0, 2)
