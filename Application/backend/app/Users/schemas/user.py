"""Schemas for users: the account, its stored preferences and edits to either.

`UserPreferences` reads stored preferences with every default filled in;
`UserPreferencesPatch` carries only the preferences a save names, so a Settings save
never resets the others.
"""

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
    """Return an email address trimmed and lower-cased, after a basic shape check.

    Args:
        value: The address as entered.

    Returns:
        The normalised address.

    Raises:
        ValueError: If it does not look like `local@domain.tld`.
    """
    email = value.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError("Invalid email address")
    return email


class WeekStart(str, Enum):
    """The day a week starts on in the calendar."""
    SUNDAY = "sunday"
    MONDAY = "monday"


class ThemePreference(str, Enum):
    """The colour theme: light, dark, or follow the system."""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class DateFormat(str, Enum):
    """How dates are displayed."""
    MDY = "MM/DD/YYYY"
    DMY = "DD/MM/YYYY"
    ISO = "YYYY-MM-DD"


class TimeFormat(str, Enum):
    """Whether times are displayed on a 12- or 24-hour clock."""
    TWELVE_HOUR = "12h"
    TWENTY_FOUR_HOUR = "24h"


class AuthProvider(str, Enum):
    """How an account was first created: with Google, or locally with a password."""
    GOOGLE = "google"
    LOCAL = "local"


#: A colour as the browser's <input type="color"> produces it, and nothing else.
#: Short forms and names are refused rather than normalised: the value is put
#: straight into a CSS custom property, and the only shape every reader can rely
#: on is the one the picker emits.
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_event_colors(colors: dict[EventKind, str] | None) -> dict[EventKind, str] | None:
    """Return event colours lower-cased, after checking each is a `#rrggbb` colour.

    Shared by `UserPreferences` and `UserPreferencesPatch` so a colour accepted on write
    is always readable again.

    Args:
        colors: Event kind to colour; None passes through.

    Returns:
        The map with lower-cased colours, or None.

    Raises:
        ValueError: If any colour is not `#rrggbb`.
    """
    if colors is None:
        return None
    for kind, color in colors.items():
        if not isinstance(color, str) or not HEX_COLOR.match(color):
            raise ValueError(f"Colour for {kind.value} must be #rrggbb, got {color!r}")
    return {kind: color.lower() for kind, color in colors.items()}


