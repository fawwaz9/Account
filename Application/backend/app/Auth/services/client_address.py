"""The caller's network address, for the rate limiters and the audit log.

Behind Cloud Run the peer is the platform's proxy, so `client_of` reads
`X-Forwarded-For` counting `TRUSTED_PROXY_HOPS` entries in from the right, the end
each proxy appends to; the left end is whatever the client wrote. With 0 hops, or
any entry that does not hold up, it falls back to the peer address, which can only
merge callers into one budget, never give anyone a fresh one.
"""
import ipaddress

from fastapi import Request

from app.config import settings

HEADER = "x-forwarded-for"


def peer_of(request: Request) -> str:
    """Return the address of the connection's peer, or "unknown" when there is none.

    Args:
        request: The incoming request.

    Returns:
        The peer's host, or "unknown".
    """
    return request.client.host if request.client else "unknown"


def client_of(request: Request, hops: int | None = None) -> str:
    """Return the caller's address as the trusted proxy saw it, or the peer's.

    Args:
        request: The incoming request; every `X-Forwarded-For` header is read as one
            list, in order.
        hops: Trusted proxies counted from the right; None uses
            `settings.TRUSTED_PROXY_HOPS`, and 0 or less ignores the header.

    Returns:
        The normalised IP address `hops` entries from the right, or the peer address
        when the header is missing, too short or that entry is not an IP address.
    """
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
