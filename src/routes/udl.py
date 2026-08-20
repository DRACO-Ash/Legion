from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from src.models import (
    ClashCandidate,
    ClashCheckResponse,
    ElsetRecord,
    JCOHRRRecord,
    SearchResponse,
)
from src.security import enforce_rate_limit, enforce_team_token
from src.udl_client import UDLError, UDLNotConfigured

logger = logging.getLogger("udl_tactics_app.routes.udl")

router = APIRouter(prefix="/api/udl")

# The three 2026 Russian objects whose source spreadsheet recorded the same
# NORAD ID (68762) against all three - see tactics_wiki.html for the flag.
# Queried by commonName against the JCO HRR feed so the true, distinct
# satNo values (if UDL holds them) surface directly rather than by ID,
# which is exactly what's in doubt.
CLASH_CANDIDATES = ["COSMOS-2612", "COSMOS-2613", "COSMOS-2614"]
CLASH_SOURCE_NORAD_ID = "68762"


def _gate(request: Request) -> None:
    settings = request.app.state.settings
    enforce_rate_limit(request.app.state.strict_limiter, request)
    enforce_team_token(request, settings.team_token)


def _to_generic_error(exc: Exception) -> HTTPException:
    if isinstance(exc, UDLNotConfigured):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UDL is not configured",
        )
    if isinstance(exc, UDLError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="UDL request failed"
        )
    logger.exception("Unexpected error handling UDL route")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error"
    )


@router.get("/jco-hrr", response_model=SearchResponse)
async def search_jco_hrr(
    request: Request,
    common_name: str | None = None,
    window_hours: int | None = None,
):
    """Search the JCO HRR high-interest feed by commonName substring."""
    _gate(request)
    if not common_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Provide common_name"
        )
    window_hours = (
        window_hours
        if window_hours is not None
        else request.app.state.settings.udl_jco_hrr_window_hours
    )

    client = request.app.state.udl_client
    try:
        raw_results = await client.search_by_common_name(
            common_name, window_hours=window_hours
        )
    except (UDLError, UDLNotConfigured) as exc:
        raise _to_generic_error(exc) from exc

    results = [JCOHRRRecord.from_udl(r) for r in raw_results]
    return SearchResponse(
        query={"common_name": common_name, "window_hours": window_hours},
        count=len(results),
        results=results,
    )


@router.get("/jco-hrr/{sat_no}", response_model=JCOHRRRecord)
async def get_jco_hrr_by_sat_no(
    request: Request, sat_no: str, window_hours: int | None = None
):
    _gate(request)
    window_hours = (
        window_hours
        if window_hours is not None
        else request.app.state.settings.udl_jco_hrr_window_hours
    )
    client = request.app.state.udl_client
    try:
        satellites = await client.fetch_jco_hrr(window_hours=window_hours)
    except (UDLError, UDLNotConfigured) as exc:
        raise _to_generic_error(exc) from exc

    for entry in satellites:
        if str(entry.get("satNo")) == str(sat_no):
            return JCOHRRRecord.from_udl(entry)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No JCO HRR record for that satNo"
    )


@router.get("/elset/{sat_no}", response_model=ElsetRecord)
async def get_elset(request: Request, sat_no: str):
    _gate(request)
    client = request.app.state.udl_client
    try:
        raw = await client.get_elset(sat_no)
    except (UDLError, UDLNotConfigured) as exc:
        raise _to_generic_error(exc) from exc

    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No element set for that satNo",
        )
    return ElsetRecord.from_udl(raw)


@router.get("/clash-check", response_model=ClashCheckResponse)
async def clash_check(request: Request, window_hours: int | None = None):
    """First test case: does UDL hold a distinct, correct satNo for each of
    COSMOS-2612/2613/2614, or does the source spreadsheet's 68762 collision
    reflect a real upstream ambiguity rather than a transcription error?"""
    _gate(request)
    window_hours = (
        window_hours
        if window_hours is not None
        else request.app.state.settings.udl_jco_hrr_window_hours
    )
    client = request.app.state.udl_client

    candidates: list[ClashCandidate] = []
    for name in CLASH_CANDIDATES:
        try:
            record = await client.find_by_common_name(name, window_hours=window_hours)
        except (UDLError, UDLNotConfigured) as exc:
            raise _to_generic_error(exc) from exc

        if record is None:
            candidates.append(
                ClashCandidate(
                    catalogue_name=name,
                    source_norad_id=CLASH_SOURCE_NORAD_ID,
                    udl_sat_no=None,
                    matches_source=None,
                    note="No JCO HRR entry for this name in the current window - it may not be JCO high-interest, or the window may be too narrow",
                )
            )
            continue

        parsed = JCOHRRRecord.from_udl(record)
        matches = parsed.sat_no == CLASH_SOURCE_NORAD_ID
        candidates.append(
            ClashCandidate(
                catalogue_name=name,
                source_norad_id=CLASH_SOURCE_NORAD_ID,
                udl_sat_no=parsed.sat_no,
                matches_source=matches,
                note="Matches source spreadsheet"
                if matches
                else "Differs from source spreadsheet - source likely a transcription error",
            )
        )

    distinct_ids = {c.udl_sat_no for c in candidates if c.udl_sat_no}
    found_count = sum(1 for c in candidates if c.udl_sat_no)
    if found_count == 0:
        summary = "UDL returned no JCO HRR entries for any of the three names in this window - widen window_hours or confirm these objects are JCO high-interest before trusting this result."
    elif len(distinct_ids) == found_count and found_count == len(CLASH_CANDIDATES):
        summary = "UDL reports three distinct satNo values; the spreadsheet's shared 68762 looks like a transcription error."
    elif len(distinct_ids) <= 1 and found_count == len(CLASH_CANDIDATES):
        summary = "UDL also reports a shared satNo across these objects; this may be a genuine upstream ambiguity, not just a spreadsheet error."
    else:
        summary = (
            "Mixed or incomplete results from UDL; review each candidate individually."
        )

    return ClashCheckResponse(
        summary=summary, window_hours=window_hours, candidates=candidates
    )
