"""Rounding money, in one place.

This existed four times over -- in `subscription_service`, `sinking_service`,
`safe_service` and `paycheque_service` -- byte-identical every time, and a fifth
service imported one of those copies from another service rather than write a
sixth, which is how a layering rule quietly becomes a suggestion.

The project's own rule says a rule two modules share belongs somewhere both can
read, and this is that somewhere: `app/shared/` already holds the tokenizer, the
audit log and the error bodies.
"""


def money(value: float) -> float:
    """Round to cents, so a sum of parts can equal the whole it came from.

    **The `+ 0.0` is deliberate, and narrower than it looks.** It normalises an
    input that is *already* negative zero -- `-0.0 + 0.0` is `0.0` -- which is
    what a sum of nothing, or a multiplication by zero, can leave behind.
    Without it `round(-0.0, 2)` stays `-0.0`, and a balance of nothing reads as
    `-0.00` on screen.

    It sits before the rounding rather than after, so it does **not** catch a
    small negative that rounds *away* to nothing: `money(-0.004)` is still
    `-0.0`. Moving it after the round would close that too, and would change no
    other value, but it is a behaviour change rather than a move and is left
    for its own commit. Measured, not assumed -- there is a test for both.
    """
    return round(value + 0.0, 2)
