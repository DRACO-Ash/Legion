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
import logging
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status

logger = logging.getLogger("udl_tactics_app.security")


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


# Characters that a copy through a document, a chat client or a PDF quietly
# substitutes for their ASCII originals. Every one of them is a single
# character, so a value carrying them still reports the same length as the
# real token: length stops being able to tell them apart, which is exactly the
# case this describes.
LOOK_ALIKES = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u00a0": " ",
    "\u202f": " ",
}
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
_LOOK_ALIKE_TABLE = str.maketrans(LOOK_ALIKES)

NO_TOKEN_RECEIVED = (
    "No bearer token reached the app. If this tab has one saved, something "
    "between the browser and the app is removing the Authorization header."
)
TOKEN_MATCHES = "The token matches. Anything still failing is not the token."
TOKEN_LOOK_ALIKES = (
    "The two values differ only by invisible or look-alike characters, the "
    "kind a copy through a document or chat client introduces. Re-copy the "
    "token from a plain-text source."
)
TOKEN_CASE_ONLY = "The two values differ only in letter case."
TOKEN_NON_ASCII = (
    "Same number of characters but a different number of bytes: the value "
    "sent here contains at least one non-ASCII character. Re-copy it from a "
    "plain-text source."
)
TOKEN_LENGTH_DIFFERS = (
    "Different lengths. If this tab shows the right number, the header was "
    "altered between the browser and the app; if not, the paste is incomplete."
)
TOKEN_GENUINELY_DIFFERENT = (
    "Same shape, different values. Re-copy TEAM_TOKEN from the Configuration "
    "tab, and check the app has restarted since it was last changed."
)


def _repair(value: str) -> str:
    """Undo the substitutions a copy-paste makes, so a comparison can say
    whether that is all that differs."""
    repaired = unicodedata.normalize("NFKC", value)
    return repaired.translate(_ZERO_WIDTH).translate(_LOOK_ALIKE_TABLE).strip()


def _shape(value: str) -> dict[str, object]:
    """What a value looks like, never what it is."""
    return {
        "characters": len(value),
        "utf8_bytes": len(value.encode("utf-8")),
        "ascii_only": value.isascii(),
        "has_whitespace": any(character.isspace() for character in value),
    }


def _verdict(given: str, expected: str) -> str:
    if _repair(given) == _repair(expected):
        return TOKEN_LOOK_ALIKES
    if given.casefold() == expected.casefold():
        return TOKEN_CASE_ONLY
    if len(given) != len(expected):
        return TOKEN_LENGTH_DIFFERS
    if len(given.encode("utf-8")) != len(expected.encode("utf-8")):
        return TOKEN_NON_ASCII
    return TOKEN_GENUINELY_DIFFERENT


def describe_token_difference(given: str | None, expected: str) -> dict[str, object]:
    """Say how two tokens differ without revealing either.

    Lengths, byte counts and a handful of booleans, and never a character, a
    position or a digest. The caller already holds the value it sent, so the
    only new information is the shape of the difference, which is the thing
    that two equal lengths cannot express.

    This exists because a live deployment sat at "both are 43 characters" with
    no way to get further: a look-alike hyphen or a non-breaking space is one
    character and reads identically.
    """
    if given is None:
        return {"matches": False, "received": None, "verdict": NO_TOKEN_RECEIVED}
    if token_matches(given, expected):
        return {
            "matches": True,
            "received": _shape(given),
            "configured": _shape(expected),
            "verdict": TOKEN_MATCHES,
        }
    return {
        "matches": False,
        "received": _shape(given),
        "configured": _shape(expected),
        "verdict": _verdict(given, expected),
    }


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

    Three outcomes, and they are deliberately distinguishable: no token
    configured on the deployment is 503 with a reason, a wrong or missing
    bearer token is 401, and a match passes. The UI turns the 401 into
    different advice depending on whether it sent a token at all, because
    "set the team token" is useless advice to someone who just did.

    Fails closed when no token is configured. This used to return early, so a
    deployment that never set TEAM_TOKEN accepted unauthenticated writes from
    anyone who could reach it, while the UI displayed "read only" and looked
    safe. The UI hint is a convenience; this is the control. Set TEAM_TOKEN
    (see .env.example) to enable writes, locally as well as in deployment.
    """
    if not team_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Refused: no team token is configured for this deployment. "
                "Set TEAM_TOKEN to enable writes and UDL lookups."
            ),
        )
    given = extract_bearer_token(request)
    if not token_matches(given, team_token):
        # Lengths only, never the values, and server-side where the log is
        # already privileged. Equal lengths with a failed compare is the
        # useful case: two different tokens are usually the same length, so
        # the log is what distinguishes a mistyped value from a worker that
        # never picked up a configuration change.
        logger.warning(
            "Team token rejected: caller sent %d characters, this process is "
            "configured with %d",
            len(given or ""),
            len(team_token),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token"
        )
