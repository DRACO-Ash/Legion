"""The relationship graph: the ontology made navigable.

Assembled on the server from what the store already holds, rather than kept
as a second copy of it. Three sources feed it and each one already carries
its own provenance, which is what makes the graph's central rule affordable:

● **Family membership** comes from the catalogue record's `family_id`.
● **Proximity and capture edges** come from pattern-of-life segments. A
  segment already names its counterpart and carries a claim, so the edge
  inherits both. Storing the same fact twice would let the timeline and the
  graph disagree about what happened.
● **Coplanar edges** come from the catalogue's own `coplanar` field, sourced
  to the catalogue as a source class in its own right. The spreadsheet said
  it, and saying so is different from saying an analyst assessed it.

Hand-authored edges in the compendium's `relationships` collection are added
on top, and they carry a claim by model.

**No edge is unsourced**, which is the phase's bar. Every one arrives with a
marker, a confidence and a citation, and `edge_tone` maps the marker to the
same redundant encoding the rest of the application uses.

Node ids are namespaced so they cannot collide: a catalogued object is its
store id, a family is `family:<family_id>`, and a counterpart outside the
catalogue keeps the `target:` slug it already had.
"""

from __future__ import annotations

from typing import Any

from src.compendium_models import INSTANTANEOUS_MODES
from src.pol import MODE_LABELS

FAMILY_PREFIX = "family:"
TARGET_PREFIX = "target:"

OBJECT = "object"
FAMILY = "family"
TARGET = "target"

BELONGS_TO_FAMILY = "belongs_to_family"
COPLANAR_WITH = "coplanar_with"

# Which edge a pattern-of-life mode implies. Only modes that are genuinely a
# relationship between two things appear: a drift or a station-keep is a
# behaviour, not an edge, and inventing one would fill the graph with lines
# that mean nothing.
MODE_EDGE: dict[str, str] = {
    "rpo_inspection": "approached",
    "rpo_shadowing": "shadowed",
    "rpo_corkscrew": "approached",
    "rpo_docking": "captured",
    "pursuit": "approached",
    "separation_event": "birthed",
}

EDGE_LABELS: dict[str, str] = {
    BELONGS_TO_FAMILY: "belongs to",
    COPLANAR_WITH: "coplanar with",
    "shadowed": "shadowed",
    "birthed": "released",
    "approached": "approached",
    "captured": "captured",
    "refuelled": "refuelled",
    "demonstrated_tactic": "demonstrated",
    "threatens": "threatens",
    "supports": "supports",
    "same_series_as": "same series as",
    "sourced_from": "sourced from",
}


def _catalogue_claim(field: str) -> dict[str, Any]:
    """A claim sourced to the catalogue itself, naming the field it came from.

    One shared claim for every catalogue-derived edge was wrong: a family
    membership edge cited the coplanar field, which is not where it came
    from. Caught in a browser, reading the citations the panel prints. A
    citation that names the wrong field is worse than none, because a reader
    who follows it finds something that does not support the edge.
    """
    return {
        "marker": "FACT",
        "confidence": "moderate",
        "source_class": "catalogue",
        "source_citation": f"Red_ASAT_Systems.xlsx, the catalogue's {field}",
        "asserted_by": "catalogue",
    }


MEMBERSHIP_CLAIM = _catalogue_claim("family_id field")
COPLANAR_CLAIM = _catalogue_claim("coplanar field")

_TONES = {"FACT": "fact", "INFERENCE": "inference", "SPECULATION": "speculation"}


def edge_tone(claim: dict[str, Any] | None) -> str:
    """Solid, dashed or dotted, from the claim's marker.

    Style alone never carries it: the interface prints the marker as text
    beside every edge it lists. This is the redundant half.
    """
    return _TONES.get(str((claim or {}).get("marker")), "inference")


def _object_node(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "type": OBJECT,
        "label": record.get("catalogue_name") or record["id"],
        "nation": record.get("nation"),
        "regime": record.get("regime"),
        "status": record.get("status"),
        "norad_id": record.get("norad_id"),
        "in_catalogue": True,
    }


def _family_node(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": FAMILY_PREFIX + str(record["family_id"]),
        "type": FAMILY,
        "label": record.get("family_title") or record["family_id"],
        "nation": record.get("nation"),
        "in_catalogue": True,
    }


def _target_node(node_id: str) -> dict[str, Any]:
    """A counterpart we do not hold. Marked as outside the catalogue, because
    presenting USA 314 as one of our systems would be a phantom object."""
    return {
        "id": node_id,
        "type": TARGET,
        "label": node_id[len(TARGET_PREFIX) :].replace("-", " "),
        "in_catalogue": False,
    }


