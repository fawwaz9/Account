"""Schemas for Web Push: subscriptions, test sends and the scheduler's dispatch."""

from pydantic import BaseModel, Field, field_validator


class SubscriptionKeys(BaseModel):
    """A browser subscription's encryption keys, base64url-encoded as sent.

    Attributes:
        p256dh: The browser's P-256 public key, 40-200 characters; must decode to a
            point on the curve.
        auth: The browser's authentication secret, 10-100 characters.
    """
    p256dh: str = Field(..., min_length=40, max_length=200)
    auth: str = Field(..., min_length=10, max_length=100)

    @field_validator("p256dh")
    @classmethod
    def a_real_key(cls, value: str) -> str:
        """Require `p256dh` to decode to a valid P-256 public key.

        Args:
            value: The browser's `p256dh` key, base64url.

        Returns:
            The key, unchanged.

        Raises:
            ValueError: If it does not, since nothing could ever be encrypted to it (a
                422).
        """
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
    """Request body subscribing a browser, as `PushSubscription.toJSON()` produces it.

    Attributes:
        endpoint: The push service's URL for this browser, https only, at most 1000
            characters.
        keys: The browser's encryption keys.
    """

    endpoint: str = Field(..., max_length=1000)
    keys: SubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def https_only(cls, value: str) -> str:
        """Require an https:// endpoint, since the server will POST to it.

        Args:
            value: The push service endpoint URL.

        Returns:
            The endpoint, unchanged.

        Raises:
            ValueError: If the endpoint is not https (a 422).
        """
        # Every push service is HTTPS, and the server is about to POST to this
        # address: anything else is a request to somewhere it should not go.
        if not value.startswith("https://"):
            raise ValueError("A push endpoint is an https:// address")
        return value


class SubscriptionRemove(BaseModel):
    """Request body unsubscribing a browser.

    Attributes:
        endpoint: The browser's push endpoint, at most 1000 characters.
    """
    endpoint: str = Field(..., max_length=1000)


class TestRequest(BaseModel):
    """Request body for a test notification.

    Attributes:
        endpoint: The device asking, which alone receives the test; None sends to every
            device on the account.
    """
    #: The device asking for the test. It goes there alone, not to every device.
    endpoint: str | None = Field(default=None, max_length=1000)


class PushStatus(BaseModel):
    """Whether push works on this server, and for how many of the caller's devices.

    Attributes:
        available: Whether the server has its VAPID key and can send at all.
        public_key: The VAPID public key a browser subscribes with; None when
            unavailable.
        devices: How many browsers this account has turned notifications on for.
    """
    #: Whether this server can send at all -- it needs its VAPID key.
    available: bool
    public_key: str | None
    #: How many devices this account has turned notifications on for.
    devices: int


class TestResult(BaseModel):
    """The outcome of a test notification.

    Attributes:
        sent: Devices it was delivered to.
    """
    sent: int


class DispatchResult(BaseModel):
    """What one scheduler run of due reminders did.

    Attributes:
        users: Users with something due who were processed.
        pushed: Notifications delivered.
        removed: Subscriptions deleted because the push service said they are gone.
    """
    users: int
    pushed: int
    removed: int
