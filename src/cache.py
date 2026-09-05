"""A very small time-to-live cache, used to keep the family charts off UDL's back.

One family chart fans out to one UDL call per satellite, and an analyst
clicking between families would otherwise re-fetch the same element sets
within seconds. This holds each satellite's answer for a short window.

Deliberately in-process and unshared: each gunicorn worker keeps its own,
which means a cache miss is at worst one extra upstream call, and there is no
new dependency, no new port and nothing to operate. If a shared cache is ever
needed, that is a different decision with a different set of trade-offs - do
not quietly grow this into one.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class TTLCache:
    """Insertion-ordered cache with a fixed lifetime per entry.

    `clock` is injectable so tests can advance time without sleeping.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[str, tuple[float, Any]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None if absent or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if self._clock() - stored_at > self._ttl:
            del self._entries[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        # Re-inserting moves the key to the end, so a refreshed entry is the
        # last thing evicted rather than the first.
        self._entries.pop(key, None)
        self._entries[key] = (self._clock(), value)
        while len(self._entries) > self._max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
