"""Rate limiting.

Threat model (server archetype): the high-value assets are the UDL
credentials and the UDL call budget, not secrecy of the catalogue data
itself, which is drawn from public-domain sources. The credentials never
leave the process and never appear in a response; the call budget is
protected by the two-tier limiter below.

There is deliberately no application-level authentication. A shared bearer
token was tried and removed in 0.9.0: it cost more operator time to
diagnose than it ever protected, and it gated the UDL lookups that are the
point of the application. Access control belongs to the platform in front
of this app, not to a secret pasted into a browser tab. If an
application-level control is ever needed again, it should be real identity
from the platform, not a shared string.

No new runtime dependency was added for rate limiting; a small in-memory
limiter per key covers the two-tier requirement without pulling in
slowapi/limits for a single-process app. Note this does not survive a
process restart or scale beyond one replica - acceptable for this
deployment, recorded here rather than left silent.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status


@dataclass
class RateLimiter:
    """Fixed-window-ish limiter: at most `limit` calls per `window_seconds` per key."""

    limit: int
    window_seconds: float
    _hits: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


def client_key(request: Request) -> str:
    """Best-effort caller identity for rate-limit bucketing; not an auth control."""
    if request.client:
        return request.client.host
    return "unknown"


def enforce_rate_limit(limiter: RateLimiter, request: Request) -> None:
    if not limiter.allow(client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded"
        )
