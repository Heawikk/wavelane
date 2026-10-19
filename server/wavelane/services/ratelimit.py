"""A small in-memory limiter for the endpoints that guess-and-check can abuse.

It counts events per key inside a sliding window. State lives in this process
only, which is right for a single-instance server: a restart forgives everyone,
and nothing is shared that an attacker could poison. Behind several instances it
would need a shared store instead.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

#: Past this many tracked keys the idle ones are swept, so a flood of distinct
#: keys (one per spoofed address) cannot grow the table without bound.
_SWEEP_THRESHOLD = 10_000


class RateLimiter:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        events = self._events[key]
        while events and events[0] <= now - window:
            events.popleft()
        return events

    def retry_after(self, key: str, limit: int, window: float) -> int:
        """Seconds until `key` may act again; 0 if it is under the limit."""
        if not self.enabled:
            return 0
        now = time.monotonic()
        with self._lock:
            events = self._prune(key, window, now)
            if len(events) < limit:
                return 0
            # The oldest event leaving the window is what frees a slot.
            return max(1, int(events[0] + window - now) + 1)

    def add(self, key: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            if len(self._events) > _SWEEP_THRESHOLD:
                self._sweep(now)
            self._events[key].append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def _sweep(self, now: float) -> None:
        # Nothing here is older than a day, whatever the caller's window was.
        cutoff = now - 86_400
        stale = [key for key, events in self._events.items() if not events or events[-1] < cutoff]
        for key in stale:
            del self._events[key]

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        from ..config import get_settings

        _limiter = RateLimiter(enabled=get_settings().rate_limit_enabled)
    return _limiter
