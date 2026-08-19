from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

STATUS_VALUES = Literal["onorbit", "decaying", "decayed", "unknown"]


class TrackedSystemCreate(BaseModel):
    """Boundary-validated input for a new tracked system. Every field an
    analyst can set on creation; required fields are the minimum needed to
    place a record meaningfully on the timeline and in a family group."""

    family_id: str = Field(min_length=1, description="Slug grouping this with related objects, e.g. 'rus-2027-cluster'")
    family_title: str = Field(min_length=1)
    family_sub: str = Field(min_length=1)
    nation: str = Field(min_length=1, max_length=4, description="Free-text nation code, e.g. RU, CN, IR, KP")
    designator: str | None = None
    catalogue_name: str = Field(min_length=1)
    launch_year: int = Field(ge=1957, le=2100)
    launch_site: str | None = None
    norad_id: str | None = None
    regime: str = Field(min_length=1, description="e.g. LEO, GEO, HEO, MEO")
    delta_v: str | None = None
    status: STATUS_VALUES = "unknown"
    life: str | None = None
    coplanar: str | None = None
    notes: str | None = None
    flag: str | None = None


class TrackedSystemUpdate(BaseModel):
    """All fields optional - only the ones sent are merged (anti-shrink)."""

    family_id: str | None = None
    family_title: str | None = None
    family_sub: str | None = None
    nation: str | None = None
    designator: str | None = None
    catalogue_name: str | None = None
    launch_year: int | None = None
    launch_site: str | None = None
    norad_id: str | None = None
    regime: str | None = None
    delta_v: str | None = None
    status: STATUS_VALUES | None = None
    life: str | None = None
    coplanar: str | None = None
    notes: str | None = None
    flag: str | None = None


class TrackedSystem(TrackedSystemCreate):
    id: str
    archived: bool
    created_at: str
    updated_at: str


class TrackedSystemList(BaseModel):
    count: int
    systems: list[TrackedSystem]


class JCOHRRRecord(BaseModel):
    """A single satellite entry from the JCO HRR msgBody array (FACT schema,
    CONTEXT-001 Section 5): commonName, country, satNo, rank, orbitRegime."""

    common_name: str | None = None
    country: str | None = None
    sat_no: str | None = None
    rank: int | None = None
    orbit_regime: str | None = None
    raw: dict

    @classmethod
    def from_udl(cls, record: dict) -> "JCOHRRRecord":
        return cls(
            common_name=record.get("commonName"),
            country=record.get("country"),
            sat_no=str(record["satNo"]) if record.get("satNo") is not None else None,
            rank=record.get("rank"),
            orbit_regime=record.get("orbitRegime"),
            raw=record,
        )


class ElsetRecord(BaseModel):
    """Element set fields per CONTEXT-001 Section 5 (FACT schema)."""

    sat_no: str | None = None
    epoch: str | None = None
    inclination: float | None = None
    eccentricity: float | None = None
    raan: float | None = None
    arg_of_perigee: float | None = None
    mean_anomaly: float | None = None
    mean_motion: float | None = None
    classification_marking: str | None = None
    raw: dict

    @classmethod
    def from_udl(cls, record: dict) -> "ElsetRecord":
        return cls(
            sat_no=str(record["satNo"]) if record.get("satNo") is not None else None,
            epoch=record.get("epoch"),
            inclination=record.get("inclination"),
            eccentricity=record.get("eccentricity"),
            raan=record.get("raan"),
            arg_of_perigee=record.get("argOfPerigee"),
            mean_anomaly=record.get("meanAnomaly"),
            mean_motion=record.get("meanMotion"),
            classification_marking=record.get("classificationMarking"),
            raw=record,
        )


class SearchResponse(BaseModel):
    query: dict
    count: int
    results: list[JCOHRRRecord]


class ClashCandidate(BaseModel):
    catalogue_name: str
    source_norad_id: str
    udl_sat_no: str | None
    matches_source: bool | None  # None when UDL had nothing for this name
    note: str


class ClashCheckResponse(BaseModel):
    summary: str
    window_hours: int
    candidates: list[ClashCandidate]
