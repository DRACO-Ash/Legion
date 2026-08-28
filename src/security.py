"""Authentication and rate limiting.

Threat model (server archetype): the high-value assets are the UDL
credentials and the UDL call budget, not secrecy of the (low-sensitivity,
already-public-domain) catalogue data itself. The trust boundary is the
HTTP edge - every request is untrusted until the team token is checked.

No new runtime dependency was added for rate limiting; a small in-memory
token-bucket-per-key limiter covers the two-tier requirement without
pulling in slowapi/limits for a single-process app. Note this does not
survive a process restart or scale beyond one replica - acceptable for a
first release, recorded here rather than left silent.
"""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status


def token_matches(given: str | None, expected: str) -> bool:
    """Constant-time compare with a length guard. `given` may be missing entirely."""
    given_bytes = (given or "").encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(given_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(given_bytes, expected_bytes)


def extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return header[7:].strip()


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


def enforce_team_token(request: Request, team_token: str | None) -> None:
    """Gate a state-changing or cost-incurring route.

    Fails closed when no token is configured. This used to return early, so a
    deployment that never set TEAM_TOKEN accepted unauthenticated writes from
    anyone who could reach it, while the UI displayed "read only" and looked
    safe. The UI hint is a convenience; this is the control. Set TEAM_TOKEN
    (see .env.example) to enable writes, locally as well as in deployment.
    """
    if not team_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Writes are disabled: no team token is configured for this deployment",
        )
    given = extract_bearer_token(request)
    if not token_matches(given, team_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token"
        )
