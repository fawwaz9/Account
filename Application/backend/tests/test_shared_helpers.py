"""The two helpers that used to exist thirteen times over.

`money` was copied into four services and `today` into nine, byte-identical
every time, and neither had a test anywhere -- which is how a one-line function
gets retyped slightly differently and nobody finds out.
"""
import math
from datetime import date

from app.shared.dates import today
from app.shared.money import money


class TestMoney:
    def test_rounds_to_cents(self):
        assert money(11.825) == 11.82
        assert money(1.005) == 1.0
        assert money(12.344) == 12.34
        assert money(-12.344) == -12.34

    def test_leaves_a_whole_number_alone(self):
        assert money(5) == 5.0
        assert money(0) == 0.0

    def test_a_split_still_sums_to_its_whole(self):
        """The reason this rounds at all: parts that do not add up to the
        amount that actually arrived are a cent invented or lost."""
        whole = 146.79
        parts = [money(whole * share) for share in (0.5, 0.2, 0.2)]
        remainder = money(whole - sum(parts))

        assert money(sum(parts) + remainder) == whole

    def test_normalises_an_input_that_is_already_negative_zero(self):
        """`-0.0` is a real float that prints as `-0.00`, so a balance of
        nothing would read as a negative amount. This is what the `+ 0.0` in
        `money` is for, and the only thing it is for."""
        assert math.copysign(1, money(-0.0)) == 1.0
        assert math.copysign(1, round(-0.0, 2)) == -1.0  # what it would be without

    def test_does_not_catch_a_small_negative_that_rounds_away(self):
        """The limit of the above, pinned so it is a known gap rather than a
        surprise. The `+ 0.0` runs *before* the rounding, so a value that only
        becomes negative zero by being rounded keeps its sign.

        Moving the addition after the round would close this and would change
        no other value. That is a behaviour change rather than a move, so it is
        deliberately not bundled with the consolidation that created this file.
        """
        assert math.copysign(1, money(-0.004)) == -1.0


class TestToday:
    def test_is_the_current_date(self):
        assert today() == date.today()

    def test_returns_a_date_rather_than_a_datetime(self):
        """Every caller compares it against a plain `due_date` or `occurred_on`,
        which are dates. A datetime would compare unequal to all of them."""
        assert type(today()) is date
