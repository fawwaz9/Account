"""Request bodies for email-and-password auth: register, log in, set a password."""

from pydantic import BaseModel, Field, field_validator

from app.Auth.services.password_service import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH
from app.Users.schemas.user import normalize_email


def validate_password(value: str) -> str:
    """Return a password unchanged after checking its length limits.

    Args:
        value: The password as typed.

    Returns:
        The same password; it is never stripped.

    Raises:
        ValueError: If it has fewer than `MIN_PASSWORD_LENGTH` characters, more than
            `MAX_PASSWORD_BYTES` bytes in UTF-8 (bcrypt's limit), or only whitespace.
    """
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    if value.strip() == "":
        raise ValueError("Password cannot be blank")
    return value


class RegisterRequest(BaseModel):
    """Request body for creating an account with an email and a password.

    Attributes:
        name: Display name, 1-100 characters; stripped, not blank.
        email: Address, 3-255 characters; normalised and shape-checked.
        password: At least 8 characters and at most 72 bytes.
    """
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(
        ...,
        description=f"At least {MIN_PASSWORD_LENGTH} characters, at most {MAX_PASSWORD_BYTES} bytes",
    )

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        """Normalise and shape-check the email.

        Args:
            value: The submitted email.

        Returns:
            The email trimmed and lower-cased.

        Raises:
            ValueError: If it is not a plausible address (a 422).
        """
        return normalize_email(value)

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        """Strip the name and reject a blank one.

        Args:
            value: The submitted display name.

        Returns:
            The name with surrounding whitespace removed.

        Raises:
            ValueError: If the name is blank (a 422).
        """
        if value.strip() == "":
            raise ValueError("User name cannot be empty")
        return value.strip()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        """Apply the password length rules.

        Args:
            value: The submitted password.

        Returns:
            The password, unchanged.

        Raises:
            ValueError: If it breaks the length rules (a 422).
        """
        return validate_password(value)


class LoginRequest(BaseModel):
    """Request body for signing in with an email and a password.

    Attributes:
        email: Address, 3-255 characters; only trimmed and lower-cased, never
            shape-checked, so a malformed address fails like a wrong password.
        password: The password, checked against the stored hash.
    """
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(...)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        """Trim and lower-case the email without validating its shape.

        Args:
            value: The submitted email.

        Returns:
            The email trimmed and lower-cased.
        """
        # Deliberately lenient: login must not reveal, through a 422, whether
        # a given address is well-formed differently from how it was stored.
        return value.strip().lower()


class SetPasswordRequest(BaseModel):
    """Request body for adding a first password or changing the current one.

    Attributes:
        new_password: At least 8 characters and at most 72 bytes.
        current_password: The existing password; required only when the account
            already has one.
    """

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
        """Apply the password length rules.

        Args:
            value: The submitted new password.

        Returns:
            The password, unchanged.

        Raises:
            ValueError: If it breaks the length rules (a 422).
        """
        return validate_password(value)