def _edge(
    kind: str, source: str, target: str, claim: Any, detail: str
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": EDGE_LABELS.get(kind, kind),
        "source": source,
        "target": target,
        "tone": edge_tone(claim),
        "marker": (claim or {}).get("marker"),
        "confidence": (claim or {}).get("confidence"),
        "citation": (claim or {}).get("source_citation"),
        "detail": detail,
    }


def _coplanar_names(record: dict[str, Any]) -> list[str]:
    raw = record.get("coplanar")
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def _segment_edge(
    record: dict[str, Any], segment: dict[str, Any], known: set[str]
) -> dict[str, Any] | None:
    """The edge one segment implies, or None if it implies none.

    A drift or a station-keep is a behaviour, not a relationship, and an
    edge naming a counterpart nothing else holds would be a line to nowhere.
    """
    if segment.get("archived"):
        return None
    mode = str(segment.get("mode"))
    kind = MODE_EDGE.get(mode)
    other = str(segment.get("related_object_id") or "")
    if kind is None or not other:
        return None
    if other not in known and not other.startswith(TARGET_PREFIX):
        return None
    detail = f"{MODE_LABELS.get(mode, mode)}, {segment.get('start_epoch') or ''}"
    return _edge(kind, record["id"], other, segment.get("claim"), detail.strip(", "))


def _segment_edges(
    records: list[dict[str, Any]], layers: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    known = {record["id"] for record in records}
    edges = []
    for record in records:
        layer = layers.get(record["id"]) or {}
        for segment in layer.get("pol_segments", []):
            edge = _segment_edge(record, segment, known)
            if edge is not None:
                edges.append(edge)
    return edges


def _coplanar_edges(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {str(r.get("catalogue_name")): r["id"] for r in records}
    edges = []
    for record in records:
        for name in _coplanar_names(record):
            other = by_name.get(name)
            target = other or TARGET_PREFIX + name.lower().replace(" ", "-")
            if target == record["id"]:
                continue
            edges.append(
                _edge(
                    COPLANAR_WITH,
                    record["id"],
                    target,
                    COPLANAR_CLAIM,
                    "recorded in the catalogue",
                )
            )
    return edges


def build_graph(
    records: list[dict[str, Any]],
    layers: dict[str, dict[str, Any]] | None = None,
    stored_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Nodes and edges for the whole catalogue."""
    live = [r for r in records if not r.get("archived")]
    nodes: dict[str, dict[str, Any]] = {}
    for record in live:
        nodes[record["id"]] = _object_node(record)
        family = _family_node(record)
        nodes.setdefault(family["id"], family)

    edges = [
        _edge(
            BELONGS_TO_FAMILY,
            record["id"],
            FAMILY_PREFIX + str(record["family_id"]),
            MEMBERSHIP_CLAIM,
            "catalogue membership",
        )
        for record in live
    ]
    edges += _segment_edges(live, layers or {})
    edges += _coplanar_edges(live)
    for stored in stored_edges or []:
        if stored.get("archived"):
            continue
        edges.append(
            _edge(
                str(stored.get("kind")),
                str(stored.get("from_id")),
                str(stored.get("to_id")),
                stored.get("claim"),
                "recorded relationship",
            )
        )

    for edge in edges:
        for end in (edge["source"], edge["target"]):
            if end not in nodes and end.startswith(TARGET_PREFIX):
                nodes[end] = _target_node(end)
    edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    return {
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["label"])),
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
    }


def neighbourhood(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    """One node, its edges, and the nodes on the other end of them.

    The graph is navigated one step at a time rather than drawn whole. At 56
    objects plus families, targets and their edges, the whole thing is a
    hairball nobody can read, and the analyst's question is always "what is
    this connected to", never "show me everything at once".
    """
    by_id = {node["id"]: node for node in graph["nodes"]}
    focus = by_id.get(node_id)
    if focus is None:
        return {"focus": None, "nodes": [], "edges": []}
    touching = [
        edge for edge in graph["edges"] if node_id in (edge["source"], edge["target"])
    ]
    reachable = {focus["id"]}
    for edge in touching:
        reachable.update((edge["source"], edge["target"]))
    return {
        "focus": focus,
        "nodes": [by_id[i] for i in sorted(reachable) if i in by_id],
        "edges": touching,
        "counts": {"neighbours": len(reachable) - 1, "edges": len(touching)},
    }


def edge_vocabulary() -> dict[str, Any]:
    """What each edge kind means, served so the interface holds no copy."""
    return {
        "kinds": [
            {"value": kind, "label": label} for kind, label in EDGE_LABELS.items()
        ],
        "node_types": [
            {"value": OBJECT, "label": "Catalogued object"},
            {"value": FAMILY, "label": "Family"},
            {"value": TARGET, "label": "Outside the catalogue"},
        ],
        "instantaneous_modes": sorted(INSTANTANEOUS_MODES),
    }
