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

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


settings = Settings()