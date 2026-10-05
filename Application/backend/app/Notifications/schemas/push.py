from pydantic import BaseModel, Field, field_validator


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(..., min_length=40, max_length=200)
    auth: str = Field(..., min_length=10, max_length=100)

    @field_validator("p256dh")
    @classmethod
    def a_real_key(cls, value: str) -> str:
        # Checked here, once, rather than discovered by the scheduler: a key
        # that is not a point on P-256 can never be encrypted to.
        from cryptography.hazmat.primitives.asymmetric import ec

        from app.Notifications.services.webpush import b64url_decode
        try:
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64url_decode(value))
        except (ValueError, TypeError) as exc:
            raise ValueError("Not a valid browser push key") from exc
        return value


class SubscriptionCreate(BaseModel):
    """What the browser's PushSubscription.toJSON() returns, as sent."""

    endpoint: str = Field(..., max_length=1000)
    keys: SubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def https_only(cls, value: str) -> str:
        # Every push service is HTTPS, and the server is about to POST to this
        # address: anything else is a request to somewhere it should not go.
        if not value.startswith("https://"):
            raise ValueError("A push endpoint is an https:// address")
        return value


class SubscriptionRemove(BaseModel):
    endpoint: str = Field(..., max_length=1000)


class TestRequest(BaseModel):
    #: The device asking for the test. It goes there alone, not to every device.
    endpoint: str | None = Field(default=None, max_length=1000)


class PushStatus(BaseModel):
    #: Whether this server can send at all -- it needs its VAPID key.
    available: bool
    public_key: str | None
    #: How many devices this account has turned notifications on for.
    devices: int


class TestResult(BaseModel):
    sent: int


class DispatchResult(BaseModel):
    users: int
    pushed: int
    removed: int
