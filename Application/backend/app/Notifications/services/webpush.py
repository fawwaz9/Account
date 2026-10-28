"""The Web Push protocol: RFC 8291 payload encryption and RFC 8292 VAPID signing.

Written out over `cryptography` and PyJWT rather than taken from a library;
`tests/test_webpush.py` reproduces RFC 8291's worked example byte for byte. Nothing
here knows about users or reminders: it encrypts one payload for one browser
subscription and signs the request that delivers it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: One record is enough: a notification is a few hundred bytes. RFC 8188
#: requires the record size to exceed the payload plus padding and tag.
RECORD_SIZE = 4096
#: How long the push service should hold a message for an offline device. A
#: reminder that arrives a day late is no longer a reminder.
TTL_SECONDS = 12 * 60 * 60


def b64url_decode(value: str) -> bytes:
    """Decode unpadded base64url text, as browsers and VAPID keys use it.

    Args:
        value: base64url text, with or without padding.

    Returns:
        The decoded bytes.
    """
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url_encode(value: bytes) -> str:
    """Encode bytes as base64url without padding.

    Args:
        value: Bytes to encode.

    Returns:
        Unpadded base64url text.
    """
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """Return HKDF-SHA256 output of up to 32 bytes (one block) for these inputs."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    """Return a P-256 public key as an uncompressed point."""
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(
    payload: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    salt: bytes | None = None,
    as_private: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """Encrypt a payload for one subscription as an RFC 8291 `aes128gcm` body.

    Args:
        payload: The message bytes; one 4096-byte record holds it.
        ua_public: The subscription's `p256dh` key, decoded.
        auth_secret: The subscription's `auth` secret, decoded.
        salt: 16 random bytes; generated fresh unless a test fixes it.
        as_private: The sender's ephemeral P-256 key; generated fresh unless a test
            fixes it.

    Returns:
        The header (salt, record size, sender key) followed by the ciphertext.
    """
    salt = salt if salt is not None else os.urandom(16)
    as_private = as_private if as_private is not None else ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(as_private.public_key())

    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = as_private.exchange(ec.ECDH(), ua_key)

    key_info = b"WebPush: info\x00" + ua_public + as_public
    ikm = _hkdf(auth_secret, ecdh_secret, key_info, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    # One record, so it is also the last: the 0x02 delimiter, no padding.
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!L", RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext


@dataclass(frozen=True)
class Vapid:
    """The server's identity to push services: an ES256 key pair and a contact.

    Attributes:
        private_key: The VAPID P-256 private key.
        subject: The contact URL or `mailto:` push services see.
    """

    private_key: ec.EllipticCurvePrivateKey
    subject: str

    @classmethod
    def from_settings(cls, private_key_b64: str, subject: str) -> "Vapid":
        """Return the identity from a base64url private scalar and a contact.

        Args:
            private_key_b64: The raw 32-byte private scalar, base64url; surrounding
                whitespace is ignored.
            subject: The contact URL or `mailto:` address.

        Returns:
            The VAPID identity.
        """
        scalar = int.from_bytes(b64url_decode(private_key_b64.strip()), "big")
        return cls(ec.derive_private_key(scalar, ec.SECP256R1()), subject)

    @property
    def public_key(self) -> str:
        """The public key browsers subscribe with, as a base64url uncompressed point."""
        return b64url_encode(_public_bytes(self.private_key.public_key()))

    def authorization(self, endpoint: str, now: float | None = None) -> str:
        """Return the RFC 8292 `Authorization` header for a request to an endpoint.

        Args:
            endpoint: The push endpoint; its origin is the token's audience.
            now: Unix time to sign at, for tests; defaults to now.

        Returns:
            "vapid t=<JWT>, k=<public key>", with the JWT valid for 12 hours.
        """
        parts = urlsplit(endpoint)
        issued = int(now if now is not None else time.time())
        token = jwt.encode(
            {"aud": f"{parts.scheme}://{parts.netloc}", "exp": issued + 12 * 60 * 60, "sub": self.subject},
            self.private_key,
            algorithm="ES256",
        )
        return f"vapid t={token}, k={self.public_key}"


def generate_keys() -> tuple[str, str]:
    """Return a new VAPID key pair as (private, public) base64url, for the runbook.

    Returns:
        (private key, public key), both unpadded base64url.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    private = b64url_encode(key.private_numbers().private_value.to_bytes(32, "big"))
    return private, b64url_encode(_public_bytes(key.public_key()))


def request_for(endpoint: str, p256dh: str, auth: str, payload: bytes, vapid: Vapid) -> tuple[dict, bytes]:
    """Return the headers and encrypted body that deliver a payload to one subscription.

    Args:
        endpoint: The subscription's push endpoint.
        p256dh: Its public key, base64url.
        auth: Its auth secret, base64url.
        payload: The message bytes.
        vapid: The server's identity.

    Returns:
        (headers, body), with a `TTL_SECONDS` time to live.
    """
    body = encrypt(payload, b64url_decode(p256dh), b64url_decode(auth))
    headers = {
        "Authorization": vapid.authorization(endpoint),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        "Urgency": "normal",
    }
    return headers, body
