"""In-memory sliding-window rate limiters for login and registration.

State lives in this process only: it resets on restart and is not shared between
workers or Cloud Run instances, so each instance enforces its own budget. Keys use
the caller's address from `client_of`.
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
    """Counts attempts per key over a sliding window, and refuses a key once it is full.

    Thread-safe: routes run in FastAPI's threadpool. At most `MAX_KEYS` keys are kept,
    the stalest evicted first.

    Args:
        max_attempts: Attempts a key may make inside the window.
        window_seconds: Length of the sliding window, in seconds.
    """

    def __init__(self, max_attempts: int = MAX_ATTEMPTS, window_seconds: int = WINDOW_SECONDS):
        self._max_attempts = max_attempts
        self._window = window_seconds
        # key -> the timestamps of its recent attempts, oldest first
        self._hits: dict[str, list[float]] = {}
        # Sync routes run in FastAPI's threadpool, so this is touched from many
        # threads at once.
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Return the seconds until a key may try again, or None if it may try now.

        Args:
            key: The limiter key, such as `account_key(...)` or a client address.

        Returns:
            None while the key has fewer than `max_attempts` attempts in the window;
            otherwise the whole seconds (at least 1) until its oldest attempt expires.
        """
        with self._lock:
            hits = self._prune(key, time.monotonic())
            if len(hits) < self._max_attempts:
                return None
            # The window clears when its oldest attempt falls out of it.
            return max(1, int(hits[0] + self._window - time.monotonic()) + 1)

    def record_attempt(self, key: str) -> None:
        """Record an attempt for a key now; evict the stalest keys past `MAX_KEYS`.

        Args:
            key: Limiter key, such as one from `account_key`.
        """
        with self._lock:
            now = time.monotonic()
            hits = self._prune(key, now)
            hits.append(now)
            self._hits[key] = hits
            self._evict_if_full()

    def reset(self, key: str) -> None:
        """Forget a key's attempts; called when it authenticates successfully.

        Args:
            key: Limiter key to clear.
        """
        with self._lock:
            self._hits.pop(key, None)

    def _prune(self, key: str, now: float) -> list[float]:
        """Drop a key's attempts older than the window and return the rest."""
        cutoff = now - self._window
        hits = [hit for hit in self._hits.get(key, []) if hit > cutoff]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def _evict_if_full(self) -> None:
        """Evict keys, oldest last attempt first, until `MAX_KEYS` remain."""
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
    """Return the per-account limiter key: normalised email and client address.

    Args:
        email: Address the sign-in was attempted for.
        client: The caller's address, from `client_of`.

    Returns:
        The key, as "email|client".
    """
    return f"{email.strip().lower()}|{client}"
