"""The Web Push protocol, written out: RFC 8291 encryption and RFC 8292 VAPID.

Phase 0 item 5 (Ideas/overhaul/phase0.md). Written here rather than taken from
pywebpush, which would bring aiohttp and its dependency tree into an app that
needs one HTTP POST. The protocol is two short standards over primitives the
app already has -- ``cryptography`` for P-256 and AES-GCM, PyJWT for the ES256
signature -- and RFC 8291 publishes a complete worked example with fixed keys,
which ``tests/test_webpush.py`` reproduces byte for byte. That test is what
makes writing it ourselves a smaller risk than it sounds.

Nothing here knows about users or reminders: it encrypts a payload for one
browser subscription and signs the request that delivers it.
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
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """HKDF-SHA256 for a single output block, which every use here fits in."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(
    payload: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    salt: bytes | None = None,
    as_private: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """RFC 8291 ``aes128gcm`` encryption of ``payload`` for one subscription.

    ``ua_public`` and ``auth_secret`` are the subscription's ``p256dh`` and
    ``auth`` keys. ``salt`` and ``as_private`` are fresh per message; they are
    parameters only so the RFC's worked example can be reproduced.
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
    """The server's identity to push services: an ES256 key pair and a contact."""

    private_key: ec.EllipticCurvePrivateKey
    subject: str

    @classmethod
    def from_settings(cls, private_key_b64: str, subject: str) -> "Vapid":
        """From the raw 32-byte private scalar, base64url -- the usual VAPID form."""
        scalar = int.from_bytes(b64url_decode(private_key_b64), "big")
        return cls(ec.derive_private_key(scalar, ec.SECP256R1()), subject)

    @property
    def public_key(self) -> str:
        """What the browser needs to subscribe: the public point, base64url."""
        return b64url_encode(_public_bytes(self.private_key.public_key()))

    def authorization(self, endpoint: str, now: float | None = None) -> str:
        """The RFC 8292 ``Authorization`` header for a request to ``endpoint``."""
        parts = urlsplit(endpoint)
        issued = int(now if now is not None else time.time())
        token = jwt.encode(
            {"aud": f"{parts.scheme}://{parts.netloc}", "exp": issued + 12 * 60 * 60, "sub": self.subject},
            self.private_key,
            algorithm="ES256",
        )
        return f"vapid t={token}, k={self.public_key}"


def generate_keys() -> tuple[str, str]:
    """A new VAPID key pair as (private, public), both base64url. For the runbook."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = b64url_encode(key.private_numbers().private_value.to_bytes(32, "big"))
    return private, b64url_encode(_public_bytes(key.public_key()))


def request_for(endpoint: str, p256dh: str, auth: str, payload: bytes, vapid: Vapid) -> tuple[dict, bytes]:
    """The headers and body that deliver ``payload`` to one subscription."""
    body = encrypt(payload, b64url_decode(p256dh), b64url_decode(auth))
    headers = {
        "Authorization": vapid.authorization(endpoint),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        "Urgency": "normal",
    }
    return headers, body
