from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from app.Grades.schemas.course import CourseDetail


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

    @model_validator(mode="after")
    def validate_user_logic(self):
        if self.name.strip() == "":
            raise ValueError("User name cannot be empty")
        if "@" not in self.email or self.email.strip() == "":
            raise ValueError("Invalid email address")
        return self


class UserCreate(UserBase):
    """Used for Google OAuth signup - the only supported path for now."""
    google_id: str = Field(..., min_length=1)
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    preferences: UserPreferences | None = None

    @model_validator(mode="after")
    def validate_user_update(self):
        if self.name is not None and self.name.strip() == "":
            raise ValueError("User name cannot be empty")
        if self.email is not None and ("@" not in self.email or self.email.strip() == ""):
            raise ValueError("Invalid email address")
        return self


class User(UserBase):
    id: UUID = Field(default_factory=uuid4)
    auth_provider: AuthProvider = AuthProvider.GOOGLE
    google_id: str | None = None
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