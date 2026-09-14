"""Rate limiting for the two unauthenticated endpoints that cost real work.

`POST /api/auth/login` ran one bcrypt verification per request with nothing
bounding how many requests arrived. The careful timing-equalisation in
`password_service` defends a far smaller hole than an unbounded guessing loop
against an 8-character minimum password.

Deliberately hand-rolled rather than adding a throttling library: this is a
single-process app, `requirements.txt` is already carrying ~30 packages it does
not use, and the whole mechanism is forty lines.

**Limits of this approach, stated plainly.** State lives in this process's
memory, so it resets on restart and is not shared between workers. Running more
than one worker, or putting this behind several instances, needs a shared store
(Redis) instead. For a single-process personal app it is the right size; it is
not a substitute for an edge rate limiter in front of a public deployment.

**And a second limit that matters more once this is deployed.** Every key here
is derived from `request.client.host`, the peer address. Behind a proxy that is
the proxy, not the caller -- so on a platform like Cloud Run these limiters
collapse towards a single shared budget rather than one per person. That is not
useless (an unbounded loop still stops) but it is a different thing from what
runs locally, and the registration ceiling below is chosen with it in mind. The
fix is to read a *trusted* forwarded-for header, which is a decision about the
specific proxy and is deliberately not made here; see `client_of` in
`api/routes/auth.py`.
"""

import threading
import time

#: Attempts allowed per key inside the window, then the key is refused.
MAX_ATTEMPTS = 8
#: Sliding window, in seconds.
WINDOW_SECONDS = 15 * 60
#: Ceiling on tracked keys, so someone rotating the email they guess against
#: cannot grow this dict without bound. When full, the stalest keys go first.
MAX_KEYS = 4096


class SlidingWindowLimiter:
    """Counts recent attempts per key, and forgets them as the window slides."""

    def __init__(self, max_attempts: int = MAX_ATTEMPTS, window_seconds: int = WINDOW_SECONDS):
        self._max_attempts = max_attempts
        self._window = window_seconds
        # key -> the timestamps of its recent attempts, oldest first
        self._hits: dict[str, list[float]] = {}
        # Sync routes run in FastAPI's threadpool, so this is touched from many
        # threads at once.
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may try again, or None if it may try now."""
        with self._lock:
            hits = self._prune(key, time.monotonic())
            if len(hits) < self._max_attempts:
                return None
            # The window clears when its oldest attempt falls out of it.
            return max(1, int(hits[0] + self._window - time.monotonic()) + 1)

    def record_attempt(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            hits = self._prune(key, now)
            hits.append(now)
            self._hits[key] = hits
            self._evict_if_full()

    def reset(self, key: str) -> None:
        """Forget a key's history, called when it authenticates successfully."""
        with self._lock:
            self._hits.pop(key, None)

    def _prune(self, key: str, now: float) -> list[float]:
        cutoff = now - self._window
        hits = [hit for hit in self._hits.get(key, []) if hit > cutoff]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def _evict_if_full(self) -> None:
        if len(self._hits) <= MAX_KEYS:
            return
        # Oldest last-attempt first. Only reached under a deliberate flood.
        stalest = sorted(self._hits, key=lambda k: self._hits[k][-1])
        for key in stalest[: len(self._hits) - MAX_KEYS]:
            self._hits.pop(key, None)


#: Per (address, client) pair: stops guessing at one account from one place.
per_account = SlidingWindowLimiter()
#: Per client alone: stops one place spraying one guess across many addresses,
#: which the per-account limiter would never see. Looser, since a shared NAT or
#: a household can legitimately hold several accounts.
per_client = SlidingWindowLimiter(max_attempts=30)

#: Registration allowed per client inside its window. Deliberately generous.
#: Two things push it up: a shared network (a campus, a house) is one key, and
#: behind a proxy *everyone* is one key -- see the module docstring. A ceiling
#: tuned for one person per address would lock out the group this app is for.
#: It is still a hard bound where there was none, and the invitation list is the
#: control that actually decides who gets an account.
REGISTRATION_MAX_ATTEMPTS = 20
#: An hour, not the fifteen minutes login uses. Signing up is a once-ever
#: action, so a slow window costs a real person nothing and costs a script the
#: whole day.
REGISTRATION_WINDOW_SECONDS = 60 * 60

#: Unlike the two above, this counts *every* attempt rather than only the
#: failures. Login is guarding a secret, so a success proves the caller is
#: entitled and its history is cleared. Registration has no secret to guard: the
#: thing being spent is a database row and a ~200ms password hash, and a
#: successful signup spends both. Counting only the failures would bound
#: enumeration while leaving the flood -- the larger problem -- unbounded.
per_client_registration = SlidingWindowLimiter(
    max_attempts=REGISTRATION_MAX_ATTEMPTS,
    window_seconds=REGISTRATION_WINDOW_SECONDS,
)


def account_key(email: str, client: str) -> str:
    return f"{email.strip().lower()}|{client}"
