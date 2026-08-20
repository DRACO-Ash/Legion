"""Unified Data Library (UDL) client.

Rewritten against CONTEXT-001's verified LEARNED register rather than a
generic guess. Two endpoints, both FACT (copied from CONTEXT-001 Section 5,
not re-derived):

/udl/notification - the JCO HRR high-interest satellite feed. This is the
SAME endpoint PSIRENS already pulls for its GEO population, so this app
shares a verified, battle-tested data source rather than inventing one.
  - Query: createdAt=>now-N hours (relative operator, URL-encoded by httpx
    automatically), dataMode=REAL, msgType=JCO-HRR-SATELLITES, source=JCO.
  - Returns a JSON list of notification records. Each record's msgBody is a
    direct array of {commonName, country, satNo (string), rank (1-5),
    orbitRegime}. Top-level record fields: classificationMarking, createdAt,
    createdBy, dataMode, id, msgType, origNetwork, origin, source.
  - Live baseline (6 Aug 2026): 2942 satellite entries, 594 GEO, marking
    U//DS-JCO-NOTIF. List cap 30,000 - time-slice above that (not yet
    needed here; flagged for when window_hours grows large).

/udl/elset - orbital element sets, keyed by satNo. Fields: satNo, epoch,
inclination, eccentricity, raan, argOfPerigee, meanAnomaly, meanMotion,
bStar, dataMode, classificationMarking, origObjectId, source. No target
field. Epoch range needs the trailing-Z microsecond form if filtering by
time.

INFERENCE, flagged for Ash to confirm: whether /udl/elset accepts a direct
`satNo=` equality filter for a single-object lookup (the LEARNED register
documents the response field names, not this specific query parameter).
Also inference: the notification window semantics (does a wider
window_hours return the full current baseline, or only deltas created in
that window). Both are marked as assumptions in the docstrings below, not
asserted as fact.

The client never logs or returns credentials; upstream failures are logged
with detail server-side and surfaced to callers as a generic UDLError so a
route handler can turn that into a generic client-facing error rather than
leaking upstream internals.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("udl_tactics_app.udl_client")

ENDPOINT_NOTIFICATION = "/udl/notification"
ENDPOINT_ELSET = "/udl/elset"

NOTIFICATION_LIST_CAP = 30_000  # FACT, CONTEXT-001 Section 5 - slice by time above this


class UDLError(Exception):
    """Raised for any upstream UDL failure. Message is safe to log, not to return raw."""


class UDLNotConfigured(UDLError):
    """Raised when no UDL credentials are available at all."""


class UDLClient:
    def __init__(
        self,
        base_url: str,
        username: str | None,
        password: str | None,
        timeout_seconds: float,
    ):
        self._base_url = base_url
        self._configured = bool(username and password)
        self._timeout = timeout_seconds
        auth = httpx.BasicAuth(username, password) if username and password else None
        # httpx's default Accept header is "*/*", which satisfies the one
        # verified header rule (eoobservation/history requires Accept: */*).
        # That rule is confirmed only for that endpoint; generalising it to
        # notification/elset is inference, but the default is harmless either way.
        self._http = httpx.AsyncClient(
            base_url=base_url, auth=auth, timeout=timeout_seconds
        )

    @property
    def configured(self) -> bool:
        return self._configured

    async def aclose(self) -> None:
        await self._http.aclose()

    def _require_configured(self) -> None:
        if not self._configured:
            raise UDLNotConfigured("UDL credentials are not configured")

    async def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        try:
            response = await self._http.get(path, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("UDL request timed out after %.1fs: %s", self._timeout, exc)
            raise UDLError("UDL request timed out") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "UDL returned HTTP %s for %s", exc.response.status_code, path
            )
            raise UDLError(
                f"UDL upstream error (HTTP {exc.response.status_code})"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("UDL request failed: %s", exc)
            raise UDLError("UDL request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            logger.warning("UDL returned a non-JSON body from %s", path)
            raise UDLError("UDL returned an unexpected response body") from exc

    async def fetch_jco_hrr(self, *, window_hours: int = 24) -> list[dict[str, Any]]:
        """Fetch the JCO HRR high-interest feed and flatten every record's msgBody
        into a single list of satellite entries: {commonName, country, satNo,
        rank, orbitRegime}.

        INFERENCE: window_hours=24 as a default is a guess at what returns a
        useful current snapshot, not a confirmed semantic - confirm against
        your PSIRENS pull window before relying on this for anything beyond
        the ad-hoc clash-check.
        """
        self._require_configured()
        params = {
            "createdAt": f">now-{window_hours} hours",
            "dataMode": "REAL",
            "msgType": "JCO-HRR-SATELLITES",
            "source": "JCO",
        }
        payload = await self._get_json(ENDPOINT_NOTIFICATION, params)

        if not isinstance(payload, list):
            logger.warning(
                "UDL notification endpoint returned an unexpected shape: %s",
                type(payload).__name__,
            )
            raise UDLError("UDL returned an unexpected response shape")

        satellites: list[dict[str, Any]] = []
        for record in payload:
            msg_body = record.get("msgBody") if isinstance(record, dict) else None
            if isinstance(msg_body, list):
                satellites.extend(
                    entry for entry in msg_body if isinstance(entry, dict)
                )
        return satellites

    async def find_by_common_name(
        self, common_name: str, *, window_hours: int = 24
    ) -> dict[str, Any] | None:
        """Case-insensitive exact match on commonName within the JCO HRR feed."""
        satellites = await self.fetch_jco_hrr(window_hours=window_hours)
        target = common_name.strip().casefold()
        for entry in satellites:
            if str(entry.get("commonName", "")).strip().casefold() == target:
                return entry
        return None

    async def search_by_common_name(
        self, query: str, *, window_hours: int = 24
    ) -> list[dict[str, Any]]:
        """Case-insensitive substring match on commonName within the JCO HRR feed."""
        satellites = await self.fetch_jco_hrr(window_hours=window_hours)
        needle = query.strip().casefold()
        return [
            e
            for e in satellites
            if needle in str(e.get("commonName", "")).strip().casefold()
        ]

    async def get_elset(self, sat_no: str) -> dict[str, Any] | None:
        """Look up the latest element set for a NORAD/satNo.

        INFERENCE: assumes /udl/elset accepts a direct `satNo=` equality
        filter and returns the most recent element set first. Neither is
        confirmed in the LEARNED register - flagged for you to check against
        a live pull before trusting this beyond a smoke test.
        """
        self._require_configured()
        payload = await self._get_json(ENDPOINT_ELSET, {"satNo": sat_no})
        if isinstance(payload, list):
            return payload[0] if payload else None
        if isinstance(payload, dict):
            return payload
        logger.warning(
            "UDL elset endpoint returned an unexpected shape: %s",
            type(payload).__name__,
        )
        raise UDLError("UDL returned an unexpected response shape")
