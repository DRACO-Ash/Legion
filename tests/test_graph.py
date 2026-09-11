"""The relationship graph: every edge sourced, and sourced to the right thing.

The phase's bar is that an analyst can traverse from one object to everything
related to it, and that no edge is unsourced. The second half is the one that
can fail quietly, so most of this file is about provenance rather than shape.

The graph is derived from what the store already holds. Nothing here is a
second copy of the timeline or the catalogue, which is why the timeline and
the graph cannot disagree about what happened.
"""

from __future__ import annotations

import pytest

from src.graph import (
    BELONGS_TO_FAMILY,
    COPLANAR_WITH,
    FAMILY_PREFIX,
    MODE_EDGE,
    TARGET_PREFIX,
    build_graph,
    edge_tone,
    neighbourhood,
)

from .conftest import make_claim


def _record(name: str, **extra) -> dict:
    body = {
        "id": f"id-{name}",
        "catalogue_name": name,
        "family_id": "fam-1",
        "family_title": "Family One",
        "nation": "CN",
        "regime": "GEO",
        "archived": False,
    }
    body.update(extra)
    return body


def _layer(*segments) -> dict:
    return {"pol_segments": list(segments)}


def _segment(mode: str, other: str | None, **extra) -> dict:
    body = {"mode": mode, "start_epoch": "2025-01", "claim": make_claim()}
    body["related_object_id"] = other
    body.update(extra)
    return body


def _kinds(graph: dict) -> list[str]:
    return [edge["kind"] for edge in graph["edges"]]


# --- every edge is sourced --------------------------------------------------


def test_no_edge_arrives_without_a_citation() -> None:
    """The phase's bar. An unsourced edge would render identically to a
    sourced one, which is the failure this whole layer exists to prevent."""
    records = [_record("A", coplanar="B"), _record("B")]
    layers = {"id-A": _layer(_segment("rpo_docking", "id-B"))}

    graph = build_graph(records, layers)

    assert graph["edges"]
    for edge in graph["edges"]:
        assert edge["citation"], edge
        assert edge["marker"], edge


def test_a_catalogue_edge_cites_the_field_it_came_from() -> None:
    """Found in a browser: one shared claim meant a family membership edge
    cited the coplanar field. A citation naming the wrong field is worse than
    none, because a reader who follows it finds nothing that supports it."""
    graph = build_graph([_record("A", coplanar="B"), _record("B")])
    cited = {edge["kind"]: edge["citation"] for edge in graph["edges"]}

    assert "family_id" in cited[BELONGS_TO_FAMILY]
    assert "coplanar" in cited[COPLANAR_WITH]
    assert cited[BELONGS_TO_FAMILY] != cited[COPLANAR_WITH]


def test_an_edge_inherits_the_provenance_of_the_segment_behind_it() -> None:
    """Storing the same fact twice would let the timeline and the graph
    disagree about what happened."""
    layers = {
        "id-A": _layer(
            _segment(
                "rpo_shadowing",
                "id-B",
                claim=make_claim(
                    marker="INFERENCE", confidence="low", source_citation="A source"
                ),
            )
        )
    }

    graph = build_graph([_record("A"), _record("B")], layers)
    edge = next(e for e in graph["edges"] if e["kind"] == "shadowed")

    assert edge["marker"] == "INFERENCE"
    assert edge["confidence"] == "low"
    assert edge["tone"] == "inference"


@pytest.mark.parametrize(
    ("marker", "tone"),
    [("FACT", "fact"), ("INFERENCE", "inference"), ("SPECULATION", "speculation")],
)
def test_the_line_style_follows_the_marker(marker, tone) -> None:
    """Style is the redundant half. The interface prints the marker as text
    beside every edge, so a dashed line is never the whole signal."""
    assert edge_tone({"marker": marker}) == tone


def test_an_unmarked_claim_does_not_render_as_established() -> None:
    """Defaulting to solid would promote an unknown to a fact."""
    assert edge_tone(None) == "inference"
    assert edge_tone({}) == "inference"


# --- what becomes an edge, and what does not --------------------------------


