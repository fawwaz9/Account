"""What "today" is, in one place -- on the student's clock, not the server's.

Nine services defined this identically -- across Tasks, Finances and Jobs -- and
nine copies of a one-line function are nine chances for one of them to start
meaning something slightly different: a timezone, a test seam, a clock injected
for one module and not the rest.

**It used to be `date.today()`, and on Cloud Run that is UTC.** The container sets
no `TZ`, so `datetime.now()` and `utcnow()` return the same instant. Every figure
anchored to "today" was therefore anchored to a day that, for a student in
`America/Regina`, begins six hours early and rolls over at six in the evening.
Free time was the visible symptom: after 18:00 local, UTC was already tomorrow, so
the day the client had asked about was in the past and was skipped entirely --
no free time for the rest of every evening. The study window's *hours* came from
the student's preferences all along, which is what made it read as inconsistent
rather than simply wrong.

So the naive `today()` is gone rather than deprecated. Leaving it would leave the
mistake one import away, and the failure is silent: the wrong answer is a
plausible date, off by a day only some of the time.

Everything here resolves through `preferences.timezone`, which the student sets in
Settings. `at` exists on each function so a test can fix the instant: without it a
test can only express times relative to the same function it is checking, which
makes it agree with any clock the function chooses -- including a wrong one.
"""

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app._database.models import UserModel
from app.Users.schemas.user import UserPreferences

#: Where an unreadable or missing zone lands. UTC rather than the preference
#: default, because this is the "we do not know" case and UTC is the one zone
#: that is never a wrong guess about where somebody is -- it is an admission.
FALLBACK_ZONE = ZoneInfo("UTC")


def zone_of(user: UserModel | None) -> ZoneInfo:
    """The student's own time zone, falling back to UTC if it is unreadable.

    A stored zone is validated on the way in, so a bad one here means the row
    predates that validation. Falling back beats failing the whole page.
    """
    if user is None:
        return FALLBACK_ZONE
    try:
        return ZoneInfo(UserPreferences(**(user.preferences or {})).timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return FALLBACK_ZONE


def local_now(user: UserModel | None, at: datetime | None = None) -> datetime:
    """Now, on the student's own clock, naive so it compares with stored wall times.

    Naive on purpose: `remind_at` and the study window are naive *local* wall
    times, and an aware value would refuse to compare with them.
    """
    moment = at or datetime.now(timezone.utc)
    return moment.astimezone(zone_of(user)).replace(tzinfo=None)


def local_today(user: UserModel | None, at: datetime | None = None) -> date:
    """The calendar day it is where the student is standing.

    This is the function that replaced `date.today()`. The difference is a whole
    day for part of every day, which is why it is worth a call rather than a
    constant.
    """
    return local_now(user, at).date()


# --------------------------------------------------------------------------
# For services that hold a `user_id` rather than the row. One primary-key
# lookup; never call these inside a loop over rows -- resolve the day once at
# the top of the function and pass it down, which is the shape every service
# here already has in its `on_day` argument.
# --------------------------------------------------------------------------

def user_for(db: Session, user_id: uuid.UUID) -> UserModel | None:
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def user_zone(db: Session, user_id: uuid.UUID) -> ZoneInfo:
    return zone_of(user_for(db, user_id))


def user_now(db: Session, user_id: uuid.UUID, at: datetime | None = None) -> datetime:
    return local_now(user_for(db, user_id), at)


def user_today(db: Session, user_id: uuid.UUID, at: datetime | None = None) -> date:
    """Today, for a service that was handed an id. The common case."""
    return local_today(user_for(db, user_id), at)
