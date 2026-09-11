from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Not a setting. Read from the environment this could be set to "none", which
#: PyJWT accepts as the unsigned algorithm -- every token would then verify.
JWT_ALGORITHM = "HS256"


class Settings(BaseSettings):
    GOOGLE_CLIENT_ID: str
    #: Docker Compose substitutes an empty string for an unset variable, and an
    #: empty HMAC key signs tokens anyone can forge. Refuse to start instead.
    JWT_SECRET: str = Field(..., min_length=32)
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()