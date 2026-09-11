"""The relationship graph, assembled server-side.

Read-only. Every edge is derived from something that already carries its own
provenance -- a catalogue field, a pattern-of-life segment, or a stored
relationship -- so the graph cannot disagree with the timeline about what
happened, and no edge arrives unsourced.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.graph import build_graph, edge_vocabulary, neighbourhood

router = APIRouter(prefix="/api/graph")

NODE_NOT_FOUND = "No node with that id in the graph"


def _graph(request: Request) -> dict:
    store = request.app.state.systems_store
    records = store.list(include_archived=True)
    layers = {
        record["id"]: store.compendium_object(record["id"]) or {} for record in records
    }
    return build_graph(records, layers, store.list_compendium("relationships"))


@router.get("/vocabulary")
async def graph_vocabulary():
    """What each edge kind and node type means."""
    return edge_vocabulary()


@router.get("")
async def whole_graph(request: Request):
    """Every node and edge. The interface navigates it a step at a time, but
    the counts and the filters need the whole thing."""
    return _graph(request)


@router.get("/{node_id:path}")
async def node_neighbourhood(request: Request, node_id: str):
    """One node, its edges, and what is on the other end of them."""
    result = neighbourhood(_graph(request), node_id)
    if result["focus"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NODE_NOT_FOUND
        )
    return result
