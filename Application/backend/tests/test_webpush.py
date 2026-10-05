"""The Web Push protocol against its own standard.

RFC 8291 section 5 and Appendix A publish a complete example: fixed keys, a
fixed salt, a plaintext, and the exact bytes that must result. Reproducing them
byte for byte is what makes it reasonable to have written this protocol here
instead of importing a library for it.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.Notifications.services.webpush import (
    Vapid,
    _hkdf,
    b64url_decode,
    b64url_encode,
    encrypt,
    generate_keys,
    request_for,
)

# RFC 8291, section 5.
PLAINTEXT = b"When I grow up, I want to be a watermelon"
AUTH_SECRET = "BTBZMqHH6r4Tts7J_aSIgg"
UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"
MESSAGE = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
    "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
    "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)


def private_key(b64: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(b64url_decode(b64), "big"), ec.SECP256R1())


def decrypt(message: bytes, ua_private: ec.EllipticCurvePrivateKey, auth_secret: bytes) -> bytes:
    """The receiving browser's side, written from the RFC independently of encrypt()."""
    salt, idlen = message[:16], message[20]
    as_public = message[21:21 + idlen]
    ciphertext = message[21 + idlen:]
    from cryptography.hazmat.primitives import serialization
    ua_public = ua_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    secret = ua_private.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = _hkdf(auth_secret, secret, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


def test_reproduces_the_rfc_8291_example_exactly():
    message = encrypt(
        PLAINTEXT, b64url_decode(UA_PUBLIC), b64url_decode(AUTH_SECRET),
        salt=b64url_decode(SALT), as_private=private_key(AS_PRIVATE),
    )
    assert b64url_encode(message) == MESSAGE


def test_the_receiver_can_read_a_fresh_message():
    message = encrypt(PLAINTEXT, b64url_decode(UA_PUBLIC), b64url_decode(AUTH_SECRET))
    assert decrypt(message, private_key(UA_PRIVATE), b64url_decode(AUTH_SECRET)) == PLAINTEXT


def test_every_message_is_encrypted_afresh():
    """A new salt and a new sender key each time: the same text never repeats."""
    one = encrypt(PLAINTEXT, b64url_decode(UA_PUBLIC), b64url_decode(AUTH_SECRET))
    two = encrypt(PLAINTEXT, b64url_decode(UA_PUBLIC), b64url_decode(AUTH_SECRET))
    assert one != two


def test_vapid_signs_for_the_push_services_origin_only():
    private, public = generate_keys()
    vapid = Vapid.from_settings(private, "mailto:owner@example.com")
    assert vapid.public_key == public

    now = time.time()
    header = vapid.authorization("https://fcm.googleapis.com/fcm/send/abc123", now=now)
    token = header.split("t=")[1].split(",")[0]
    assert header.endswith(f"k={public}")

    verifying = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64url_decode(public))
    claims = jwt.decode(token, verifying, algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert claims["sub"] == "mailto:owner@example.com"
    assert 0 < claims["exp"] - now <= 24 * 60 * 60  # RFC 8292: at most a day

    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(token, verifying, algorithms=["ES256"], audience="https://evil.example")


def test_a_request_is_what_a_push_service_expects():
    private, _ = generate_keys()
    headers, body = request_for(
        "https://updates.push.services.mozilla.com/wpush/v2/xyz", UA_PUBLIC, AUTH_SECRET,
        b'{"title":"x"}', Vapid.from_settings(private, "mailto:a@example.com"),
    )
    assert headers["Content-Encoding"] == "aes128gcm"
    assert headers["Authorization"].startswith("vapid t=")
    assert int(headers["TTL"]) > 0
    assert decrypt(body, private_key(UA_PRIVATE), b64url_decode(AUTH_SECRET)) == b'{"title":"x"}'