class UserPreferences(BaseModel):
    """A user's preferences as stored, with a default for every field.

    Also the reader: `get_preferences` re-validates the stored JSON through it, so a bad
    stored value would fail every page that reads a preference.

    Attributes:
        timezone: IANA time zone name, such as "America/Regina"; decides the user's
            "today" and when reminders fire.
        currency: Three-letter ISO 4217 code, upper-cased; "CAD" by default.
        week_start: First day of the week.
        theme: Colour theme.
        date_format: How dates are shown.
        time_format: 12- or 24-hour clock.
        default_reminder_minutes_before: Default reminder lead time, 0-10080 minutes.
        credit_target: Credits the degree requires, 1-400.
        gpa_scale_enabled: Whether grade points and the CGPA are shown.
        default_target_grade: Target percentage for any course without its own, 0-100.
        study_day_start: Earliest local time a free block may start.
        study_day_end: Latest local time a free block may end.
        min_free_block_minutes: Shortest gap counted as a free block, 5-240 minutes.
        event_colors: The user's own colour per event kind, only for kinds they changed.
        cash_tip_account_id: Account cash tips are filed into; None holds them out of
            the budget. Set only through the cash-tip-account route, never a settings
            save.
        use_estimate_ratio: Scale the workload forecast by how long tasks really take.
        exam_buffer_hours: A shift ending less than this many hours before an exam is
            flagged, 0-48.
        share_merchant_categories: Whether the user's confident category per merchant
            is counted, with no name, toward the shared merchant map (Phase 3 item 4).
        exertion_goal: The weekly exertion points the user aims for; None for no goal
            (Phase 3 item 7). Set only through the goal route, so it can be cleared.
        leaderboard_opt_in: Whether the user's weekly points appear on their teams'
            boards and count toward listed teams' standing (Phase 3 item 8).
    """
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
    #: Phase 3 item 4 (D11): on unless switched off. Off takes the user's votes
    #: out at the next recount; reading the map is never gated by it.
    share_merchant_categories: bool = True
    #: Phase 3 item 7: advised, never imposed. Not on UserPreferencesPatch,
    #: where a null means "no opinion" and so could never clear it.
    exertion_goal: int | None = Field(default=None, ge=1, le=10000)
    #: Phase 3 item 8 (D13): off until chosen.
    leaderboard_opt_in: bool = False

    @field_validator("event_colors")
    @classmethod
    def validate_event_colors(cls, v: dict[EventKind, str]) -> dict[EventKind, str]:
        """Check and lower-case the event colours.

        Args:
            v: Colour by event kind, as "#rrggbb".

        Returns:
            The colours, lower-cased.

        Raises:
            ValueError: If a colour is not "#rrggbb" (a 422).
        """
        return validate_event_colors(v)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Require an alphabetic currency code and upper-case it.

        Args:
            v: The submitted currency code.

        Returns:
            The code upper-cased.

        Raises:
            ValueError: If the code contains anything but letters (a 422).
        """
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Require a time zone name the zoneinfo database knows.

        Args:
            v: An IANA zone name, such as "America/Vancouver".

        Returns:
            The name, unchanged.

        Raises:
            ValueError: If the zone is unknown (a 422).
        """
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {v}") from exc
        return v


class UserPreferencesPatch(BaseModel):
    """Request body for changing some preferences; unnamed fields are left as they are.

    A separate model from `UserPreferences` because that one fills in defaults, which
    would overwrite stored values on every save. The bounds and validators are repeated
    here so nothing invalid is stored; an explicit null means no change.

    Attributes:
        timezone: IANA time zone name, such as "America/Regina"; decides the user's
            "today" and when reminders fire.
        currency: Three-letter ISO 4217 code, upper-cased.
        week_start: First day of the week.
        theme: Colour theme.
        date_format: How dates are shown.
        time_format: 12- or 24-hour clock.
        default_reminder_minutes_before: Default reminder lead time, 0-10080 minutes.
        credit_target: Credits the degree requires, 1-400.
        gpa_scale_enabled: Whether grade points and the CGPA are shown.
        default_target_grade: Default target percentage, 0-100.
        study_day_start: Earliest local time a free block may start.
        study_day_end: Latest local time a free block may end.
        min_free_block_minutes: Shortest free block, 5-240 minutes.
        event_colors: The whole colour map; replaces the stored one when sent.
        use_estimate_ratio: Scale the workload forecast by real task durations.
        exam_buffer_hours: Hours before an exam a shift may not end within, 0-48.
        share_merchant_categories: Count the user's merchant categories toward the
            shared map.
        leaderboard_opt_in: Show the user's weekly points on their teams' boards.
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
    share_merchant_categories: bool | None = None
    leaderboard_opt_in: bool | None = None

    # Both validators pass `None` straight through. An explicit null means "no
    # opinion" here, and running the check on it would reject the one value that
    # is always allowed.
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str | None) -> str | None:
        """Upper-case an alphabetic currency code; None passes through.

        Args:
            v: The submitted currency code, or None.

        Returns:
            The code upper-cased, or None.

        Raises:
            ValueError: If the code contains anything but letters (a 422).
        """
        if v is None:
            return None
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("event_colors")
    @classmethod
    def validate_event_colors(cls, v: dict[EventKind, str] | None) -> dict[EventKind, str] | None:
        """Check and lower-case the event colours; None passes through.

        Args:
            v: Colour by event kind, as "#rrggbb", or None.

        Returns:
            The colours lower-cased, or None.

        Raises:
            ValueError: If a colour is not "#rrggbb" (a 422).
        """
        return validate_event_colors(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Require a known time zone name; None passes through.

        Args:
            v: An IANA zone name, or None.

        Returns:
            The name unchanged, or None.

        Raises:
            ValueError: If the zone is unknown (a 422).
        """
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {v}") from exc
        return v


