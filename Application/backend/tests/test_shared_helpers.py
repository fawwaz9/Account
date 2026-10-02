"""The two helpers that used to exist thirteen times over.

`money` was copied into four services and `today` into nine, byte-identical
every time, and neither had a test anywhere -- which is how a one-line function
gets retyped slightly differently and nobody finds out.
"""
import math
import uuid
from datetime import date, datetime, timezone

from app._database.models import UserModel

from app.shared.dates import local_now, local_today, user_today, zone_of
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


#: An instant chosen so the answer differs by zone. 03:00 UTC on the 2nd is still
#: 21:00 on the 1st in Regina (UTC-6) and already 12:00 on the 2nd in Tokyo
#: (UTC+9). A test that used the real now could not tell a correct clock from the
#: server's, because both would agree most of the day.
FIXED_UTC = datetime(2026, 10, 2, 3, 0, tzinfo=timezone.utc)


def a_user(zone):
    """A detached row is enough: nothing here touches a session."""
    return UserModel(name="S", email="s@example.com", preferences={"timezone": zone})


class TestLocalToday:
    def test_is_the_students_day_not_the_servers(self):
        """The bug this replaced. `date.today()` on Cloud Run is UTC, so at this
        instant every figure anchored to "today" claimed the 2nd while the student
        was still living the 1st -- and free time skipped the day as already past.
        """
        assert local_today(a_user("America/Regina"), FIXED_UTC) == date(2026, 10, 1)
        assert FIXED_UTC.date() == date(2026, 10, 2), "the UTC answer, for contrast"

    def test_works_the_other_way_too(self):
        """A zone ahead of UTC, so the fix is not a constant six-hour shift."""
        assert local_today(a_user("Asia/Tokyo"), FIXED_UTC) == date(2026, 10, 2)
        assert local_today(a_user("Pacific/Kiritimati"), FIXED_UTC) == date(2026, 10, 2)

    def test_returns_a_date_rather_than_a_datetime(self):
        """Every caller compares it against a plain `due_date` or `occurred_on`,
        which are dates. A datetime would compare unequal to all of them."""
        assert type(local_today(a_user("America/Regina"), FIXED_UTC)) is date

    def test_an_unset_preference_falls_back_to_the_stored_default(self):
        user = UserModel(name="S", email="s@example.com", preferences=None)
        # UserPreferences' own default is America/Regina, so this is the 1st.
        assert local_today(user, FIXED_UTC) == date(2026, 10, 1)


class TestLocalNow:
    def test_is_naive_so_it_compares_with_stored_wall_times(self):
        """`remind_at` and the study window are naive local times. An aware value
        raises TypeError the moment it is compared with one."""
        assert local_now(a_user("America/Regina"), FIXED_UTC).tzinfo is None

    def test_carries_the_time_of_day_not_just_the_date(self):
        assert local_now(a_user("America/Regina"), FIXED_UTC) == datetime(2026, 10, 1, 21, 0)


class TestZoneFallback:
    def test_an_unreadable_stored_zone_falls_back_to_utc(self):
        """A zone is validated on the way in, so a bad one predates that. Falling
        back beats failing the whole page."""
        assert str(zone_of(a_user("Mars/Olympus_Mons"))) == "UTC"

    def test_no_user_at_all_falls_back_to_utc(self):
        assert str(zone_of(None)) == "UTC"


class TestUserToday:
    def test_resolves_through_the_stored_preference(self, db, user):
        """The form every service actually calls, holding an id rather than a row."""
        user.preferences = {"timezone": "America/Regina"}
        db.commit()

        assert user_today(db, user.id, FIXED_UTC) == date(2026, 10, 1)

    def test_an_unknown_user_does_not_raise(self, db):
        """Services call this before they have checked the id exists."""
        assert user_today(db, uuid.uuid4(), FIXED_UTC) == date(2026, 10, 2)
