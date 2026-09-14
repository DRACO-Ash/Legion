"""The GEO belt: every catalogued geostationary object at its derived longitude.

The stage of the interface. One picture of who is parked next to whom, which
is the question a table cannot answer and the reason this view exists.

Four things are load-bearing and easy to undo:

● **The rank gate is the chart's gate, reused, not reimplemented.** `hrr_ranks`
  and `_skip_reason` come from `src/family_elements.py` so the JCO HRR 0 to 3
  band cannot drift between the charts and the belt. A second copy would be a
  second place for Ash's rule to rot, and would trip the gate's
  duplicated-lines condition besides.
● **A feed failure stops the pull.** Same reasoning as the charts: a gate that
  cannot be applied must never quietly open. There is no fallback to "plot
  everything" when the rank feed is down.
● **An object without a longitude is excluded and says why.** Mean longitude
  needs RAAN, argument of perigee, mean anomaly and an epoch. A partial
  element set drops the object rather than placing it somewhere plausible,
  because a satellite drawn at the wrong slot looks entirely normal.
● **Only GEO objects are placed.** The belt is a GEO instrument. A LEO object
  has no meaningful belt longitude, so it is listed as off-plot rather than
  projected onto a circle it does not sit on.

Mean longitude is derived, never measured: RAAN plus argument of perigee plus
mean anomaly, less GMST at epoch. It holds for a near-circular, near-equatorial
orbit, and it is good for drift and station-keeping and not for conjunction
assessment. The interface says so on the plot itself.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from src.family_elements import (
    MAX_SERIES,
    _skip_reason,
    hrr_ranks,
    order_members,
)
from src.orbits import is_geo_regime, mean_longitude_degrees, parse_epoch

logger = logging.getLogger("udl_tactics_app.belt")

OFF_PLOT_NOT_GEO = "Not a GEO object, so it has no belt longitude"
OFF_PLOT_NO_ELSET = "No element set came back for this satellite"
OFF_PLOT_NO_LONGITUDE = (
    "The element set is missing a field the longitude derivation needs"
)

DERIVATION_NOTE = (
    "Mean longitude is derived as RAAN plus argument of perigee plus mean "
    "anomaly, less GMST at epoch. Good for drift and station-keeping. Never "
    "for conjunction assessment."
)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _longitude_of(record: dict[str, Any]) -> tuple[float | None, dt.datetime | None]:
    """The derived mean longitude of one element set, and its epoch."""
    epoch = parse_epoch(record.get("epoch"))
    longitude = mean_longitude_degrees(
        raan=_as_float(record.get("raan")),
        arg_of_perigee=_as_float(record.get("argOfPerigee")),
        mean_anomaly=_as_float(record.get("meanAnomaly")),
        epoch=epoch,
    )
    return longitude, epoch


def _colour_index(system: dict[str, Any], family_order: dict[str, list[str]]) -> int:
    """The object's launch-order position within its own family.

    Colour follows the satellite, never its position in the belt result, so
    filtering the belt never repaints a surviving object and a satellite looks
    the same here as it does in its family's chart.
    """
    family = family_order.get(str(system.get("family_id")), [])
    try:
        return family.index(str(system.get("id"))) % MAX_SERIES
    except ValueError:
        return 0


def family_launch_order(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Each family's member ids, in launch order, for the colour assignment."""
    families: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        families.setdefault(str(record.get("family_id")), []).append(record)
    return {
        family_id: [str(member.get("id")) for member in order_members(members)]
        for family_id, members in families.items()
    }


async def build_belt(
    *,
    client: Any,
    cache: Any,
    records: list[dict[str, Any]],
    hrr_window_hours: int,
) -> dict[str, Any]:
    """Place every eligible GEO object on the belt.

    One feed call ranks the whole catalogue, then one element-set lookup per
    eligible object. Everything excluded is listed with the reason, because an
    object that silently vanishes from the belt reads as an object that is not
    there.
    """
    ranks = await hrr_ranks(client, cache, hrr_window_hours)
    order = family_launch_order(records)

    placed: list[dict[str, Any]] = []
    off_plot: list[dict[str, Any]] = []

    for record in records:
        name = record.get("catalogue_name")
        if not is_geo_regime(record.get("regime")):
            off_plot.append({"name": name, "reason": OFF_PLOT_NOT_GEO})
            continue

        # The charts' own gate, applied unchanged. charted_so_far is passed as
        # 0 deliberately: the eight-slot palette limit is a per-chart rule, and
        # the belt is not a chart. Colour still comes from family position.
        rank = (
            ranks.get(str(record.get("norad_id"))) if record.get("norad_id") else None
        )
        skip = _skip_reason(record, rank, 0)
        if skip is not None:
            off_plot.append({"name": name, "reason": skip})
            continue

        elset = await client.get_elset(str(record.get("norad_id")))
        if not elset:
            off_plot.append({"name": name, "reason": OFF_PLOT_NO_ELSET})
            continue

        longitude, epoch = _longitude_of(elset)
        if longitude is None:
            off_plot.append({"name": name, "reason": OFF_PLOT_NO_LONGITUDE})
            continue

        placed.append(
            {
                "id": record.get("id"),
                "name": name,
                "norad_id": record.get("norad_id"),
                "family_id": record.get("family_id"),
                "family_title": record.get("family_title"),
                "nation": record.get("nation"),
                "longitude": round(longitude, 2),
                "epoch": epoch.isoformat() if epoch else None,
                "rank": rank,
                "colour_index": _colour_index(record, order),
            }
        )

    placed.sort(key=lambda entry: entry["longitude"])
    return {
        "count": len(placed),
        "placed": placed,
        "off_plot": off_plot,
        "derivation": DERIVATION_NOTE,
    }