class UserBase(BaseModel):
    """The name and email every user schema carries.

    Attributes:
        name: Display name, 1-100 characters, not blank.
        email: Address, 3-255 characters; normalised by `normalize_email`.
    """
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Normalise the email address.

        Args:
            value: The submitted email.

        Returns:
            The email trimmed and lower-cased.

        Raises:
            ValueError: If it is not a plausible address (a 422).
        """
        return normalize_email(value)

    @model_validator(mode="after")
    def validate_user_logic(self):
        """Reject a name that is only whitespace.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank (a 422).
        """
        if self.name.strip() == "":
            raise ValueError("User name cannot be empty")
        return self


class UserCreate(UserBase):
    """A new account from Google sign-in; password signup uses `RegisterRequest`.

    Attributes:
        google_id: Google's subject id for the person.
        preferences: Starting preferences; all defaults.
    """
    google_id: str = Field(..., min_length=1)
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class UserUpdate(BaseModel):
    """Request body for editing the signed-in user; omitted fields stay as they are.

    Attributes:
        name: New display name, 1-100 characters, not blank.
        email: New address, normalised; changing it is handled by `user_service`.
        preferences: The preferences to change, as a partial patch.
    """
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    #: A patch, not a whole object -- see `UserPreferencesPatch`. Typing this as
    #: `UserPreferences` is what made every Settings save reset the preferences
    #: it did not mention.
    preferences: UserPreferencesPatch | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        """Normalise a sent email address; None passes through.

        Args:
            value: The submitted email, or None.

        Returns:
            The email trimmed and lower-cased, or None.

        Raises:
            ValueError: If it is not a plausible address (a 422).
        """
        return None if value is None else normalize_email(value)

    @model_validator(mode="after")
    def validate_user_update(self):
        """Reject a sent name that is only whitespace.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank (a 422).
        """
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
    """A user as the API returns it; never carries the password hash.

    Attributes:
        id: The user's id.
        auth_provider: How the account was first created.
        google_id: Google subject id; None when not linked.
        email_verified: Whether an identity provider vouched for the address.
        has_password: Whether the account can sign in with a password.
        has_google: Whether the account can sign in with Google.
        current_school_year: The student's school year now; None until set, when every
            course reads as current.
        current_semester: The student's term now; None until set.
        term_label: Free-text label for the current term.
        first_year_calendar_year: First-year anchor; None leaves terms undated.
        suggested_first_year: Anchor inferred from dated courses, for Settings to offer;
            derived on read.
        preferences: The user's preferences, defaults filled in.
        created_at: When the account was made; None for older accounts.
        deleted_at: When deletion was requested; None for a live account.
        deletes_on: The day the account stops being recoverable; derived from
            `deleted_at`.
    """
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
        """Derive `deletes_on` from `deleted_at`, never trusting an input value.

        Returns:
            The validated model.
        """
        self.deletes_on = (
            None if self.deleted_at is None
            else (self.deleted_at + timedelta(days=DELETION_GRACE_DAYS)).date()
        )
        return self

    @model_validator(mode="after")
    def validate_auth_consistency(self):
        """Require a Google id on an account created with Google.

        Returns:
            The validated model.

        Raises:
            ValueError: If `auth_provider` is Google and `google_id` is missing.
        """
        if self.auth_provider == AuthProvider.GOOGLE and not self.google_id:
            raise ValueError("google_id is required for Google-authenticated users")
        return self

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True


class UserDetail(User):
    """A user with every course in full, for the user detail routes.

    Attributes:
        courses: The user's courses with their grades.
    """
    courses: list[CourseDetail] = Field(default_factory=list)

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True
