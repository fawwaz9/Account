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

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


settings = Settings()