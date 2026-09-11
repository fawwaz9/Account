"""Request bodies for the local email + password auth routes."""

from pydantic import BaseModel, Field, field_validator

from app.Auth.services.password_service import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH
from app.Users.schemas.user import normalize_email


def validate_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    if value.strip() == "":
        raise ValueError("Password cannot be blank")
    return value


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(
        ...,
        description=f"At least {MIN_PASSWORD_LENGTH} characters, at most {MAX_PASSWORD_BYTES} bytes",
    )

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("User name cannot be empty")
        return value.strip()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password(value)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(...)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        # Deliberately lenient: login must not reveal, through a 422, whether
        # a given address is well-formed differently from how it was stored.
        return value.strip().lower()


class SetPasswordRequest(BaseModel):
    """Add a first password, or change an existing one, while signed in."""

    new_password: str = Field(
        ...,
        description=f"At least {MIN_PASSWORD_LENGTH} characters, at most {MAX_PASSWORD_BYTES} bytes",
    )
    current_password: str | None = Field(
        default=None,
        description="Required only when the account already has a password",
    )

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, value: str) -> str:
        return validate_password(value)
