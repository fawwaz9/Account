import re
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

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
    preferences: UserPreferences | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return None if value is None else normalize_email(value)

    @model_validator(mode="after")
    def validate_user_update(self):
        if self.name is not None and self.name.strip() == "":
            raise ValueError("User name cannot be empty")
        return self


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
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    created_at: datetime | None = None

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