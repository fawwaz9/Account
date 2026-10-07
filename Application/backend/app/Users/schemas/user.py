import re
from datetime import date, datetime, time, timedelta
from enum import Enum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from app.Calendar.schemas.event import EventKind
from app.Grades.schemas.course import CourseDetail

# Each domain label excludes the dot, so a label and the separator that follows
# it can never match the same character. That makes the match linear; the
# earlier `[^@\s]+\.[^@\s]+` let the engine backtrack across every dot in a
# long non-matching address (SonarQube S8786).
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def normalize_email(value: str) -> str:
    """Trim, lower-case, and sanity-check an email address.

    Email is the login identifier for the local auth provider, so it is
    normalized on the way in. Lookups also use ILIKE, but storing a single
    canonical form keeps 'A@b.com' and 'a@b.com' from reading as two
    different accounts anywhere else in the app.
    """
    email = value.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError("Invalid email address")
    return email


class WeekStart(str, Enum):
    SUNDAY = "sunday"
    MONDAY = "monday"


class ThemePreference(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class DateFormat(str, Enum):
    MDY = "MM/DD/YYYY"
    DMY = "DD/MM/YYYY"
    ISO = "YYYY-MM-DD"


class TimeFormat(str, Enum):
    TWELVE_HOUR = "12h"
    TWENTY_FOUR_HOUR = "24h"


class AuthProvider(str, Enum):
    GOOGLE = "google"
    LOCAL = "local"


#: A colour as the browser's <input type="color"> produces it, and nothing else.
#: Short forms and names are refused rather than normalised: the value is put
#: straight into a CSS custom property, and the only shape every reader can rely
#: on is the one the picker emits.
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_event_colors(colors: dict[EventKind, str] | None) -> dict[EventKind, str] | None:
    """Every value a #rrggbb colour, lowercased; keys are already EventKinds.

    Shared by `UserPreferences` and `UserPreferencesPatch` so the two cannot
    drift. Both must run it: a bad colour written through the patch would be
    re-read through `UserPreferences` on every page, and fail there instead.
    """
    if colors is None:
        return None
    for kind, color in colors.items():
        if not isinstance(color, str) or not HEX_COLOR.match(color):
            raise ValueError(f"Colour for {kind.value} must be #rrggbb, got {color!r}")
    return {kind: color.lower() for kind, color in colors.items()}


class UserPreferences(BaseModel):
    timezone: str = Field(default="America/Regina", description="IANA timezone")
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    week_start: WeekStart = Field(default=WeekStart.SUNDAY)
    theme: ThemePreference = Field(default=ThemePreference.DARK)
    date_format: DateFormat = Field(default=DateFormat.ISO)
    time_format: TimeFormat = Field(default=TimeFormat.TWENTY_FOUR_HOUR)
    default_reminder_minutes_before: int = Field(default=30, ge=0, le=10080)
    #: Total credits the degree requires, for the credits progress bar.
    credit_target: int = Field(default=120, ge=1, le=400)
    #: UBC does not publish a GPA on transcripts, so this is opt-out.
    gpa_scale_enabled: bool = Field(default=True)
    #: Used for any course without its own target.
    default_target_grade: float = Field(default=85.0, ge=0, le=100)
    #: The hours a free block is worth offering. 03:00 is technically free and
    #: is not study time, so the gaps between classes are only counted inside
    #: this window.
    study_day_start: time = Field(default=time(8, 0))
    study_day_end: time = Field(default=time(22, 0))
    #: Below this a gap is not a block: twenty minutes between two lectures is
    #: walking time, not an hour of work.
    min_free_block_minutes: int = Field(default=30, ge=5, le=240)
    #: The student's own colour per event kind. Only the kinds they changed: a
    #: missing kind means its default, so resetting one is removing its key and
    #: no stale copy of a default is ever stored. Recolouring only -- kinds
    #: themselves stay a fixed enum because each carries behaviour.
    event_colors: dict[EventKind, str] = Field(default_factory=dict)
    #: The one account cash tips are filed into. None means tips are held out
    #: of the budget until one is chosen. Read here, but NOT on
    #: UserPreferencesPatch: choosing it files every held tip, and that side
    #: effect and its ownership check live in one call
    #: (PUT /jobs/{user_id}/cash-tip-account), not in a generic settings save.
    cash_tip_account_id: UUID | None = None
    #: Phase 1 D36: scale the workload forecast's estimates by how long tasks
    #: really take. Off until asked for; estimates themselves never change.
    use_estimate_ratio: bool = False
    #: Phase 2 item 14: a shift ending less than this many hours before an
    #: exam is flagged as crowding it. 0 flags only real overlaps.
    exam_buffer_hours: int = Field(default=12, ge=0, le=48)

    @field_validator("event_colors")
    @classmethod
    def validate_event_colors(cls, v: dict[EventKind, str]) -> dict[EventKind, str]:
        return validate_event_colors(v)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {v}") from exc
        return v


class UserPreferencesPatch(BaseModel):
    """The same preferences, for *changing* some of them.

    Deliberately a separate model rather than a subclass either way round,
    because this one and `UserPreferences` have opposite jobs. `UserPreferences`
    fills every default in, so a reader never meets a missing key.
    This one leaves an unmentioned field unset, so a writer never touches a
    preference the caller did not name.

    **One model cannot do both, and the attempt was a live bug.** `UserUpdate`
    used to declare `preferences: UserPreferences`, so a patch naming six fields
    was parsed into a complete fourteen-field model and `model_dump` emitted all
    fourteen -- which the merge in `update_user` then wrote over the top of what
    was stored. Every save in Settings reset `timezone` to `America/Regina`,
    silently, and `timezone` decides when reminders fire and whether a task
    counts as finished early or late. The merge was already written to avoid
    exactly this and could not, because what reached it was never partial.

    So the bounds and the validators are duplicated here on purpose. Dropping a
    validator would be worse than the bug it replaced: an invalid value would be
    stored, and `get_preferences` re-validates on *read* through
    `UserPreferences`, from six call sites that do not catch anything. A bad
    write would become a 500 on every page that reads a preference.
    """

    timezone: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    week_start: WeekStart | None = None
    theme: ThemePreference | None = None
    date_format: DateFormat | None = None
    time_format: TimeFormat | None = None
    default_reminder_minutes_before: int | None = Field(default=None, ge=0, le=10080)
    credit_target: int | None = Field(default=None, ge=1, le=400)
    gpa_scale_enabled: bool | None = None
    default_target_grade: float | None = Field(default=None, ge=0, le=100)
    study_day_start: time | None = None
    study_day_end: time | None = None
    min_free_block_minutes: int | None = Field(default=None, ge=5, le=240)
    #: Replaces the whole map when sent -- Settings always sends all of it.
    event_colors: dict[EventKind, str] | None = None
    use_estimate_ratio: bool | None = None
    exam_buffer_hours: int | None = Field(default=None, ge=0, le=48)

    # Both validators pass `None` straight through. An explicit null means "no
    # opinion" here, and running the check on it would reject the one value that
    # is always allowed.
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("event_colors")
    @classmethod
    def validate_event_colors(cls, v: dict[EventKind, str] | None) -> dict[EventKind, str] | None:
        return validate_event_colors(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {v}") from exc
        return v


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @model_validator(mode="after")
    def validate_user_logic(self):
        if self.name.strip() == "":
            raise ValueError("User name cannot be empty")
        return self


class UserCreate(UserBase):
    """Google OAuth signup.

    Local email + password signup goes through
    ``app.Auth.schemas.credentials.RegisterRequest`` instead, which carries a
    password rather than a google_id.
    """
    google_id: str = Field(..., min_length=1)
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    #: A patch, not a whole object -- see `UserPreferencesPatch`. Typing this as
    #: `UserPreferences` is what made every Settings save reset the preferences
    #: it did not mention.
    preferences: UserPreferencesPatch | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return None if value is None else normalize_email(value)

    @model_validator(mode="after")
    def validate_user_update(self):
        if self.name is not None and self.name.strip() == "":
            raise ValueError("User name cannot be empty")
        return self


#: How long a deleted account can still be brought back.
#:
#: Thirty days because the thing being protected is a whole academic record,
#: and the mistake being protected against -- a misclick, or a stolen session --
#: is usually noticed within a month.
#:
#: Lives here rather than in the service so the schema can derive `deletes_on`
#: without importing the service back.
DELETION_GRACE_DAYS = 30


class User(UserBase):
    id: UUID = Field(default_factory=uuid4)
    # How the account was originally created. Ask has_password / has_google
    # for what it can actually sign in with today.
    auth_provider: AuthProvider = AuthProvider.GOOGLE
    google_id: str | None = None
    email_verified: bool = False
    has_password: bool = False
    has_google: bool = False
    # Which term the student is in. Null until they set it, in which case every
    # course reads as current rather than the page showing nothing.
    current_school_year: int | None = None
    current_semester: str | None = None
    term_label: str | None = None
    #: The calendar year first year began, which is what gives every term real
    #: dates. Null means terms have none and anything measuring one says so.
    first_year_calendar_year: int | None = None
    #: What the anchor looks like from the courses that carry dates, so Settings
    #: can offer it rather than making the student work it out. Derived on read,
    #: never stored -- and deliberately not taken from `term_label`, which is
    #: free text nothing keeps current.
    suggested_first_year: int | None = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    created_at: datetime | None = None

    #: Set once deletion has been *requested*. The account still works while it
    #: is set -- this is what the client reads to offer undoing it.
    deleted_at: datetime | None = None
    #: The day it stops being recoverable. Derived, so the client never has to
    #: know what the grace period is.
    deletes_on: date | None = None

    @model_validator(mode="after")
    def derive_deletes_on(self):
        """Always computed from `deleted_at`, never trusted from input."""
        self.deletes_on = (
            None if self.deleted_at is None
            else (self.deleted_at + timedelta(days=DELETION_GRACE_DAYS)).date()
        )
        return self

    @model_validator(mode="after")
    def validate_auth_consistency(self):
        if self.auth_provider == AuthProvider.GOOGLE and not self.google_id:
            raise ValueError("google_id is required for Google-authenticated users")
        return self

    class Config:
        from_attributes = True


class UserDetail(User):
    courses: list[CourseDetail] = Field(default_factory=list)

    class Config:
        from_attributes = True