"""The relationship graph, assembled server-side.

Read-only. Every edge is derived from something that already carries its own
provenance -- a catalogue field, a pattern-of-life segment, or a stored
relationship -- so the graph cannot disagree with the timeline about what
happened, and no edge arrives unsourced.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.graph import edge_vocabulary, graph_from_store, neighbourhood

router = APIRouter(prefix="/api/graph")

NODE_NOT_FOUND = "No node with that id in the graph"


def _graph(request: Request) -> dict:
    return graph_from_store(request.app.state.systems_store)


@router.get("/vocabulary")
def graph_vocabulary():
    """What each edge kind and node type means."""
    return edge_vocabulary()


@router.get("")
def whole_graph(request: Request):
    """Every node and edge. The interface navigates it a step at a time, but
    the counts and the filters need the whole thing."""
    return _graph(request)


@router.get("/{node_id:path}")
def node_neighbourhood(request: Request, node_id: str):
    """One node, its edges, and what is on the other end of them."""
    result = neighbourhood(_graph(request), node_id)
    if result["focus"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NODE_NOT_FOUND
        )
    return result