@pytest.mark.parametrize("mode", sorted(MODE_EDGE))
def test_every_relational_mode_produces_an_edge(mode: str) -> None:
    layers = {"id-A": _layer(_segment(mode, "id-B"))}
    graph = build_graph([_record("A"), _record("B")], layers)
    assert MODE_EDGE[mode] in _kinds(graph)


@pytest.mark.parametrize("mode", ["station_keeping", "longitudinal_drift", "quiescent"])
def test_a_solo_behaviour_is_not_a_relationship(mode: str) -> None:
    """A drift is a behaviour, not an edge. Inventing one would fill the
    graph with lines that mean nothing."""
    layers = {"id-A": _layer(_segment(mode, None))}
    graph = build_graph([_record("A"), _record("B")], layers)
    assert _kinds(graph) == [BELONGS_TO_FAMILY, BELONGS_TO_FAMILY]


def test_an_archived_segment_contributes_no_edge() -> None:
    layers = {"id-A": _layer(_segment("rpo_docking", "id-B", archived=True))}
    graph = build_graph([_record("A"), _record("B")], layers)
    assert "captured" not in _kinds(graph)


def test_an_archived_record_is_not_a_node() -> None:
    graph = build_graph([_record("A"), _record("B", archived=True)])
    assert [n["label"] for n in graph["nodes"] if n["type"] == "object"] == ["A"]


def test_a_counterpart_outside_the_catalogue_becomes_a_marked_node() -> None:
    """USA 314 is reachable, and visibly not one of our systems."""
    layers = {"id-A": _layer(_segment("rpo_shadowing", f"{TARGET_PREFIX}usa-314"))}
    graph = build_graph([_record("A")], layers)
    target = next(n for n in graph["nodes"] if n["type"] == "target")

    assert target["label"] == "usa 314"
    assert target["in_catalogue"] is False


def test_an_edge_to_a_node_that_does_not_exist_is_dropped() -> None:
    """A line to nowhere is worse than a missing line: it implies a
    relationship with something the analyst cannot inspect."""
    layers = {"id-A": _layer(_segment("rpo_docking", "id-nobody"))}
    graph = build_graph([_record("A")], layers)
    assert _kinds(graph) == [BELONGS_TO_FAMILY]


def test_a_family_is_a_node_its_members_point_at() -> None:
    graph = build_graph([_record("A"), _record("B")])
    family = next(n for n in graph["nodes"] if n["type"] == "family")

    assert family["id"] == FAMILY_PREFIX + "fam-1"
    assert [e["target"] for e in graph["edges"]] == [family["id"], family["id"]]


# --- traversal --------------------------------------------------------------


def test_a_neighbourhood_carries_the_focus_its_edges_and_both_ends() -> None:
    records = [_record("A", coplanar="B"), _record("B"), _record("C")]
    graph = build_graph(records)

    view = neighbourhood(graph, "id-A")

    assert view["focus"]["label"] == "A"
    assert {n["label"] for n in view["nodes"]} == {"A", "B", "Family One"}
    assert view["counts"]["neighbours"] == 2


def test_a_neighbourhood_includes_edges_pointing_inward() -> None:
    """Direction matters, but reachability does not depend on it: an analyst
    has to find the object that approached this one, not only the ones it
    approached."""
    layers = {"id-A": _layer(_segment("rpo_docking", "id-B"))}
    graph = build_graph([_record("A"), _record("B")], layers)

    view = neighbourhood(graph, "id-B")
    assert "captured" in [e["kind"] for e in view["edges"]]


def test_an_unknown_node_has_no_focus_rather_than_an_empty_graph() -> None:
    graph = build_graph([_record("A")])
    assert neighbourhood(graph, "nope")["focus"] is None


def test_every_object_can_reach_its_family_and_so_every_other_member() -> None:
    """The traversal bar: start from one object and reach the rest."""
    records = [_record(name) for name in "ABC"]
    graph = build_graph(records)

    family_id = neighbourhood(graph, "id-A")["nodes"]
    family = next(n for n in family_id if n["type"] == "family")
    siblings = {n["label"] for n in neighbourhood(graph, family["id"])["nodes"]}

    assert {"A", "B", "C"} <= siblings
