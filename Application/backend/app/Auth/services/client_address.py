"""Who is calling, for the rate limiters and the audit log (Phase 2 item 12a, D18).

Behind Cloud Run the peer address is the platform's proxy, so keying the
limiters on it made them one shared budget for everyone (production logs: 99
of 99 requests from one internal address). The caller's address is in
``X-Forwarded-For`` -- but that header is a list anyone can start. A client
sends ``X-Forwarded-For: 203.0.113.7`` and the front end appends the real
address after it, so **the left end is attacker-controlled and only the right
end is trustworthy**: each proxy appends the address it actually saw.

So: count ``TRUSTED_PROXY_HOPS`` entries in from the right, and use that one.
Never the leftmost, never "the first public address". With 0 (the default) the
header is ignored entirely, which is exactly the old behaviour; the switch is
flipped in production only once a forged-header request has shown the right
address in the logs.

Anything that does not hold up -- no header, too few entries, an entry that is
not an IP address -- falls back to the peer address. Falling back is the safe
direction: it can only merge callers into the shared budget, never hand anyone
a fresh one.
"""
import ipaddress

from fastapi import Request

from app.config import settings

HEADER = "x-forwarded-for"


def peer_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def client_of(request: Request, hops: int | None = None) -> str:
    """The caller's address, as the trusted proxy saw it, or the peer's."""
    hops = settings.TRUSTED_PROXY_HOPS if hops is None else hops
    if hops <= 0:
        return peer_of(request)
    # Several X-Forwarded-For headers are one list, joined in order (RFC 7230).
    entries = [part.strip() for value in request.headers.getlist(HEADER) for part in value.split(",")]
    entries = [entry for entry in entries if entry]
    if len(entries) < hops:
        return peer_of(request)
    chosen = entries[-hops]
    try:
        return str(ipaddress.ip_address(chosen))
    except ValueError:
        return peer_of(request)
