"""The user's own "now" and "today", from the time zone in their Settings.

Every date anchored to today goes through here, never `date.today()`, which is UTC on
Cloud Run and a day ahead of a student in the Americas every evening. Each function
takes an optional `at` so a test can fix the instant; the `user_*` helpers look the
user up by id, so resolve the day once per request rather than once per row.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app._database.models import UserModel
from app.Users.schemas.user import UserPreferences

#: Where an unreadable or missing zone lands. UTC rather than the preference
#: default, because this is the "we do not know" case and UTC is the one zone
#: that is never a wrong guess about where somebody is -- it is an admission.
FALLBACK_ZONE = ZoneInfo("UTC")


def zone_of(user: UserModel | None) -> ZoneInfo:
    """Return a user's time zone from their preferences, or UTC when it is unknown.

    Args:
        user: The user row; None falls back to UTC.

    Returns:
        The zone named in `preferences.timezone`; UTC if the user is None or the stored
        zone cannot be read.
    """
    if user is None:
        return FALLBACK_ZONE
    try:
        return ZoneInfo(UserPreferences(**(user.preferences or {})).timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return FALLBACK_ZONE


def local_now(user: UserModel | None, at: datetime | None = None) -> datetime:
    """Return the current moment on the user's own clock, as a naive datetime.

    Args:
        user: The user row; None uses UTC.
        at: Timezone-aware instant to convert instead of now, for tests. A naive value
            is read as the server's local time.

    Returns:
        Local wall time with `tzinfo` removed, comparable with naive local columns such
        as `reminders.remind_at`.
    """
    moment = at or datetime.now(timezone.utc)
    return moment.astimezone(zone_of(user)).replace(tzinfo=None)


def local_today(user: UserModel | None, at: datetime | None = None) -> date:
    """Return the calendar date where the user is.

    Args:
        user: The user row; None uses UTC.
        at: Timezone-aware instant to use instead of now, for tests.

    Returns:
        The user's local date.
    """
    return local_now(user, at).date()


def local_day_in_utc(user: UserModel | None, day: date) -> tuple[datetime, datetime]:
    """Return when one of the user's local days starts and ends, in naive UTC.

    For counting rows stamped in UTC (with `utc_now`) by the user's own day, which
    comparing `date(created_at)` with a local date gets wrong every evening west of
    Greenwich.

    Args:
        user: The user row; None uses UTC.
        day: The user's local calendar date.

    Returns:
        (start, end) as naive UTC datetimes: local midnight of `day` and of the next
        day, so the range is half-open.
    """
    zone = zone_of(user)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


# --------------------------------------------------------------------------
# For services that hold a `user_id` rather than the row. One primary-key
# lookup; never call these inside a loop over rows -- resolve the day once at
# the top of the function and pass it down, which is the shape every service
# here already has in its `on_day` argument.
# --------------------------------------------------------------------------

def user_for(db: Session, user_id: uuid.UUID) -> UserModel | None:
    """Return the user row for an id, or None if there is none.

    Args:
        db: Open database session.
        user_id: The user to load.

    Returns:
        The `UserModel`, or None.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def user_zone(db: Session, user_id: uuid.UUID) -> ZoneInfo:
    """Return a user's time zone by id; UTC when the user or the zone is unknown.

    Args:
        db: Open database session.
        user_id: The user.

    Returns:
        The user's zone.
    """
    return zone_of(user_for(db, user_id))


def user_now(db: Session, user_id: uuid.UUID, at: datetime | None = None) -> datetime:
    """Return the current moment on a user's own clock, by id, as a naive datetime.

    Args:
        db: Open database session.
        user_id: The user.
        at: Timezone-aware instant to use instead of now, for tests.

    Returns:
        The user's local wall time with `tzinfo` removed.
    """
    return local_now(user_for(db, user_id), at)


def user_today(db: Session, user_id: uuid.UUID, at: datetime | None = None) -> date:
    """Return today's date in a user's own time zone, by id.

    Args:
        db: Open database session.
        user_id: The user.
        at: Timezone-aware instant to use instead of now, for tests.

    Returns:
        The user's local date.
    """
    return local_today(user_for(db, user_id), at)
