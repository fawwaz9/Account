"""Typed application settings, read once at import from the environment and the `.env`.

`settings` is the instance the app imports. Real environment variables win over
`Application/.env`, which is how the containers are configured, and a missing
required value or a short `JWT_SECRET` stops the app at import.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Not a setting. Read from the environment this could be set to "none", which
#: PyJWT accepts as the unsigned algorithm -- every token would then verify.
JWT_ALGORITHM = "HS256"

# app/config.py -> app -> backend -> Application
APPLICATION_DIR = Path(__file__).resolve().parents[2]

#: The single .env for this project, resolved by path rather than by working
#: directory. `env_file=".env"` was relative to wherever the process started, so
#: it found backend/.env from backend/ and nothing at all from anywhere else --
#: which is why a second copy existed beside docker-compose.yml. The two held
#: the same secrets, byte-identical, with nothing keeping them that way; when
#: they drifted the symptom would have been tokens signed with one key and
#: verified with another, which reads to a person as being randomly signed out.
#:
#: One file, named absolutely. Real environment variables still win over it,
#: which is how the containers are configured -- they have no .env at all.
ENV_FILE = APPLICATION_DIR / ".env"


class Settings(BaseSettings):
    """Every setting the app reads through pydantic, validated when it is instantiated.

    Attributes:
        GOOGLE_CLIENT_ID: OAuth client id that Google ID tokens must be issued for;
            required.
        JWT_SECRET: HMAC key that signs session tokens; required, at least 32
            characters.
        JWT_EXPIRE_MINUTES: Session token lifetime in minutes; 7 days by default.
        VAPID_PRIVATE_KEY: Web Push signing key; unset turns push notifications off.
        VAPID_SUBJECT: Contact URL or `mailto:` address that push services see.
        CRON_SECRET: Shared secret for the scheduler endpoints, at least 32 characters;
            unset, they are unavailable.
        LLM_PROVIDER: Syllabus model provider: "openai", "gemini" or "anthropic"; unset
            turns syllabus reading off.
        LLM_MODEL_EXTRACT: The provider's model name used for syllabus extraction.
        LLM_API_KEY: The provider's API key.
        LLM_PARSES_PER_DAY: Syllabus parses allowed per person per day, 1-200.
        SYLLABUS_BUCKET: Private Cloud Storage bucket for uploaded syllabi; unset keeps
            the extraction but not the file.
        TRUSTED_PROXY_HOPS: Proxies counted in from the right of `X-Forwarded-For`, 0-3;
            0 ignores the header.

    Raises:
        pydantic.ValidationError: On instantiation, if a required value is missing or a
            value is out of range.
    """
    GOOGLE_CLIENT_ID: str
    #: Docker Compose substitutes an empty string for an unset variable, and an
    #: empty HMAC key signs tokens anyone can forge. Refuse to start instead.
    JWT_SECRET: str = Field(..., min_length=32)
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    #: Push notifications (Phase 0 item 5). All optional: without the keys the
    #: feature reports itself unavailable, and without CRON_SECRET the
    #: scheduler endpoint does not exist. See Ideas/overhaul/phase0-runbook.md.
    VAPID_PRIVATE_KEY: str | None = None
    #: The contact push services see. RFC 8292 allows a mailto: or an https:
    #: URL; the site's own address, so no personal email leaves the app unless
    #: one is configured deliberately.
    VAPID_SUBJECT: str = "https://account-2a7.pages.dev"
    CRON_SECRET: str | None = Field(default=None, min_length=32)

    #: Document intake (Phase 1 item 1, account-vision.md §13.21). All optional:
    #: without them syllabus reading reports itself unavailable. The provider is
    #: openai, gemini or anthropic; the model is that provider's model name.
    LLM_PROVIDER: str | None = None
    LLM_MODEL_EXTRACT: str | None = None
    LLM_API_KEY: str | None = None
    #: Parses per person per day: every call costs money, and a cap is what
    #: keeps a stuck retry loop from costing much of it.
    LLM_PARSES_PER_DAY: int = Field(default=10, ge=1, le=200)
    #: The private Cloud Storage bucket syllabi are kept in (Phase 1 D24).
    #: Unset, a syllabus is read and its extraction kept, but not the file.
    SYLLABUS_BUCKET: str | None = None

    #: How many proxies in front of the API append to X-Forwarded-For, counted
    #: from the right (Phase 2 item 12a). 0, the default, ignores the header and
    #: keys the rate limiters on the peer address -- which on Cloud Run is the
    #: platform's proxy, so every caller shares one budget. 1 trusts the entry
    #: Google's front end appends, the one a caller cannot write. Set only after
    #: a forged-header request shows the right address in the logs; setting it
    #: back to 0 is the rollback. See Ideas/overhaul/Phase 2/phase2-runbook.md.
    TRUSTED_PROXY_HOPS: int = Field(default=0, ge=0, le=3)

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


settings = Settings()
"""The process-wide settings, validated when this module is first imported."""
