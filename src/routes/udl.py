from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from src.family_elements import build_family_charts, clamp_window_days
from src.models import (
    ClashCandidate,
    ClashCheckResponse,
    ElsetRecord,
    FamilyElementsResponse,
    JCOHRRRecord,
    SearchResponse,
)
from src.security import enforce_rate_limit
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

UDL_NOT_CONFIGURED_DETAIL = "UDL is not configured"


def _gate(request: Request) -> None:
    """Rate limit a UDL-facing route.

    These routes cost a live UDL call, so the strict limiter is the control
    that matters: it protects the call budget. Authentication was removed in
    0.9.0 and is the platform's job.
    """
    enforce_rate_limit(request.app.state.strict_limiter, request)


def _to_generic_error(exc: Exception) -> HTTPException:
    # UDLNotConfigured subclasses UDLError, so catching UDLError catches both;
    # naming both in an except tuple is redundant. The distinction is made
    # here instead, where it decides the status code.
    if isinstance(exc, UDLNotConfigured):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UDL_NOT_CONFIGURED_DETAIL,
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
    except UDLError as exc:
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
    except UDLError as exc:
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
    except UDLError as exc:
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
        except UDLError as exc:
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


@router.get("/family-elements", response_model=FamilyElementsResponse)
async def family_elements(
    request: Request, family_id: str, window_days: int | None = None
):
    """Element-set tracks for every catalogued member of one family.

    The catalogue supplies the membership and the NORAD IDs; UDL supplies the
    element sets. The family, not the filtered catalogue view, defines the
    series: a chart of a class is only meaningful with the whole class on it,
    so a nation or status filter in the UI narrows the table without silently
    narrowing the chart.

    Only objects at JCO HRR rank 0 to 3 are pulled. `window_days=0` asks for
    the full history UDL holds rather than a trailing window.
    """
    _gate(request)
    client = request.app.state.udl_client
    if not client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UDL_NOT_CONFIGURED_DETAIL,
        )

    store = request.app.state.systems_store
    members = [
        record
        for record in store.list(include_archived=False)
        if record.get("family_id") == family_id
    ]
    if not members:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No catalogued systems in that family",
        )

    try:
        return await build_family_charts(
            client=client,
            cache=getattr(request.app.state, "elset_cache", None),
            family_id=family_id,
            family_title=str(members[0].get("family_title") or family_id),
            members=members,
            window_days=clamp_window_days(window_days),
            hrr_window_hours=request.app.state.settings.udl_jco_hrr_window_hours,
        )
    except UDLError as exc:
        raise _to_generic_error(exc) from exc


@router.get("/object-elements", response_model=FamilyElementsResponse)
async def object_elements(
    request: Request, record_id: str, window_days: int | None = None
):
    """The element-set history of one catalogued object.

    Same rules as the family chart, deliberately: the JCO HRR rank 0 to 3 gate
    still applies, the metric still follows the regime, and the colour still
    comes from the object's launch-order position in its own family, so a
    satellite looks the same whether it is charted alone or beside its
    siblings. An object at rank 4 or 5, or absent from the feed, comes back
    with a skip reason and no chart rather than an unranked line.
    """
    _gate(request)
    client = request.app.state.udl_client
    if not client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=UDL_NOT_CONFIGURED_DETAIL,
        )

    store = request.app.state.systems_store
    record = next(
        (
            candidate
            for candidate in store.list(include_archived=True)
            if candidate.get("id") == record_id
        ),
        None,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No system with that id",
        )
    norad_id = str(record.get("norad_id") or "")
    if not norad_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That record carries no NORAD ID, so there is nothing to look "
                "up in UDL."
            ),
        )

    family_id = str(record.get("family_id") or "")
    siblings = [
        candidate
        for candidate in store.list(include_archived=False)
        if candidate.get("family_id") == family_id
    ] or [record]

    label = str(record.get("designator") or record.get("catalogue_name") or norad_id)
    try:
        return await build_family_charts(
            client=client,
            cache=getattr(request.app.state, "elset_cache", None),
            family_id=family_id,
            family_title=label,
            members=siblings,
            window_days=clamp_window_days(window_days),
            hrr_window_hours=request.app.state.settings.udl_jco_hrr_window_hours,
            focus_norad_id=norad_id,
        )
    except UDLError as exc:
        raise _to_generic_error(exc) from exc
